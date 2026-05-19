"""throttle.py — Gestion de la fréquence d'accès aux sources.

Cinq mécanismes complémentaires :
  1. TTL par source (min_interval_days, défaut 7j)
  2. Cooldown adaptatif si rendement faible (low_yield)
  3. Politesse par domaine (60s entre 2 hits)
  4. Respect robots.txt (cache 7j)
  5. Cooldown sur erreurs HTTP (429/503 → 24h, 403 → 7j)

État persisté dans `synopsis/throttle_state.json`.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.robotparser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# ── Constantes ───────────────────────────────────────────────────────────────
DEFAULT_INTERVAL_DAYS = 7
LOW_YIELD_THRESHOLD = 3
LOW_YIELD_RUNS_BEFORE_COOLDOWN = 3
MAX_INTERVAL_DAYS = 60
DOMAIN_POLITENESS_SEC = 60
ROBOTS_CACHE_DAYS = 7
RATE_LIMIT_COOLDOWN_HOURS = 24
BAN_COOLDOWN_DAYS = 7
USER_AGENT = "LibraryBot"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE = _PROJECT_ROOT / "synopsis" / "throttle_state.json"


# ── Utilitaires ──────────────────────────────────────────────────────────────
def _now() -> datetime:
    """Heure courante en UTC."""
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    """Sérialise une datetime en ISO 8601 avec suffixe Z."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(s: Optional[str]) -> Optional[datetime]:
    """Parse une chaîne ISO 8601 (Z accepté). None → None."""
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _domain(url: str) -> str:
    """Extrait le domaine (host) d'une URL, en minuscules."""
    return (urlparse(url).hostname or "").lower()


def _load(state_path: Path) -> dict:
    """Charge l'état JSON ou retourne une coquille vide."""
    if not state_path.exists():
        return {"sources": {}, "domains": {}}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"sources": {}, "domains": {}}


def _save(state: dict, state_path: Path) -> None:
    """Écriture atomique : tmp + os.replace."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(state_path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, state_path)


def _src_entry(state: dict, source: dict) -> dict:
    """Récupère/initialise l'entrée d'une source dans l'état."""
    label = source["label"]
    if label not in state["sources"]:
        state["sources"][label] = {
            "url": source.get("url", ""),
            "domain": _domain(source.get("url", "")),
            "last_fetch": None,
            "last_fetch_attempts": 0,
            "last_doc_count": 0,
            "consecutive_low_yield": 0,
            "current_interval_days": source.get("min_interval_days", DEFAULT_INTERVAL_DAYS),
            "last_status_code": None,
            "last_http_error": None,
            "last_html_fingerprint": None,
            "last_etag": None,
            "last_modified": None,
            "cooldown_until": None,
        }
    return state["sources"][label]


def _dom_entry(state: dict, domain: str) -> dict:
    """Récupère/initialise l'entrée d'un domaine dans l'état."""
    if domain not in state["domains"]:
        state["domains"][domain] = {
            "last_request_at": None,
            "rate_limit_until": None,
            "robots_txt_cached_at": None,
            "robots_disallow": [],
            "robots_crawl_delay": None,
        }
    return state["domains"][domain]


# ── API publique ─────────────────────────────────────────────────────────────
def should_fetch(source: dict, state_path: Path = DEFAULT_STATE) -> tuple[bool, str]:
    """Décide si la source doit être interrogée maintenant.

    Ordre de priorité (du plus dur au plus souple) :
    cooldown_source > domain_rate_limited > robots > ttl > politesse.
    """
    state = _load(state_path)
    src = _src_entry(state, source)
    dom = _dom_entry(state, src["domain"])
    now = _now()

    # 1. Cooldown source (suite à erreur HTTP)
    cd = _parse(src.get("cooldown_until"))
    if cd and cd > now:
        return False, "in_cooldown"

    # 2. Rate-limit domaine
    rl = _parse(dom.get("rate_limit_until"))
    if rl and rl > now:
        return False, "domain_rate_limited"

    # 3. robots.txt
    if not check_robots(source.get("url", ""), state_path):
        return False, "robots_disallow"

    # 4. TTL adaptatif (low_yield est implicitement encodé via current_interval_days)
    last = _parse(src.get("last_fetch"))
    interval = max(
        source.get("min_interval_days", DEFAULT_INTERVAL_DAYS),
        int(src.get("current_interval_days") or DEFAULT_INTERVAL_DAYS),
    )
    if last and (now - last) < timedelta(days=interval):
        if src.get("consecutive_low_yield", 0) >= LOW_YIELD_RUNS_BEFORE_COOLDOWN:
            return False, "low_yield_cooldown"
        return False, "ttl_not_elapsed"

    # 5. Politesse domaine (sans bloquer ici ; politeness_wait s'en charge si voulu)
    last_req = _parse(dom.get("last_request_at"))
    if last_req and (now - last_req).total_seconds() < DOMAIN_POLITENESS_SEC:
        return False, "domain_polite_wait"

    return True, "ok"


def record_fetch(
    source: dict,
    success: bool,
    doc_count: int = 0,
    status_code: int = 200,
    response_html: str = "",
    response_headers: Optional[dict] = None,
    state_path: Path = DEFAULT_STATE,
) -> None:
    """Met à jour l'état après un fetch."""
    response_headers = response_headers or {}
    state = _load(state_path)
    src = _src_entry(state, source)
    now = _now()

    src["last_fetch_attempts"] = int(src.get("last_fetch_attempts", 0)) + 1
    src["last_status_code"] = status_code

    if success:
        src["last_fetch"] = _iso(now)
        src["last_doc_count"] = doc_count
        src["last_http_error"] = None

        if response_html:
            src["last_html_fingerprint"] = hashlib.sha256(
                response_html.encode("utf-8", errors="ignore")
            ).hexdigest()

        # Headers conditionnels (case-insensitive)
        headers_lc = {k.lower(): v for k, v in response_headers.items()}
        if "etag" in headers_lc:
            src["last_etag"] = headers_lc["etag"]
        if "last-modified" in headers_lc:
            src["last_modified"] = headers_lc["last-modified"]

        # Gestion low_yield
        if doc_count > 0 and doc_count >= LOW_YIELD_THRESHOLD:
            src["consecutive_low_yield"] = 0
            # On peut détendre l'intervalle après un retour productif
            src["current_interval_days"] = source.get(
                "min_interval_days", DEFAULT_INTERVAL_DAYS
            )
        else:
            src["consecutive_low_yield"] = int(src.get("consecutive_low_yield", 0)) + 1
            if src["consecutive_low_yield"] >= LOW_YIELD_RUNS_BEFORE_COOLDOWN:
                cur = int(src.get("current_interval_days") or DEFAULT_INTERVAL_DAYS)
                src["current_interval_days"] = min(max(cur, 1) * 2, MAX_INTERVAL_DAYS)
    else:
        src["last_http_error"] = f"HTTP {status_code}"

    # Cooldowns sur erreurs HTTP
    if status_code in (429, 503):
        src["cooldown_until"] = _iso(now + timedelta(hours=RATE_LIMIT_COOLDOWN_HOURS))
        dom = _dom_entry(state, src["domain"])
        dom["rate_limit_until"] = _iso(now + timedelta(hours=1))
    elif status_code == 403:
        src["cooldown_until"] = _iso(now + timedelta(days=BAN_COOLDOWN_DAYS))

    _save(state, state_path)


def conditional_headers(source: dict, state_path: Path = DEFAULT_STATE) -> dict:
    """Construit les headers If-None-Match / If-Modified-Since si dispos."""
    state = _load(state_path)
    src = _src_entry(state, source)
    headers: dict = {}
    if src.get("last_etag"):
        headers["If-None-Match"] = src["last_etag"]
    if src.get("last_modified"):
        headers["If-Modified-Since"] = src["last_modified"]
    return headers


def fingerprint_changed(
    html: str, source: dict, state_path: Path = DEFAULT_STATE
) -> bool:
    """True si le HTML diffère du dernier fingerprint connu."""
    state = _load(state_path)
    src = _src_entry(state, source)
    new_fp = hashlib.sha256(html.encode("utf-8", errors="ignore")).hexdigest()
    old_fp = src.get("last_html_fingerprint")
    return old_fp != new_fp


def _parse_robots_minimal(robots_txt: str, user_agent: str) -> list[str]:
    """Parseur tolérant : retourne la liste des Disallow qui s'appliquent
    à notre user-agent. Ignore les wildcards (* et $) — extensions non-standard
    que stdlib RobotFileParser interprète comme bloquantes par défaut, ce qui
    cause des faux positifs sur des sites parfaitement permissifs comme
    Reporterre ou libcom.

    Stratégie :
    - Plusieurs `User-agent:` consécutifs forment un même bloc
    - Dès qu'on voit un `Disallow:` (ou `Allow:`), le groupe d'UA est figé
    - Le bloc suivant `User-agent:` (après une directive) ouvre un nouveau groupe
    - Notre block est "actif" si user_agent OU '*' est dans la liste des UA du bloc
    """
    matching_ua = user_agent.lower()
    disallows: list[str] = []

    current_uas: list[str] = []
    block_active = False
    # True après avoir vu un Disallow/Allow dans le bloc courant — un nouveau
    # User-agent à ce moment ouvre un NOUVEAU bloc.
    block_has_rules = False

    for line in robots_txt.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()

        if key == "user-agent":
            if block_has_rules:
                # On entame un NOUVEAU bloc — réinitialiser
                current_uas = []
                block_active = False
                block_has_rules = False
            ua = value.lower()
            current_uas.append(ua)
            if ua == "*" or ua == matching_ua:
                block_active = True
        elif key == "disallow":
            block_has_rules = True
            if block_active and value:
                if "*" in value or "$" in value:
                    continue  # wildcards ignorés
                disallows.append(value)
        elif key == "allow":
            block_has_rules = True
        # Autres directives (Crawl-delay, Sitemap, etc.) : ignorées

    return disallows


def check_robots(url: str, state_path: Path = DEFAULT_STATE) -> bool:
    """Vérifie robots.txt avec cache 7j. True si autorisé (ou indisponible)."""
    if not url:
        return True
    domain = _domain(url)
    if not domain:
        return True
    state = _load(state_path)
    dom = _dom_entry(state, domain)
    now = _now()

    cached_at = _parse(dom.get("robots_txt_cached_at"))
    cache_stale = (not cached_at) or (now - cached_at) > timedelta(days=ROBOTS_CACHE_DAYS)

    if cache_stale:
        scheme = urlparse(url).scheme or "https"
        robots_url = f"{scheme}://{domain}/robots.txt"
        disallows: list[str] = []
        try:
            import urllib.request
            req = urllib.request.Request(
                robots_url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; LibraryBot/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                ctype = resp.headers.get("Content-Type", "").lower()
                body = resp.read(64_000).decode("utf-8", errors="replace")
            # Si le serveur renvoie du HTML (CAPTCHA, page d'erreur déguisée) :
            # on considère qu'il n'y a pas de robots.txt valide → autorisé.
            if "html" in ctype or body.lstrip().lower().startswith("<!doctype"):
                disallows = []  # vide = pas de règle → autorisé
            else:
                disallows = _parse_robots_minimal(body, USER_AGENT)
        except Exception:
            # Pas de robots.txt accessible → autorisé par défaut.
            disallows = []
        dom["robots_disallow"] = disallows
        dom["robots_crawl_delay"] = None  # crawl-delay rarement utile, on simplifie
        dom["robots_txt_cached_at"] = _iso(now)
        _save(state, state_path)

    # Décision : on bloque uniquement si le path matche exactement un Disallow.
    path = urlparse(url).path or "/"
    for d in dom.get("robots_disallow", []):
        if d and path.startswith(d):
            return False
    return True


def politeness_wait(domain: str, state_path: Path = DEFAULT_STATE) -> None:
    """Bloque jusqu'à ce que 60s se soient écoulées depuis le dernier hit."""
    state = _load(state_path)
    dom = _dom_entry(state, domain)
    last_req = _parse(dom.get("last_request_at"))
    now = _now()

    if last_req:
        delta = (now - last_req).total_seconds()
        wait = DOMAIN_POLITENESS_SEC - delta
        # Respecter aussi un crawl-delay éventuel
        crawl_delay = dom.get("robots_crawl_delay") or 0
        wait = max(wait, crawl_delay - delta)
        if wait > 0:
            time.sleep(wait)

    dom["last_request_at"] = _iso(_now())
    _save(state, state_path)


def report(state_path: Path = DEFAULT_STATE) -> dict:
    """Statistiques agrégées sur l'état throttle."""
    state = _load(state_path)
    now = _now()
    sources = state.get("sources", {})
    domains = state.get("domains", {})

    active = 0
    in_cooldown = 0
    low_yield = 0
    longest_idle_days = 0.0
    longest_idle_label = None

    for label, src in sources.items():
        cd = _parse(src.get("cooldown_until"))
        if cd and cd > now:
            in_cooldown += 1
        else:
            active += 1
        if src.get("consecutive_low_yield", 0) >= LOW_YIELD_RUNS_BEFORE_COOLDOWN:
            low_yield += 1
        last = _parse(src.get("last_fetch"))
        if last:
            idle = (now - last).total_seconds() / 86400.0
            if idle > longest_idle_days:
                longest_idle_days = idle
                longest_idle_label = label

    rate_limited_domains = sum(
        1
        for d in domains.values()
        if (rl := _parse(d.get("rate_limit_until"))) and rl > now
    )

    return {
        "sources_total": len(sources),
        "sources_active": active,
        "sources_in_cooldown": in_cooldown,
        "sources_low_yield": low_yield,
        "domains_total": len(domains),
        "domains_rate_limited": rate_limited_domains,
        "longest_idle_days": round(longest_idle_days, 2),
        "longest_idle_source": longest_idle_label,
        "generated_at": _iso(now),
    }


# ── Démonstration ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import tempfile

    demo_state = Path(tempfile.gettempdir()) / "throttle_demo_state.json"
    if demo_state.exists():
        demo_state.unlink()

    sources = [
        {"label": "Demo A", "url": "https://example.com/a", "min_interval_days": 7},
        {"label": "Demo B", "url": "https://example.org/b", "min_interval_days": 3},
        {"label": "Demo C", "url": "https://example.net/c"},
    ]

    print("── 1. should_fetch sur 3 sources factices (état vide) ──")
    for s in sources:
        ok, reason = should_fetch(s, state_path=demo_state)
        print(f"  {s['label']:8s} → {ok} ({reason})")

    print("\n── 2. 3 record_fetch consécutifs avec doc_count=0 (Demo A) ──")
    for i in range(3):
        record_fetch(
            sources[0],
            success=True,
            doc_count=0,
            status_code=200,
            response_html=f"<html>iter{i}</html>",
            state_path=demo_state,
        )
        st = _load(demo_state)["sources"]["Demo A"]
        print(
            f"  iter {i+1}: low_yield={st['consecutive_low_yield']}, "
            f"interval={st['current_interval_days']}d"
        )

    print("\n── 3. record_fetch avec status_code=429 (Demo B) ──")
    record_fetch(
        sources[1],
        success=False,
        doc_count=0,
        status_code=429,
        state_path=demo_state,
    )
    st_b = _load(demo_state)["sources"]["Demo B"]
    print(f"  cooldown_until = {st_b['cooldown_until']}")
    ok, reason = should_fetch(sources[1], state_path=demo_state)
    print(f"  should_fetch → {ok} ({reason})")

    print("\n── 4. conditional_headers / fingerprint_changed ──")
    record_fetch(
        sources[2],
        success=True,
        doc_count=10,
        status_code=200,
        response_html="<html>v1</html>",
        response_headers={"ETag": '"xyz"', "Last-Modified": "Sat, 15 May 2026 12:00:00 GMT"},
        state_path=demo_state,
    )
    print(f"  headers conditionnels: {conditional_headers(sources[2], state_path=demo_state)}")
    print(
        f"  fingerprint identique  : {fingerprint_changed('<html>v1</html>', sources[2], state_path=demo_state)}"
    )
    print(
        f"  fingerprint différent  : {fingerprint_changed('<html>v2</html>', sources[2], state_path=demo_state)}"
    )

    print("\n── 5. report() ──")
    rep = report(state_path=demo_state)
    for k, v in rep.items():
        print(f"  {k:24s}: {v}")

    print(f"\nÉtat de démo écrit dans : {demo_state}")

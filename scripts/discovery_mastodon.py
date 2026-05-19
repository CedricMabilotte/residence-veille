#!/usr/bin/env python3
"""
discovery_mastodon.py — Veille sur hashtags + comptes Mastodon.

API Mastodon publique (sans auth) :
- GET https://<instance>/api/v1/timelines/tag/<hashtag>?limit=40
- GET https://<instance>/api/v1/accounts/lookup?acct=<user>
- GET https://<instance>/api/v1/accounts/<id>/statuses?limit=40

On extrait les URLs externes (pas les permaliens Mastodon, pas les mentions)
mentionnées dans les statuses, et on les agrège dans discovery/candidates.yml.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
import yaml

HEADERS = {"User-Agent": "LibraryBot/1.0 (mailto:cedric.mabilotte@gmail.com)"}
TIMEOUT = 20
DELAY = 0.8

DEFAULT_INSTANCES = ["mamot.fr", "todon.eu", "mastodon.social"]
DEFAULT_HASHTAGS = [
    "opencall", "appelacandidature", "residenceartiste", "artistresidency",
    "convocatoria", "appelaprojets", "appelaartistes", "aircall",
    "residencia", "residencyopen",
]
DEFAULT_ACCOUNTS: list[str] = []  # ex. ["confederationpaysanne@mamot.fr"]

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CANDIDATES = ROOT / "discovery" / "candidates.yml"
DEFAULT_CATALOG = ROOT / "synopsis" / "catalog.json"


# ── Helpers candidates.yml ────────────────────────────────────────────────────
def _now_iso() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _today() -> str:
    return _dt.date.today().isoformat()


def _load_candidates(path: Path) -> dict:
    if not path.exists():
        return {"last_updated": _now_iso(), "total_candidates": 0, "candidates": []}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {"candidates": []}


def _save_candidates(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["last_updated"] = _now_iso()
    data["total_candidates"] = len(data.get("candidates", []))
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def _merge_candidate(existing: list[dict], new_cand: dict) -> None:
    for cand in existing:
        if cand.get("url") == new_cand["url"]:
            cand["seen_count"] = cand.get("seen_count", 1) + 1
            cand["last_seen"] = new_cand["last_seen"]
            for ff in new_cand.get("found_from", []):
                if ff not in cand.get("found_from", []):
                    cand.setdefault("found_from", []).append(ff)
            return
    existing.append(new_cand)


def _known_urls_from_catalog(catalog_path: Path) -> set[str]:
    """URLs déjà présentes dans le catalog → on ne les re-proposera pas."""
    if not catalog_path.exists():
        return set()
    try:
        with catalog_path.open("r", encoding="utf-8") as f:
            cat = json.load(f)
    except (OSError, json.JSONDecodeError):
        return set()
    return {doc.get("url", "") for doc in (cat.get("docs") or {}).values()
            if doc.get("url")}


# ── API Mastodon ──────────────────────────────────────────────────────────────
def fetch_tag_timeline(instance: str, hashtag: str,
                        limit: int = 40) -> list[dict]:
    """Retourne les statuses récents pour ce hashtag sur l'instance."""
    url = f"https://{instance}/api/v1/timelines/tag/{hashtag}"
    try:
        r = requests.get(url, params={"limit": str(min(limit, 40))},
                          headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        return r.json() if isinstance(r.json(), list) else []
    except (requests.RequestException, ValueError):
        return []


def _lookup_account(instance: str, acct: str) -> Optional[str]:
    """Résout un acct (ex 'user@instance') vers un id sur l'instance donnée."""
    url = f"https://{instance}/api/v1/accounts/lookup"
    try:
        r = requests.get(url, params={"acct": acct}, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        return r.json().get("id")
    except (requests.RequestException, ValueError):
        return None


def fetch_account_statuses(instance: str, acct: str,
                            limit: int = 40) -> list[dict]:
    """Retourne les derniers statuses d'un compte (acct = 'user@instance' ou 'user')."""
    acct_id = _lookup_account(instance, acct)
    if not acct_id:
        return []
    url = f"https://{instance}/api/v1/accounts/{acct_id}/statuses"
    try:
        r = requests.get(url, params={"limit": str(min(limit, 40))},
                          headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        return r.json() if isinstance(r.json(), list) else []
    except (requests.RequestException, ValueError):
        return []


# ── Extraction d'URLs depuis un status ────────────────────────────────────────
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)


def extract_urls_from_status(status: dict) -> list[str]:
    """Parse le HTML du content pour extraire les liens externes.
    Filtre les permaliens Mastodon (.../tags/X, .../@user) et les mentions."""
    content = status.get("content") or ""
    urls = _HREF_RE.findall(content)
    out: list[str] = []
    for u in urls:
        if not u.startswith("http"):
            continue
        # Permaliens Mastodon : /tags/<tag> ou /@<user>
        path = urlparse(u).path
        if "/tags/" in path or path.startswith("/@") or "/@/" in path:
            continue
        out.append(u)
    return out


def _account_label(status: dict) -> str:
    acc = status.get("account") or {}
    return acc.get("acct") or acc.get("username") or "unknown"


# ── Orchestration ─────────────────────────────────────────────────────────────
def discover_from_mastodon(candidates_path: Path = DEFAULT_CANDIDATES,
                            instances: Optional[list[str]] = None,
                            hashtags: Optional[list[str]] = None,
                            accounts: Optional[list[str]] = None) -> dict:
    """Agrège les URLs trouvées dans les hashtags + comptes surveillés.
    Skip si déjà dans le catalog (URL match)."""
    instances = instances or DEFAULT_INSTANCES
    hashtags = hashtags or DEFAULT_HASHTAGS
    accounts = accounts or DEFAULT_ACCOUNTS

    known_urls = _known_urls_from_catalog(DEFAULT_CATALOG)
    data = _load_candidates(candidates_path)
    new_count, statuses_seen = 0, 0

    # 1) Hashtags : on essaie chaque instance jusqu'à obtenir une réponse.
    for tag in hashtags:
        for inst in instances:
            statuses = fetch_tag_timeline(inst, tag, limit=40)
            time.sleep(DELAY)
            if not statuses:
                continue
            statuses_seen += len(statuses)
            for s in statuses:
                for url in extract_urls_from_status(s):
                    if url in known_urls:
                        continue
                    cand = {
                        "url": url,
                        "type": "mastodon",
                        "found_from": [{
                            "source": f"Mastodon #{tag} @{inst} (par @{_account_label(s)})",
                            "context": re.sub(r"<[^>]+>", " ",
                                              s.get("content", ""))[:300].strip(),
                            "timestamp": _now_iso(),
                        }],
                        "seen_count": 1,
                        "domain": urlparse(url).netloc,
                        "first_seen": _today(),
                        "last_seen": _today(),
                        "metadata": {"hashtag": tag, "instance": inst},
                        "suggested_action": "follow_one_time",
                    }
                    _merge_candidate(data["candidates"], cand)
                    new_count += 1
            break  # une instance suffit par tag

    # 2) Comptes surveillés.
    for acct in accounts:
        # Choisit l'instance : 'user@host' → host ; 'user' → 1re instance.
        inst = acct.split("@")[-1] if "@" in acct else instances[0]
        statuses = fetch_account_statuses(inst, acct, limit=40)
        time.sleep(DELAY)
        for s in statuses:
            for url in extract_urls_from_status(s):
                if url in known_urls:
                    continue
                cand = {
                    "url": url,
                    "type": "mastodon",
                    "found_from": [{
                        "source": f"Mastodon account @{acct}",
                        "context": re.sub(r"<[^>]+>", " ",
                                          s.get("content", ""))[:300].strip(),
                        "timestamp": _now_iso(),
                    }],
                    "seen_count": 1,
                    "domain": urlparse(url).netloc,
                    "first_seen": _today(),
                    "last_seen": _today(),
                    "metadata": {"account": acct},
                    "suggested_action": "follow_one_time",
                }
                _merge_candidate(data["candidates"], cand)
                new_count += 1

    _save_candidates(candidates_path, data)
    return {"hashtags": len(hashtags), "accounts": len(accounts),
            "statuses_seen": statuses_seen, "added_or_updated": new_count,
            "total_candidates": data["total_candidates"]}


if __name__ == "__main__":
    res = discover_from_mastodon()
    print(json.dumps(res, indent=2, ensure_ascii=False), file=sys.stderr)

#!/usr/bin/env python3
"""
watch.py — Orchestration de la veille des opportunités arts plastiques.

Pipeline (par source) :
  1. Scrape via le bon parser (html, deep_html, rss, jsonld_event)
  2. Pour chaque item brut :
     a. Détection langue (heuristique simple)
     b. resume_fr.py si lang != fr → résumé FR + traduction titre
     c. detect_type.py → residence | bourse | prix | exposition (+ confidence)
     d. extract_opportunity.py → fiche YAML structurée
     e. score_opportunity.py → score + bonus
     f. organisme_manager → maj fiche organisme + track record
     g. auto-promotion si score ≥ threshold ET confidence ≥ 0.85

Variables d'env :
  CLAUDE_CODE_OAUTH_TOKEN : OAuth Claude Code (subscription)
  SCORE_THRESHOLD         : surcharge le seuil de concepts.yml
  DRY_RUN                 : "true" pour ne pas écrire les fiches
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import requests
import yaml

try:
    from bs4 import BeautifulSoup
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

# Imports locaux (scripts du fork « Résidence »)
from parsers import dispatch as parser_dispatch
import throttle

import detect_type
import claude_guard
import extract_opportunity
import resume_fr
import score_opportunity
import organisme_manager

# ── Chemins ────────────────────────────────────────────────────────────────────
CONFIG_PATH    = ROOT / "config" / "sources.yml"
CONCEPTS_PATH  = ROOT / "config" / "concepts.yml"
APPELS_DIR     = ROOT / "appels"
REPORTS_DIR    = ROOT / "reports"
DISCOVERY_DIR  = ROOT / "discovery"

for type_id in ("residence", "bourse", "prix", "exposition"):
    (APPELS_DIR / type_id).mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)

# ── Constantes ─────────────────────────────────────────────────────────────────
DRY_RUN = os.getenv("DRY_RUN", "").lower() == "true"

# Budget de durée par run (minutes). Au-delà, on arrête de traiter de nouvelles
# sources et on laisse la main aux étapes suivantes du workflow (deadline_tracker,
# site, publication). Ajouté le 2026-11-18 : les runs de sept.-nov. 2026 dépassaient
# le timeout du job (2 h) et le site n'était plus régénéré.
MAX_RUN_MINUTES = int(os.getenv("MAX_RUN_MINUTES") or 60)

# Index des items déjà traités (URL → statut). Versionné dans git pour survivre
# d'un run GH Actions à l'autre. Avant le 2026-11-18, chaque run repartait de zéro
# et renvoyait à Claude tous les items de toutes les sources (jusqu'à 4 appels
# par item), ce qui épuisait la limite hebdomadaire de la souscription.
SEEN_PATH = DISCOVERY_DIR / "seen_items.json"
# Re-traiter un item déjà vu après N jours (0 = jamais). Les items promus ont une
# fiche suivie par deadline_tracker, les rejets « date passée » ne reviennent pas.
RECHECK_DAYS = int(os.getenv("RECHECK_DAYS") or 0)


def _norm_url(url: str) -> str:
    u = (url or "").strip().lower()
    u = re.sub(r"^https?://(www\.)?", "", u)
    u = re.sub(r"[?#].*$", "", u)
    return u.rstrip("/")


def load_seen() -> dict:
    if SEEN_PATH.exists():
        try:
            return json.loads(SEEN_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_seen(seen: dict) -> None:
    if DRY_RUN:
        return
    SEEN_PATH.write_text(
        json.dumps(seen, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8",
    )


def seen_bootstrap(seen: dict) -> int:
    """Première exécution : peuple l'index depuis les fiches existantes (appels/,
    archive/, discovery/quarantine/) et les rapports de run passés, pour ne pas
    re-payer ce qui a déjà été traité."""
    added = 0
    today = _dt.date.today().isoformat()
    for base, status in ((APPELS_DIR, "promoted"), (ROOT / "archive", "archived"),
                         (DISCOVERY_DIR / "quarantine", "quarantined")):
        for p in base.rglob("*.yml"):
            try:
                f = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            u = _norm_url(f.get("source_url") or "")
            if u and u not in seen:
                seen[u] = {"status": status, "first_seen": f.get("fetched_at", today)[:10],
                           "last_seen": today, "fiche": p.stem}
                added += 1
    for rp in sorted(REPORTS_DIR.glob("run_*.json")):
        try:
            logs = (json.loads(rp.read_text(encoding="utf-8")) or {}).get("logs") or []
        except Exception:
            continue
        for lg in logs:
            u = _norm_url(lg.get("url") or "")
            st = lg.get("status")
            if u and st in ("below_threshold", "skipped") and u not in seen:
                seen[u] = {"status": st, "first_seen": rp.stem[4:14], "last_seen": rp.stem[4:14]}
                added += 1
    return added


def seen_should_skip(seen: dict, url: str) -> str | None:
    """Retourne la raison du skip, ou None si l'item doit être traité."""
    rec = seen.get(_norm_url(url))
    if not rec:
        return None
    if RECHECK_DAYS and rec.get("status") in ("below_threshold", "skipped", "error"):
        try:
            last = _dt.date.fromisoformat(rec.get("last_seen", "1970-01-01"))
            if (_dt.date.today() - last).days >= RECHECK_DAYS:
                return None
        except ValueError:
            return None
    return f"déjà vu ({rec.get('status')}, {rec.get('last_seen')})"


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def load_concepts() -> dict:
    return yaml.safe_load(CONCEPTS_PATH.read_text(encoding="utf-8"))


def url_uid(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:8]


# Un item doit pointer vers une page d'annonce HTML : tout lien finissant
# par l'une de ces extensions (fichier) est écarté.
SKIP_EXTENSIONS = (".pdf", ".doc", ".docx", ".epub", ".zip", ".rar",
                   ".jpg", ".jpeg", ".png", ".gif", ".mp4", ".mp3")
CACHE_DIR = ROOT / ".cache" / "pages"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def fetch_page_body(url: str, timeout: int = 30) -> str:
    """
    Fetch et nettoie une page HTML. Cache disque par hash d'URL pour éviter
    les re-fetch dans le même run et entre runs proches.
    """
    url_hash = hashlib.md5(url.encode()).hexdigest()
    cache_file = CACHE_DIR / f"{url_hash}.txt"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8,es;q=0.7",
    }
    try:
        r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        r.raise_for_status()
    except Exception as e:
        cache_file.write_text("", encoding="utf-8")  # marquer comme tenté
        return ""

    if "text/html" not in (r.headers.get("Content-Type") or ""):
        cache_file.write_text("", encoding="utf-8")
        return ""

    if _HAS_BS4:
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
    else:
        text = re.sub(r"<[^>]+>", " ", r.text)
        text = re.sub(r"\s+", " ", text).strip()

    text = text[:15000]  # cap raisonnable
    cache_file.write_text(text, encoding="utf-8")
    return text


def detect_lang(text: str) -> str:
    """Heuristique très simple. Idéalement : langdetect ou Claude."""
    t = text.lower()
    fr_hits = sum(t.count(w) for w in [" le ", " la ", " des ", " les ", " et ", " une ", " avec "])
    en_hits = sum(t.count(w) for w in [" the ", " of ", " and ", " a ", " is ", " with ", " for "])
    es_hits = sum(t.count(w) for w in [" de ", " la ", " el ", " los ", " las ", " con ", " una "])
    best = max((("fr", fr_hits), ("en", en_hits), ("es", es_hits)), key=lambda x: x[1])
    return best[0] if best[1] > 0 else "fr"


def process_item(item: dict, source_label: str) -> dict | None:
    """
    item attendu : {url, title, text, context?}
    Retourne un dict de log {url, status, score, type, ...} ou None si erreur.
    """
    url = item.get("url") or ""
    title = item.get("title") or item.get("link_text") or ""
    body = item.get("text") or item.get("context") or ""

    if not url or not title:
        return None

    print(f"    · {title[:80]}")

    url_low = url.lower().rstrip("/")

    # 0. Skip : un item doit pointer vers une page d'annonce HTML, pas vers
    #    un fichier (PDF, doc, image, archive…).
    if url_low.endswith(SKIP_EXTENSIONS):
        print(f"      ↳ skip : lien vers un fichier, pas une annonce HTML")
        return {"url": url, "status": "skipped", "reason": "non_html_link"}

    # 0bis. Enrichir le body en lisant la page de l'annonce
    if len(body) < 500:
        fetched = fetch_page_body(url)
        if fetched and len(fetched) > len(body):
            body = fetched
            print(f"      ↳ body enrichi : {len(body)} chars (HTML)")
        elif len(body) < 50:
            print(f"      ↳ skip : body trop court ({len(body)}) et fetch vide")
            return {"url": url, "status": "skipped", "reason": "empty_body"}

    # 1. Langue
    lang = detect_lang(body or title)

    # 2. Résumé FR si non-FR
    if lang != "fr":
        rfr = resume_fr.resume_fr(title, body, lang)
        nom_fr = rfr.get("nom_fr") or title
        resume = rfr.get("resume_fr")
    else:
        nom_fr = title
        resume = None

    # 3. Détection de type
    try:
        det = detect_type.detect_type(title, body, url)
    except Exception as e:
        print(f"      ↳ ✗ detect_type erreur : {str(e)[:120]}")
        return {"url": url, "status": "error", "step": "detect_type", "error": str(e)}

    if det["confidence"] < 0.7:
        print(f"      ↳ skip : type {det['type']} conf {det['confidence']:.2f} < 0.7")
        return {"url": url, "status": "skipped", "reason": "confidence type < 0.7", "detection": det}

    # 4. Extraction
    try:
        fiche = extract_opportunity.extract_opportunity(
            title, body, url, det["type"], lang,
        )
    except Exception as e:
        print(f"      ↳ ✗ extract erreur : {str(e)[:120]}")
        return {"url": url, "status": "error", "step": "extract", "error": str(e)}

    # Affichage bilingue du titre
    if lang != "fr":
        fiche.setdefault("opportunite", {})
        fiche["opportunite"]["nom_fr"] = nom_fr
        fiche["opportunite"]["affichage_titre"] = f"{title} [{nom_fr}]"
        fiche["_meta"]["resume_fr"] = resume
    fiche["_meta"]["detection_confidence"] = det["confidence"]
    fiche["_meta"]["detection_method"] = det["method"]
    fiche["_meta"]["source_label"] = source_label

    # 5. Scoring
    sc = score_opportunity.score_fiche(fiche)
    fiche["score"] = sc["score"]
    # Barème public (config/criteres.yml) — schéma déjà attendu par
    # generate_site.py::fiche_fields/render_fiche_item (table "Critères
    # recherchés"), qui existait côté rendu mais n'était jamais peuplé avant
    # le 2026-08-02. Distinct de _interne_affinite : jamais préfixé _, car
    # factuel et public par conception (cf. config/criteres.yml).
    fiche["criteres_programme"] = sc["criteres_programme"]
    fiche["_interne_affinite"] = {
        "match": sc["bonus_profil_interne"] > 0,
        "signaux": sc["signaux_profil_interne"],
        "bonus_score": sc["bonus_profil_interne"],
    }

    # 6. Auto-promotion ?
    concepts = load_concepts()
    threshold = int(os.getenv("SCORE_THRESHOLD") or concepts.get("scoring", {}).get("threshold", 6))
    auto_cfg = concepts.get("scoring", {}).get("auto_promote", {})
    min_conf = float(auto_cfg.get("min_confidence", 0.85))

    auto_ok = (
        sc["hard_filter_pass"]
        and sc["score"] >= threshold
        and det["confidence"] >= min_conf
    )

    if not auto_ok:
        reasons = []
        if not sc["hard_filter_pass"]:
            reasons.append(f"hard_filter:{sc['hard_filter_reason']}")
        if sc["score"] < threshold:
            reasons.append(f"score {sc['score']} < {threshold}")
        if det["confidence"] < min_conf:
            reasons.append(f"conf {det['confidence']:.2f} < {min_conf}")
        print(f"      ↳ {det['type']:11s} score {sc['score']:2d} conf {det['confidence']:.2f} — rejet: {'; '.join(reasons)}")

    if auto_ok and not DRY_RUN:
        print(f"      ✓ PROMU — {det['type']} score {sc['score']} conf {det['confidence']:.2f}")
        # 7. Persistance + maj organisme
        slug = url_uid(url)
        type_id = fiche["type"]
        dest = APPELS_DIR / type_id / f"{slug}.yml"
        dest.write_text(
            yaml.safe_dump(fiche, allow_unicode=True, sort_keys=False, width=120),
            encoding="utf-8",
        )

        org_nom = (fiche.get("opportunite") or {}).get("organisme")
        if org_nom:
            org = organisme_manager.get_or_create(org_nom)
            organisme_manager.attach_opportunity(
                org["uid"], fiche["uid"], type_id, fiche["opportunite"]["nom"],
            )
            # Coordonnées de l'organisme extraites de l'appel
            od = fiche.get("organisme_details") or {}
            if od:
                organisme_manager.set_details(
                    org["uid"],
                    site_web=od.get("site_web"),
                    adresse=od.get("adresse"),
                    ville=od.get("ville"),
                    contact_email=od.get("contact_email"),
                )
            for p in fiche.get("partenaires", []) or []:
                if p and p != org_nom:
                    organisme_manager.record_partnership(org["uid"], p)

        # Log de promotion (auditable)
        log = {
            "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "url": url,
            "type": type_id,
            "score": sc["score"],
            "confidence": det["confidence"],
        }
        with (DISCOVERY_DIR / "promote-log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(log, ensure_ascii=False) + "\n")

    return {
        "url": url,
        "status": "promoted" if auto_ok else "below_threshold",
        "score": sc["score"],
        "type": det["type"],
        "confidence": det["confidence"],
        "dry_run": DRY_RUN,
    }


def main():
    config = load_config()
    sources = config.get("sources", []) or []
    run_start = _dt.datetime.now(_dt.timezone.utc)

    print(f"→ {len(sources)} source(s) à traiter (DRY_RUN={DRY_RUN})")
    print(f"✓ concepts.yml : {len(load_concepts().get('opportunity_types', []))} types")
    print()

    all_logs: list[dict] = []
    sources_stats: list[dict] = []

    # State throttle (chemin propre au fork — pas synopsis/ qui n'existe pas ici)
    throttle_state_path = ROOT / "discovery" / "throttle_state.json"
    throttle_state_path.parent.mkdir(parents=True, exist_ok=True)

    # Index des items déjà vus
    seen = load_seen()
    if not seen:
        n_boot = seen_bootstrap(seen)
        print(f"✓ seen_items.json initialisé depuis les fiches et rapports existants : {n_boot} item(s)")
        save_seen(seen)
    else:
        print(f"✓ seen_items.json : {len(seen)} item(s) déjà vus")
    print(f"✓ budget : {MAX_RUN_MINUTES} min, recheck {RECHECK_DAYS or 'jamais'}")
    print()
    n_seen_skipped = 0
    sources_not_reached: list[str] = []
    budget_hit = False

    # Semences manuelles (2026-11-18) : discovery/seeds.yml liste des URL
    # d'appels repérées hors pipeline (recherche par agents, suggestions). Elles
    # passent par process_item comme n'importe quel item — extraction Claude,
    # score, promotion — puis l'index des items vus les écarte aux runs suivants.
    # Format : items: [{url, title, context?}]. Traitées en tête, avant le budget.
    seeds_path = DISCOVERY_DIR / "seeds.yml"
    if seeds_path.exists():
        try:
            seeds = (yaml.safe_load(seeds_path.read_text(encoding="utf-8")) or {}).get("items") or []
        except Exception as e:
            print(f"⚠  seeds.yml illisible : {e}")
            seeds = []
        pending = [s for s in seeds if s.get("url") and not seen_should_skip(seen, s["url"])]
        if pending:
            sources = [{"label": "Semences manuelles (discovery/seeds.yml)", "_seed_items": pending,
                        "max_items_per_run": len(pending)}] + list(sources)
            print(f"✓ semences : {len(pending)} URL à traiter sur {len(seeds)}")

    for src in sources:
        label = src.get("label", src.get("url", "?"))
        elapsed_min = (_dt.datetime.now(_dt.timezone.utc) - run_start).total_seconds() / 60
        if budget_hit or elapsed_min >= MAX_RUN_MINUTES:
            if not budget_hit:
                print(f"⏱  Budget de {MAX_RUN_MINUTES} min atteint ({elapsed_min:.0f} min) — "
                      f"sources restantes reportées au prochain run")
                budget_hit = True
            sources_not_reached.append(label)
            continue
        print(f"━━ {label} ━━")

        # Throttle check (TTL + robots + cooldown erreurs)
        is_seed = "_seed_items" in src
        ok, reason = (True, "") if is_seed else throttle.should_fetch(src, state_path=throttle_state_path)
        if not ok:
            print(f"  ⏸  Throttle : {reason}")
            continue

        # Scrape via parser dispatcher (ou items fournis pour les semences)
        try:
            items = list(src["_seed_items"]) if is_seed else parser_dispatch(src)
        except Exception as e:
            print(f"  ✗ Scrape erreur : {e}")
            sources_stats.append({"label": label, "items": 0, "error": str(e)})
            throttle.record_fetch(src, success=False, doc_count=0, status_code=500, state_path=throttle_state_path)
            continue

        # Cap par source pour limiter le temps de run
        max_items_per_source = src.get("max_items_per_run", 20)
        if len(items) > max_items_per_source:
            print(f"  ↳ {len(items)} item(s) détecté(s) → cap à {max_items_per_source}")
            items = items[:max_items_per_source]
        else:
            print(f"  ↳ {len(items)} item(s) détecté(s)")

        n_promoted = 0
        n_new = 0
        today_iso = _dt.date.today().isoformat()
        for item in items:
            item_url = item.get("url") or ""
            skip_reason = seen_should_skip(seen, item_url) if item_url else None
            if skip_reason:
                n_seen_skipped += 1
                rec = seen.get(_norm_url(item_url))
                if rec is not None:
                    rec["last_seen"] = today_iso
                continue
            n_new += 1
            try:
                log = process_item(item, label)
            except Exception as e:
                print(f"    ✗ process_item erreur : {e}")
                if item_url:
                    seen[_norm_url(item_url)] = {"status": "error", "first_seen": today_iso,
                                                 "last_seen": today_iso, "error": str(e)[:120]}
                continue
            if log is None:
                continue
            all_logs.append(log)
            if item_url and not DRY_RUN:
                seen[_norm_url(item_url)] = {
                    "status": log.get("status", "?"), "first_seen": today_iso,
                    "last_seen": today_iso, "source": label,
                }
            if log.get("status") == "promoted":
                n_promoted += 1

        save_seen(seen)
        if not is_seed:
            throttle.record_fetch(src, success=True, doc_count=n_promoted, status_code=200, state_path=throttle_state_path)

        sources_stats.append({
            "label": label,
            "items": len(items),
            "new_items": n_new,
            "promoted": n_promoted,
        })
        print(f"  ✓ {n_promoted} promu(s) sur {n_new} nouveau(x) item(s) ({len(items)} détectés)")
        print()

    # Rapport de run
    run_end = _dt.datetime.now(_dt.timezone.utc)
    duration = (run_end - run_start).total_seconds()
    report = {
        "started_at": run_start.isoformat(),
        "ended_at": run_end.isoformat(),
        "duration_sec": duration,
        "dry_run": DRY_RUN,
        "claude_session_limit_hit": claude_guard.session_limit_active(),
        "n_sources": len(sources),
        "n_items_total": sum(s.get("items", 0) for s in sources_stats),
        "n_promoted_total": sum(s.get("promoted", 0) for s in sources_stats),
        "n_new_items": sum(s.get("new_items", 0) for s in sources_stats),
        "n_seen_skipped": n_seen_skipped,
        "budget_minutes": MAX_RUN_MINUTES,
        "budget_hit": budget_hit,
        "sources_not_reached": sources_not_reached,
        "sources_stats": sources_stats,
        "logs": all_logs,
    }
    save_seen(seen)

    reports_dir = ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"run_{run_start.strftime('%Y-%m-%d_%H-%M')}.json"
    if not DRY_RUN:
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print("─" * 50)
    if claude_guard.session_limit_active():
        print(f"⚠️  Limite de session Claude atteinte pendant ce run — "
              f"une partie des items n'a pas pu être traitée par Claude "
              f"(detect_type/extract/score/resume_fr en fallback). "
              f"Voir claude_session_limit_hit dans le rapport.")
    print(f"Total items détectés  : {report['n_items_total']}")
    print(f"  dont déjà vus (skip) : {n_seen_skipped}")
    print(f"  dont nouveaux        : {report['n_new_items']}")
    if budget_hit:
        print(f"⏱  Budget atteint — {len(sources_not_reached)} source(s) non traitée(s) ce run")
    print(f"Total fiches promues  : {report['n_promoted_total']}")
    print(f"Durée                 : {duration:.1f}s")
    if not DRY_RUN:
        print(f"Rapport               : {report_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

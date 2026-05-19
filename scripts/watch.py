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
     f. dedup.py → fusion ou nouvelle fiche
     g. organisme_manager → maj fiche organisme + track record
     h. auto-promotion si score ≥ threshold ET confidence ≥ 0.85

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
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

# Imports locaux (modules BIBLIO copiés + nouveaux scripts du fork)
from parsers import dispatch as parser_dispatch
import throttle
import dedup
import discovery_external_links

import detect_type
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


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def load_concepts() -> dict:
    return yaml.safe_load(CONCEPTS_PATH.read_text(encoding="utf-8"))


def url_uid(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:8]


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

    for src in sources:
        label = src.get("label", src.get("url", "?"))
        print(f"━━ {label} ━━")

        # Throttle check (TTL + robots + cooldown erreurs)
        ok, reason = throttle.should_fetch(src, state_path=throttle_state_path)
        if not ok:
            print(f"  ⏸  Throttle : {reason}")
            continue

        # Scrape via parser dispatcher
        try:
            items = parser_dispatch(src)
        except Exception as e:
            print(f"  ✗ Scrape erreur : {e}")
            sources_stats.append({"label": label, "items": 0, "error": str(e)})
            throttle.record_fetch(src, success=False, doc_count=0, status_code=500, state_path=throttle_state_path)
            continue

        print(f"  ↳ {len(items)} item(s) détecté(s)")

        n_promoted = 0
        for item in items:
            try:
                log = process_item(item, label)
            except Exception as e:
                print(f"    ✗ process_item erreur : {e}")
                continue
            if log is None:
                continue
            all_logs.append(log)
            if log.get("status") == "promoted":
                n_promoted += 1

        throttle.record_fetch(src, success=True, doc_count=n_promoted, status_code=200, state_path=throttle_state_path)

        sources_stats.append({
            "label": label,
            "items": len(items),
            "promoted": n_promoted,
        })
        print(f"  ✓ {n_promoted} promu(s) sur {len(items)} item(s)")
        print()

    # Rapport de run
    run_end = _dt.datetime.now(_dt.timezone.utc)
    duration = (run_end - run_start).total_seconds()
    report = {
        "started_at": run_start.isoformat(),
        "ended_at": run_end.isoformat(),
        "duration_sec": duration,
        "dry_run": DRY_RUN,
        "n_sources": len(sources),
        "n_items_total": sum(s.get("items", 0) for s in sources_stats),
        "n_promoted_total": sum(s.get("promoted", 0) for s in sources_stats),
        "sources_stats": sources_stats,
        "logs": all_logs,
    }

    reports_dir = ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"run_{run_start.strftime('%Y-%m-%d_%H-%M')}.json"
    if not DRY_RUN:
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print("─" * 50)
    print(f"Total items détectés  : {report['n_items_total']}")
    print(f"Total fiches promues  : {report['n_promoted_total']}")
    print(f"Durée                 : {duration:.1f}s")
    if not DRY_RUN:
        print(f"Rapport               : {report_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

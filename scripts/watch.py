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

    if auto_ok and not DRY_RUN:
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

    print(f"→ {len(sources)} source(s) à traiter (DRY_RUN={DRY_RUN})")

    # NOTE : la phase scrape (parser_dispatch + throttle) est désactivée tant que
    # bootstrap_copy.sh n'a pas copié les modules BIBLIO. Pour l'instant, watch.py
    # se contente de valider que la config charge et que les modules locaux
    # importent correctement.

    print("⚠  Phase scrape pas encore connectée — voir bootstrap_copy.sh.")
    print(f"✓ concepts.yml chargé ({len(load_concepts().get('opportunity_types', []))} types)")
    print(f"✓ {len(sources)} sources définies dans sources.yml")
    print(f"✓ modules locaux : detect_type, extract_opportunity, resume_fr, score_opportunity, organisme_manager")

    # Smoke test : on vérifie qu'on peut créer un organisme
    if not DRY_RUN:
        test_org = organisme_manager.get_or_create("Test Bootstrap", "FR")
        print(f"✓ Smoke test organisme : {test_org['uid']}")


if __name__ == "__main__":
    main()

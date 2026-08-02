#!/usr/bin/env python3
"""
rescore_existing.py — Re-score les fiches déjà promues dans appels/*.yml avec
le scoring courant (score_opportunity.score_fiche).

Contexte (2026-08-02) : deux changements viennent d'être apportés à
score_opportunity.py (barème criteres.yml branché + bug de fuite du bonus
profil interne corrigé ; filtre discipline resserré, leçon L8/L9). Les fiches
déjà publiées avant ces changements ont un `score` et un `criteres_programme`
calculés avec l'ancien code — cet écart ne se corrige jamais tout seul (les
fiches déjà promues ne repassent pas dans watch.py). Ce script réconcilie.

Portée volontairement limitée à appels/ (les fiches ACTIVES) :
- archive/ est exclu. Ces fiches sont expirées par construction
  (date_limite < aujourd'hui) — leur repasser dans hard_filters() renverrait
  systématiquement "date_limite passée" et écraserait à tort leur score
  historique, qui documente leur pertinence AU MOMENT où elles étaient
  ouvertes (cf. INSTRUCTION-DEMARRAGE.md §11 "Archivage des expirées").

Deux issues possibles par fiche :
  - hard_filter_pass=True  → score + criteres_programme + _interne_affinite
    mis à jour en place.
  - hard_filter_pass=False pour une raison AUTRE que "date_limite passée"
    (discipline incompatible, type non reconnu, fee sans dotation) → la
    fiche n'aurait plus dû être promue avec les règles actuelles. Déplacée
    vers discovery/quarantine/{type}/ (jamais supprimée, cf. convention leçon
    L1), avec la raison consignée dans _meta.quarantine_reason.
  - hard_filter_pass=False pour "date_limite passée" → IGNORÉE (relève de
    deadline_tracker.py, pas de ce script).

Écrit un rapport JSON dans reports/rescore_<date>.json.
"""

from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
APPELS_DIR = ROOT / "appels"
QUARANTINE_DIR = ROOT / "discovery" / "quarantine"
REPORTS_DIR = ROOT / "reports"
TYPES = ["residence", "bourse", "prix", "exposition"]

sys.path.insert(0, str(ROOT / "scripts"))
import score_opportunity


def main():
    now = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    today = _dt.date.today().isoformat()
    updated, quarantined, unchanged, errors = [], [], [], []

    for type_id in TYPES:
        d = APPELS_DIR / type_id
        if not d.exists():
            continue
        for path in sorted(d.glob("*.yml")):
            try:
                fiche = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception as e:
                errors.append({"path": str(path), "error": f"load: {e}"})
                continue

            try:
                sc = score_opportunity.score_fiche(fiche)
            except Exception as e:
                errors.append({"path": str(path), "error": f"score: {e}"})
                continue

            if not sc["hard_filter_pass"]:
                if sc["hard_filter_reason"] == "date_limite passée":
                    continue  # relève de deadline_tracker.py, pas ce script
                dest_dir = QUARANTINE_DIR / type_id
                dest_dir.mkdir(parents=True, exist_ok=True)
                fiche.setdefault("_meta", {})["quarantine_reason"] = sc["hard_filter_reason"]
                fiche["_meta"]["quarantined_at"] = now
                fiche["_meta"]["quarantined_by"] = "rescore_existing.py (resserrement filtre discipline, leçon L8)"
                (dest_dir / path.name).write_text(
                    yaml.safe_dump(fiche, allow_unicode=True, sort_keys=False, width=120),
                    encoding="utf-8",
                )
                path.unlink()
                quarantined.append({
                    "uid": fiche.get("uid"), "type": type_id,
                    "nom": (fiche.get("opportunite") or {}).get("nom"),
                    "raison": sc["hard_filter_reason"],
                })
                continue

            old_score = fiche.get("score")
            new_score = sc["score"]
            fiche["score"] = new_score
            fiche["criteres_programme"] = sc["criteres_programme"]
            fiche["_interne_affinite"] = {
                "match": sc["bonus_profil_interne"] > 0,
                "signaux": sc["signaux_profil_interne"],
                "bonus_score": sc["bonus_profil_interne"],
            }
            path.write_text(
                yaml.safe_dump(fiche, allow_unicode=True, sort_keys=False, width=120),
                encoding="utf-8",
            )
            entry = {
                "uid": fiche.get("uid"), "type": type_id,
                "nom": (fiche.get("opportunite") or {}).get("nom"),
                "old_score": old_score, "new_score": new_score,
            }
            if old_score != new_score:
                updated.append(entry)
            else:
                unchanged.append(entry)

    report = {
        "date": today,
        "n_updated": len(updated), "n_unchanged": len(unchanged),
        "n_quarantined": len(quarantined), "n_errors": len(errors),
        "updated": updated, "quarantined": quarantined, "errors": errors,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"rescore_{today}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"rescore_existing : {len(updated)} score(s) changé(s), "
          f"{len(unchanged)} inchangé(s), {len(quarantined)} mis en quarantaine, "
          f"{len(errors)} erreur(s). Rapport : {report_path.relative_to(ROOT)}")
    print("DONE")


if __name__ == "__main__":
    main()

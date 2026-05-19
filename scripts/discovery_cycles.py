#!/usr/bin/env python3
"""
discovery_cycles.py — Prédiction des prochaines éditions (§12.3/A).

À l'archivage d'une fiche expirée, on regarde si le nom contient un millésime
(2024, 2025, 2026…). Si oui :
  - on enregistre une prédiction dans discovery/cycles.yml
  - on calcule la fenêtre de surveillance pour l'édition suivante
  - on alimente le track_record de l'organisme

Idempotent.
"""

from __future__ import annotations

import datetime as _dt
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = ROOT / "archive"
CYCLES_PATH = ROOT / "discovery" / "cycles.yml"

sys.path.insert(0, str(ROOT / "scripts"))
import organisme_manager

YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _load_cycles() -> dict:
    if CYCLES_PATH.exists():
        return yaml.safe_load(CYCLES_PATH.read_text(encoding="utf-8")) or {"cycles": []}
    return {"cycles": []}


def _save_cycles(data: dict) -> None:
    CYCLES_PATH.parent.mkdir(parents=True, exist_ok=True)
    CYCLES_PATH.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )


def detect_millesime(nom: str) -> int | None:
    m = YEAR_RE.search(nom)
    return int(m.group(0)) if m else None


def predict_next_window(
    date_limite_iso: str, millesime: int
) -> tuple[str, str, str]:
    """Retourne (date_estimee_iso, debut_fenetre_iso, fin_fenetre_iso)."""
    try:
        ref = _dt.date.fromisoformat(date_limite_iso[:10])
    except Exception:
        ref = _dt.date.today()
    # Prochaine édition : même mois/jour, année +1 (heuristique simple)
    try:
        next_date = ref.replace(year=ref.year + 1)
    except ValueError:
        next_date = ref + _dt.timedelta(days=365)
    debut = next_date - _dt.timedelta(days=60)
    fin = next_date + _dt.timedelta(days=60)
    return next_date.isoformat(), debut.isoformat(), fin.isoformat()


def process_one(fiche: dict) -> dict | None:
    nom = (fiche.get("opportunite") or {}).get("nom") or ""
    organisme = (fiche.get("opportunite") or {}).get("organisme") or ""
    millesime = detect_millesime(nom)
    if not millesime or not organisme:
        return None

    date_lim = (fiche.get("candidature") or {}).get("date_limite")
    if not date_lim:
        return None

    estimee, debut, fin = predict_next_window(date_lim, millesime)
    fenetre_str = f"{debut} → {fin}"

    org = organisme_manager.get_or_create(organisme)
    organisme_manager.track_edition(
        org["uid"], fiche.get("type", "unknown"), str(millesime), fenetre_str,
    )

    return {
        "organisme_uid": org["uid"],
        "type": fiche.get("type"),
        "millesime_archive": millesime,
        "prochain_estimee": estimee,
        "fenetre_surveillance": fenetre_str,
        "url_a_surveiller": fiche.get("source_url"),
    }


def main():
    data = _load_cycles()
    cycles = data.setdefault("cycles", [])
    seen = {(c.get("organisme_uid"), c.get("type"), c.get("millesime_archive")) for c in cycles}
    n_new = 0

    for type_dir in ("residence", "bourse", "prix", "exposition"):
        d = ARCHIVE_DIR / type_dir
        if not d.exists():
            continue
        for p in sorted(d.glob("*.yml")):
            fiche = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            entry = process_one(fiche)
            if entry is None:
                continue
            key = (entry["organisme_uid"], entry["type"], entry["millesime_archive"])
            if key in seen:
                continue
            cycles.append(entry)
            seen.add(key)
            n_new += 1

    _save_cycles(data)
    print(f"discovery_cycles : {n_new} nouvelle(s) prédiction(s) enregistrée(s).")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
deadline_tracker.py — Tri des fiches par statut d'échéance.

Pour chaque fiche YAML dans appels/*/*.yml :
  - calcule le statut : ouverte | bientot-fermee (J-30) | expiree
  - si expirée : déplace la fiche vers archive/{type}/{slug}.yml
  - produit alertes/J-30.json, alertes/J-14.json, alertes/J-7.json
  - met à jour _meta.last_status_check

Exécution : cron quotidien dans le workflow GH Actions.
"""

from __future__ import annotations

import datetime as _dt
import json
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
APPELS_DIR = ROOT / "appels"
ARCHIVE_DIR = ROOT / "archive"
ALERTES_DIR = ROOT / "alertes"

OPPORTUNITY_TYPES = ["residence", "bourse", "prix", "exposition"]


def _today() -> _dt.date:
    return _dt.date.today()


def _parse_date(s: str | None) -> _dt.date | None:
    if not s:
        return None
    try:
        return _dt.date.fromisoformat(s[:10])
    except (TypeError, ValueError):
        return None


def compute_status(
    date_limite: _dt.date | None,
    today: _dt.date,
    candidature_continue: bool = False,
) -> str:
    """
    - candidature_continue=True + pas de date_limite → "ouverte-continue" :
      candidature réellement continue (autofinancée ou au fil de l'eau), pas
      une donnée manquante. Distinct de "indetermine" depuis 2026-08-02 (L3) :
      auparavant les deux cas étaient confondus, noyant les vraies opportunités
      ouvertes en continu dans le bruit des fiches à date manquante par erreur
      d'extraction. Voir lecons-Residences-artistiques.md.
    - Sinon, pas de date_limite → "indetermine" (donnée manquante, à corriger).
    """
    if date_limite is None:
        return "ouverte-continue" if candidature_continue else "indetermine"
    if date_limite < today:
        return "expiree"
    delta = (date_limite - today).days
    if delta <= 30:
        return "bientot-fermee"
    return "ouverte"


def list_fiches() -> list[Path]:
    fiches = []
    for type_id in OPPORTUNITY_TYPES:
        d = APPELS_DIR / type_id
        if d.exists():
            fiches.extend(sorted(d.glob("*.yml")))
    return fiches


def update_one(path: Path, today: _dt.date) -> dict:
    """Met à jour le status d'une fiche. Retourne {path, status, days_to_deadline}."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cand = data.get("candidature") or {}
    date_lim = _parse_date(cand.get("date_limite"))
    candidature_continue = bool(cand.get("candidature_continue"))
    new_status = compute_status(date_lim, today, candidature_continue)
    data["status"] = new_status
    data.setdefault("_meta", {})
    data["_meta"]["last_status_check"] = today.isoformat()
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    return {
        "path": str(path.relative_to(ROOT)),
        "status": new_status,
        "days_to_deadline": (date_lim - today).days if date_lim else None,
        "type": data.get("type"),
        "uid": data.get("uid"),
        "nom": (data.get("opportunite") or {}).get("nom"),
    }


def archive_expired(path: Path) -> None:
    type_id = path.parent.name
    dest_dir = ARCHIVE_DIR / type_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / path.name
    shutil.move(str(path), str(dest))


def build_alerts(records: list[dict]) -> dict[str, list[dict]]:
    alerts = {"J-30": [], "J-14": [], "J-7": []}
    for r in records:
        d = r.get("days_to_deadline")
        if d is None or d < 0:
            continue
        if d <= 7:
            alerts["J-7"].append(r)
        elif d <= 14:
            alerts["J-14"].append(r)
        elif d <= 30:
            alerts["J-30"].append(r)
    return alerts


def main():
    today = _today()
    ALERTES_DIR.mkdir(parents=True, exist_ok=True)

    records = []
    for fiche_path in list_fiches():
        rec = update_one(fiche_path, today)
        records.append(rec)
        if rec["status"] == "expiree":
            archive_expired(fiche_path)
            rec["archived"] = True

    alerts = build_alerts(records)
    for tag, items in alerts.items():
        (ALERTES_DIR / f"{tag}.json").write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    summary = {
        "date": today.isoformat(),
        "total": len(records),
        "ouvertes": sum(1 for r in records if r["status"] == "ouverte"),
        "bientot_fermees": sum(1 for r in records if r["status"] == "bientot-fermee"),
        "ouvertes_continues": sum(1 for r in records if r["status"] == "ouverte-continue"),
        "expirees_archivees": sum(1 for r in records if r.get("archived")),
        "indetermine": sum(1 for r in records if r["status"] == "indetermine"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

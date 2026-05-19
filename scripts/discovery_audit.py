#!/usr/bin/env python3
"""
discovery_audit.py — Garde-fou de l'auto-promotion (§12.5).

Rejoue les N dernières promotions (discovery/promote-log.jsonl) : refait
passer Claude sur la fiche correspondante et vérifie qu'on aurait fait la
même promotion aujourd'hui. Si drift détecté, écrit une alerte dans
discovery/audit-alerts.md.

Exécution : cron quotidien.
"""

from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PROMOTE_LOG = ROOT / "discovery" / "promote-log.jsonl"
ALERTS_PATH = ROOT / "discovery" / "audit-alerts.md"
APPELS_DIR = ROOT / "appels"

sys.path.insert(0, str(ROOT / "scripts"))
import detect_type
import score_opportunity

DEFAULT_N_AUDIT = 20


def _read_last_n(path: Path, n: int) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(l) for l in lines[-n:] if l.strip()]


def _find_fiche_by_url(url: str) -> Path | None:
    for type_dir in ("residence", "bourse", "prix", "exposition"):
        for p in (APPELS_DIR / type_dir).glob("*.yml"):
            try:
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            if data.get("source_url") == url:
                return p
    return None


def audit_one(log_entry: dict) -> dict:
    url = log_entry.get("url")
    fiche_path = _find_fiche_by_url(url) if url else None
    if not fiche_path:
        return {"url": url, "drift": False, "reason": "fiche introuvable (archivée ou supprimée)"}

    fiche = yaml.safe_load(fiche_path.read_text(encoding="utf-8")) or {}
    sc = score_opportunity.score_fiche(fiche)

    drift = (sc["score"] < int(log_entry.get("score", 0)) - 2) or (not sc["hard_filter_pass"])
    return {
        "url": url,
        "score_now": sc["score"],
        "score_log": log_entry.get("score"),
        "drift": drift,
        "reason": sc.get("hard_filter_reason") or "",
    }


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_N_AUDIT
    entries = _read_last_n(PROMOTE_LOG, n)
    if not entries:
        print("Aucune promotion à auditer.")
        return

    results = [audit_one(e) for e in entries]
    drifts = [r for r in results if r["drift"]]

    today = _dt.date.today().isoformat()
    lines = [f"# Audit auto-promotion — {today}", "", f"Échantillon : {len(results)} entrées."]
    if not drifts:
        lines.append("\n✓ Aucun drift détecté.")
    else:
        lines.append(f"\n⚠ {len(drifts)} drift(s) détecté(s) :\n")
        for d in drifts:
            lines.append(f"- {d['url']} — score logué {d['score_log']} → maintenant {d['score_now']} ({d['reason']})")

    ALERTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALERTS_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"audit : {len(drifts)} drift(s) sur {len(results)} — rapport dans {ALERTS_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

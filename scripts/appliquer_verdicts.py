#!/usr/bin/env python3
"""Applique les verdicts de la recherche par agents du 2026-11-18 aux fiches sans date.
Entrée : discovery/recherche-dates-2026-11-18/verdicts.json. Réversible : rien n'est supprimé
(quarantaine / archive), chaque fiche garde _meta.recherche_dates avec preuve."""
import json, sys, datetime, shutil
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parent.parent
V = json.load(open(ROOT / "discovery/recherche-dates-2026-11-18/verdicts.json", encoding="utf-8"))
today = datetime.date.today().isoformat()
by_uid = {}
for p in (ROOT / "appels").rglob("*.yml"):
    f = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    by_uid[f.get("uid")] = (p, f)
def save(p, f): p.write_text(yaml.safe_dump(f, allow_unicode=True, sort_keys=False, width=120), encoding="utf-8")
stats = {}
for v in V:
    uid = v["uid"]
    if uid not in by_uid: print("absent:", uid); continue
    p, f = by_uid[uid]
    verdict = v["verdict"]; conf = float(v.get("confiance") or 0)
    f.setdefault("_meta", {})["recherche_dates"] = {"at": today, "by": "agents de recherche (9 agents, 2 vagues)",
        "verdict": verdict, "confiance": conf, "preuve": v.get("preuve"), "notes": v.get("notes")}
    cand = f.setdefault("candidature", {}) or {}; f["candidature"] = cand
    if v.get("url_candidature") and not cand.get("url_candidature"): cand["url_candidature"] = v["url_candidature"]
    issue = verdict
    if verdict == "date_limite" and v.get("date_limite"):
        cand["date_limite"] = v["date_limite"]
        if v.get("date_limite_precision"): cand["date_limite_precision"] = v["date_limite_precision"]
        save(p, f)
    elif verdict == "candidature_continue" and conf >= 0.6:
        cand["candidature_continue"] = True; save(p, f)
    elif verdict == "prochaine_edition" and v.get("prochaine_edition"):
        cand["prochaine_edition"] = v["prochaine_edition"]; save(p, f)
    elif verdict == "pas_un_appel" and conf >= 0.7:
        f["_meta"]["quarantine_reason"] = "pas un appel à candidature (recherche agents 2026-11-18)"
        f["_meta"]["quarantined_at"] = today; f["_meta"]["quarantined_by"] = "appliquer_verdicts.py"
        dest = ROOT / "discovery/quarantine" / f.get("type", "autre") / p.name
        dest.parent.mkdir(parents=True, exist_ok=True); save(dest, f); p.unlink(); issue = "quarantaine"
    elif verdict == "expiree" and conf >= 0.7:
        f["status"] = "expiree"
        dest = ROOT / "archive" / f.get("type", "autre") / p.name
        dest.parent.mkdir(parents=True, exist_ok=True); save(dest, f); p.unlink(); issue = "archive"
    else:
        save(p, f); issue = f"{verdict} (inchangé)"
    stats[issue] = stats.get(issue, 0) + 1
    print(f"{uid} → {issue}")
print(json.dumps(stats, ensure_ascii=False))

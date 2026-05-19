#!/usr/bin/env python3
"""
enrich_organismes.py — Enrichissement Claude des fiches organismes incomplètes (§13.3).

Pour chaque fiche organisme avec description_courte, type_organisme ou
disciplines_proposees vides, demande à Claude une suggestion basée sur le
nom canonique + l'url canonique.

Exécution : cron mensuel.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ORGANISMES_DIR = ROOT / "organismes"

CLAUDE_TIMEOUT_SEC = 90
CLAUDE_MODEL = "claude-haiku-4-5"
CLAUDE_FLAGS = [
    "--output-format", "text",
    "--no-session-persistence",
    "--disable-slash-commands",
    "--tools", "",
    "--dangerously-skip-permissions",
]


def _call_claude(prompt: str) -> str:
    result = subprocess.run(
        ["claude", "-p", prompt, "--model", CLAUDE_MODEL] + CLAUDE_FLAGS,
        capture_output=True, text=True, timeout=CLAUDE_TIMEOUT_SEC,
        cwd="/tmp", stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude exit {result.returncode}")
    raw = result.stdout.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]
    return raw.strip()


def needs_enrichment(fiche: dict) -> bool:
    return (
        not fiche.get("description_courte")
        or not fiche.get("type_organisme")
        or not fiche.get("disciplines_proposees")
    )


def enrich(fiche: dict) -> dict:
    prompt = f"""Tu enrichis la fiche d'un organisme du milieu de l'art contemporain
ou des arts plastiques. Tu réponds uniquement en JSON, sans markdown.

Organisme : {fiche.get('nom_canonique')}
URL : {fiche.get('url_canonique') or 'non fournie'}
Pays : {fiche.get('pays') or 'non précisé'}

Champs à proposer :
- description_courte (1 phrase factuelle, ≤ 30 mots)
- type_organisme parmi : institution_publique, fondation, centre_art, ecole, reseau, autre
- disciplines_proposees : liste de 3-6 disciplines plastiques

Si tu ne connais pas l'organisme avec certitude, mets `null` partout.
Pas d'invention.

Réponds :
{{"description_courte": "...", "type_organisme": "...", "disciplines_proposees": [...]}}
"""
    try:
        raw = _call_claude(prompt)
        parsed = json.loads(raw)
        return parsed
    except Exception as e:
        return {"_error": str(e)}


def main():
    ORGANISMES_DIR.mkdir(parents=True, exist_ok=True)
    n_enriched = 0
    for f in sorted(ORGANISMES_DIR.glob("*.yml")):
        fiche = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        if not needs_enrichment(fiche):
            continue
        suggestions = enrich(fiche)
        if "_error" in suggestions:
            continue
        if suggestions.get("description_courte") and not fiche.get("description_courte"):
            fiche["description_courte"] = suggestions["description_courte"]
        if suggestions.get("type_organisme") and not fiche.get("type_organisme"):
            fiche["type_organisme"] = suggestions["type_organisme"]
        if suggestions.get("disciplines_proposees") and not fiche.get("disciplines_proposees"):
            fiche["disciplines_proposees"] = suggestions["disciplines_proposees"]
        f.write_text(
            yaml.safe_dump(fiche, allow_unicode=True, sort_keys=False, width=120),
            encoding="utf-8",
        )
        n_enriched += 1
    print(f"enrich_organismes : {n_enriched} fiche(s) enrichie(s).")


if __name__ == "__main__":
    main()

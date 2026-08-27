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
import claude_guard
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
    claude_guard.guard_before_call()
    result = subprocess.run(
        ["claude", "-p", prompt, "--model", CLAUDE_MODEL] + CLAUDE_FLAGS,
        capture_output=True, text=True, timeout=CLAUDE_TIMEOUT_SEC,
        cwd="/tmp", stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        claude_guard.check_result(result.stdout, result.stderr)
        raise RuntimeError(
            f"claude exit {result.returncode} — "
            f"stdout={result.stdout[:200]} stderr={result.stderr[:200]}"
        )
    raw = result.stdout.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]
    return raw.strip()


_ENRICH_FIELDS = [
    "description_courte", "type_organisme", "disciplines_proposees",
    "url_canonique", "adresse", "ville",
]


def needs_enrichment(fiche: dict) -> bool:
    return any(not fiche.get(k) for k in _ENRICH_FIELDS)


def enrich(fiche: dict) -> dict:
    prompt = f"""Tu enrichis la fiche d'un organisme du milieu de l'art contemporain
ou des arts plastiques. Tu réponds uniquement en JSON, sans markdown.

Organisme : {fiche.get('nom_canonique')}
URL connue : {fiche.get('url_canonique') or 'non fournie'}
Pays : {fiche.get('pays') or 'non précisé'}

Champs à proposer :
- description_courte (1 phrase factuelle, ≤ 30 mots)
- type_organisme parmi : institution_publique, fondation, centre_art, ecole, reseau, autre
- disciplines_proposees : liste de 3-6 disciplines plastiques
- url_canonique : URL du site officiel (https://…) UNIQUEMENT si tu la connais
  avec certitude. En cas de doute → null. N'invente JAMAIS une URL.
- adresse : adresse postale du siège si tu la connais avec certitude, sinon null
- ville : ville du siège si tu la connais avec certitude, sinon null

Si tu ne connais pas l'organisme avec certitude, mets `null` partout.
Pas d'invention — une URL ou une adresse inventée est une faute grave.

Réponds :
{{"description_courte": "...", "type_organisme": "...", "disciplines_proposees": [...],
  "url_canonique": "...", "adresse": "...", "ville": "..."}}
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
        changed = False
        for k in _ENRICH_FIELDS:
            val = suggestions.get(k)
            if val and not fiche.get(k):
                fiche[k] = val
                changed = True
        if not changed:
            continue
        f.write_text(
            yaml.safe_dump(fiche, allow_unicode=True, sort_keys=False, width=120),
            encoding="utf-8",
        )
        n_enriched += 1
    print(f"enrich_organismes : {n_enriched} fiche(s) enrichie(s).")


if __name__ == "__main__":
    main()

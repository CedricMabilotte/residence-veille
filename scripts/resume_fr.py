#!/usr/bin/env python3
"""
resume_fr.py — Traduction/résumé en français pour les sources EN/ES.

Usage :
  - Appelé par watch.py après détection de langue, AVANT extract_opportunity.
  - Produit deux choses :
      1. `resume_fr` : court résumé éditorial FR (3-5 phrases).
      2. `nom_fr`   : traduction du titre original.
  - Les chiffres (montants, dates, m²) sont CITÉS LITTÉRALEMENT — pas paraphrasés.
"""

from __future__ import annotations

import json
import subprocess
import claude_guard
import sys

CLAUDE_TIMEOUT_SEC = 90
CLAUDE_MODEL = "claude-haiku-4-5"
CLAUDE_FLAGS = [
    "--output-format", "text",
    "--no-session-persistence",
    "--disable-slash-commands",
    "--tools", "",
    "--dangerously-skip-permissions",
]


def _call_claude(prompt: str, timeout: int = CLAUDE_TIMEOUT_SEC) -> str:
    claude_guard.guard_before_call()
    result = subprocess.run(
        ["claude", "-p", prompt, "--model", CLAUDE_MODEL] + CLAUDE_FLAGS,
        capture_output=True, text=True, timeout=timeout,
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


def resume_fr(title: str, body: str, lang: str) -> dict:
    """Si lang == 'fr', retourne {nom_fr: title, resume_fr: None}. Sinon traduit."""
    if lang == "fr":
        return {"nom_fr": title, "resume_fr": None, "lang_source": "fr"}

    prompt = f"""Tu produis une traduction et un résumé court en français
d'une page web d'appel à candidature artistique. Langue source : {lang}.

CONSIGNES strictes :
- Le titre original reste tel quel ; tu produis sa traduction française.
- Le résumé fait 3 à 5 phrases courtes, factuelles, sans emphase.
- Tous les CHIFFRES (montants, dates, m², durées) sont cités LITTÉRALEMENT, jamais paraphrasés.
- Si une info n'est pas dans le texte, tu ne l'inventes pas.

Réponds en JSON :
{{"nom_fr": "...", "resume_fr": "..."}}

Titre : {title}

Texte source (premiers 4000 caractères) :
{body[:4000]}
"""
    try:
        raw = _call_claude(prompt)
        parsed = json.loads(raw)
        return {
            "nom_fr": parsed.get("nom_fr", title),
            "resume_fr": parsed.get("resume_fr"),
            "lang_source": lang,
        }
    except Exception as e:
        # Fallback : on garde le titre original, pas de résumé
        return {
            "nom_fr": title,
            "resume_fr": None,
            "lang_source": lang,
            "_error": str(e),
        }


def main():
    if len(sys.argv) < 4:
        print("Usage: resume_fr.py <title> <body> <lang>", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(
        resume_fr(sys.argv[1], sys.argv[2], sys.argv[3]),
        ensure_ascii=False, indent=2,
    ))


if __name__ == "__main__":
    main()

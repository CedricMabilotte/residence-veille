#!/usr/bin/env python3
"""
detect_type.py — Classifier une page d'appel en {residence | bourse | prix | exposition}.

Pipeline :
  1. Heuristique légère sur titre + texte (mots-clés multilingues).
  2. Si confidence < 0.7 → fallback Claude Haiku.
  3. Retourne {type, confidence, reasoning}.

Output (stdout JSON ou import direct via detect_type_for_url()).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

import yaml

CLAUDE_TIMEOUT_SEC = 60
CLAUDE_MODEL = "claude-haiku-4-5"
CLAUDE_FLAGS = [
    "--output-format", "text",
    "--no-session-persistence",
    "--disable-slash-commands",
    "--tools", "",
    "--dangerously-skip-permissions",
]

ROOT = Path(__file__).resolve().parent.parent
CONCEPTS_PATH = ROOT / "config" / "concepts.yml"

# ── Heuristique légère ──────────────────────────────────────────────────────
# Mots-clés multilingues (FR/EN/ES) qui signalent fortement un type.
TYPE_KEYWORDS = {
    "residence": {
        "fr": ["résidence", "résider", "accueil", "atelier sur place", "séjour de création"],
        "en": ["residency", "artist-in-residence", "air program", "live and work"],
        "es": ["residencia", "residente", "estancia de creación"],
    },
    "bourse": {
        "fr": ["bourse", "aide à la création", "aide individuelle", "allocation", "soutien financier"],
        "en": ["grant", "fellowship", "stipend", "funding award"],
        "es": ["beca", "ayuda económica", "subvención"],
    },
    "prix": {
        "fr": ["prix", "concours", "lauréat", "remise du prix", "jury"],
        "en": ["prize", "award", "competition", "winner", "jury"],
        "es": ["premio", "concurso", "certamen", "ganador"],
    },
    "exposition": {
        "fr": ["exposition", "appel à artistes", "appel à projets exposition", "biennale", "salon"],
        "en": ["exhibition", "call for artists", "open call exhibition", "biennale", "submissions"],
        "es": ["exposición", "convocatoria de exposición", "convocatoria artistas", "bienal"],
    },
}


def _call_claude(prompt: str, timeout: int = CLAUDE_TIMEOUT_SEC) -> str:
    result = subprocess.run(
        ["claude", "-p", prompt, "--model", CLAUDE_MODEL] + CLAUDE_FLAGS,
        capture_output=True, text=True, timeout=timeout,
        cwd="/tmp", stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"claude exit {result.returncode} — stderr={result.stderr[:200]}"
        )
    raw = result.stdout.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]
    return raw.strip()


def heuristic_score(text: str) -> dict[str, float]:
    """Retourne {type_id: score normalisé 0..1} basé sur la fréquence des mots-clés."""
    text_l = text.lower()
    counts: dict[str, int] = {}
    for type_id, langs in TYPE_KEYWORDS.items():
        n = 0
        for words in langs.values():
            for w in words:
                # \b ne marche pas avec espaces dans w ; on cherche substring simple
                n += text_l.count(w.lower())
        counts[type_id] = n
    total = sum(counts.values()) or 1
    return {k: v / total for k, v in counts.items()}


def detect_type(title: str, body_text: str, url: str = "") -> dict:
    """
    Classifie en {residence | bourse | prix | exposition}.
    Retourne {type, confidence (0..1), method, reasoning, scores}.
    """
    full_text = f"{title}\n\n{body_text}"
    scores = heuristic_score(full_text)

    top_type, top_score = max(scores.items(), key=lambda kv: kv[1])

    # Heuristique forte : top ≥ 0.7 ET marge ≥ 0.3 avec le 2e
    sorted_scores = sorted(scores.values(), reverse=True)
    margin = sorted_scores[0] - sorted_scores[1] if len(sorted_scores) > 1 else top_score

    if top_score >= 0.7 and margin >= 0.3:
        return {
            "type": top_type,
            "confidence": min(0.95, top_score),
            "method": "heuristic",
            "reasoning": f"Mots-clés '{top_type}' dominants ({top_score:.2f}, marge {margin:.2f}).",
            "scores": scores,
        }

    # Fallback Claude pour les cas ambigus
    prompt = f"""Tu classifies une page web d'appel à candidature artistique.

Types possibles (un seul) :
- residence : accueil physique d'un·e artiste sur un lieu, durée définie, atelier
- bourse : soutien financier sans accueil physique obligatoire (production, recherche, mobilité)
- prix : distinction compétitive avec dotation (argent, exposition, achat)
- exposition : appel à participer à une exposition (collective, biennale, festival)

URL : {url}
Titre : {title}

Extrait du contenu (premiers 1500 caractères) :
{body_text[:1500]}

Réponds en JSON :
{{"type": "residence|bourse|prix|exposition", "confidence": 0.0-1.0, "reasoning": "phrase brève citant le contenu"}}
"""
    try:
        raw = _call_claude(prompt)
        parsed = json.loads(raw)
        return {
            "type": parsed.get("type", "unknown"),
            "confidence": float(parsed.get("confidence", 0.5)),
            "method": "claude",
            "reasoning": parsed.get("reasoning", ""),
            "scores": scores,
        }
    except Exception as e:
        return {
            "type": top_type,
            "confidence": top_score,
            "method": "heuristic_fallback",
            "reasoning": f"Claude indisponible ({e}); heuristique conservée.",
            "scores": scores,
        }


def main():
    if len(sys.argv) < 3:
        print("Usage: detect_type.py <title> <body_text> [url]", file=sys.stderr)
        sys.exit(2)
    title = sys.argv[1]
    body = sys.argv[2]
    url = sys.argv[3] if len(sys.argv) > 3 else ""
    print(json.dumps(detect_type(title, body, url), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

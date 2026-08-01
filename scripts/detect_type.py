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


# ── Garde-fou anti-faux-positif ("candidature ouverte") ─────────────────────
# L1 (lecons-Residences-artistiques.md, 2026-08-01) : le crawl confond une page
# d'ANNUAIRE / BILAN (partenariats existants, alumni, expositions passées,
# actualités) avec un vrai APPEL À CANDIDATURE. Les mots-clés de domaine
# (TYPE_KEYWORDS ci-dessus) matchent aussi bien "résidence" dans "nos
# résidents 2024" que dans "candidatez à notre résidence" — ils ne suffisent
# pas à distinguer les deux. Ce garde-fou cherche un signal indépendant du
# domaine : la page invite-t-elle concrètement à déposer un dossier, avec une
# échéance à venir — ou ne fait-elle que raconter ce qui a déjà eu lieu ?
OPEN_CALL_VERBS = {
    "fr": ["candidatez", "postulez", "déposez votre dossier", "déposer votre candidature",
           "envoyez votre dossier", "soumettez votre projet", "inscrivez-vous",
           "appel à candidature", "appel à candidatures", "dossier de candidature"],
    "en": ["apply now", "submit your", "apply here", "how to apply", "application form",
           "call for entries", "call for applications", "open call", "submissions open"],
    "es": ["postúlate", "postule", "presenta tu candidatura", "envía tu propuesta",
           "convocatoria abierta", "cómo postular"],
}

DEADLINE_MARKERS = {
    "fr": ["date limite", "date butoir", "clôture des candidatures", "avant le",
           "jusqu'au", "dépôt des dossiers"],
    "en": ["deadline", "closing date", "applications close", "due by", "submit by"],
    "es": ["fecha límite", "plazo", "cierre de convocatoria"],
}

RETROSPECTIVE_MARKERS = {
    "fr": ["a eu lieu", "s'est tenue", "s'est déroulée", "édition précédente",
           "ont été accueilli", "ont accueilli", "était le lauréat", "les lauréats de",
           "nos résidents", "nos anciens résidents", "alumni", "en résidence depuis",
           "a été accueilli", "était en résidence", "n'est pas un appel à candidature",
           "n'est pas une candidature", "exposition programmée", "vernissage"],
    "en": ["took place", "was held", "previous edition", "were the winners",
           "past residents", "alumni", "hosted in", "in residence from",
           "not a call for", "not an open call"],
    "es": ["tuvo lugar", "se celebró", "edición anterior", "ex residentes"],
}

FUTURE_DATE_RE = re.compile(r"\b(20[2-9]\d)\b")

# Négations fréquentes juste avant un mot-clé — évite qu'une phrase comme
# « Ceci n'est PAS un appel à candidature » (négation explicite, vue dans les
# annotations Claude des fiches quarantainées) compte comme un signal positif.
_NEGATION_CUES = ("pas ", "pas d'", "pas de ", "n'est pas", "ne sont pas",
                  "aucun", "aucune", "non ", "sans ")


def _count_signal(text_l: str, bank: dict[str, list[str]], negation_window: int = 25) -> int:
    """Compte les occurrences des mots-clés de `bank`, en ignorant celles
    précédées de près par une négation."""
    n = 0
    for words in bank.values():
        for w in words:
            wl = w.lower()
            start = 0
            while True:
                idx = text_l.find(wl, start)
                if idx == -1:
                    break
                window = text_l[max(0, idx - negation_window):idx]
                if not any(cue in window for cue in _NEGATION_CUES):
                    n += 1
                start = idx + len(wl)
    return n


def open_call_signal(text: str, today_year: int = 2026) -> dict:
    """
    Mesure le signal "candidature ouverte" d'un texte, indépendamment des
    mots-clés de domaine. Retourne :
      score (0..1), has_verb, has_deadline_marker, has_future_date,
      retrospective_hits (compte brut, non plafonné).
    """
    text_l = text.lower()

    def _count(bank: dict[str, list[str]]) -> int:
        return sum(text_l.count(w.lower()) for words in bank.values() for w in words)

    verb_hits = _count_signal(text_l, OPEN_CALL_VERBS)
    deadline_hits = _count_signal(text_l, DEADLINE_MARKERS)
    retro_hits = _count(RETROSPECTIVE_MARKERS)
    future_years = [int(y) for y in FUTURE_DATE_RE.findall(text) if int(y) >= today_year]
    has_future_date = len(future_years) > 0

    raw = (
        (1.5 if verb_hits > 0 else 0.0)
        + (1.0 if deadline_hits > 0 else 0.0)
        + (0.5 if has_future_date else 0.0)
    )
    raw -= min(retro_hits, 3) * 0.7  # plafonné pour ne pas écraser le score sur un gros texte

    return {
        "score": round(max(0.0, min(1.0, raw / 3.0)), 2),
        "has_verb": verb_hits > 0,
        "has_deadline_marker": deadline_hits > 0,
        "has_future_date": has_future_date,
        "retrospective_hits": retro_hits,
    }


def _apply_open_call_guardrail(result: dict, full_text: str) -> dict:
    """
    Plafonne result["confidence"] si le signal "candidature ouverte" est
    faible — quelle que soit la méthode qui a produit la confidence d'origine
    (heuristique ou Claude) et quel que soit le score de mots-clés de domaine.
    Objectif concret : qu'une page d'annuaire de partenariats ou d'alumni ne
    puisse jamais franchir le seuil de passage/auto-promotion défini dans
    `config/concepts.yml` (scoring.auto_promote.min_confidence — actuellement
    0.70 en V0 exploratoire, cible 0.85 une fois calibré ; watch.py applique
    aussi un skip anticipé à 0.7), même truffée du mot "résidence". Les paliers
    ci-dessous sont volontairement fixés SOUS 0.70 dès que le signal n'est pas
    net, pour rester bloquants quel que soit lequel des deux seuils (actuel ou
    cible) est en vigueur — seul un signal fort (score ≥ 0.5, typiquement
    verbe d'appel + échéance ou date future) n'est pas plafonné.
    """
    signal = open_call_signal(full_text)
    original_conf = result["confidence"]

    if signal["retrospective_hits"] >= 2 and not signal["has_verb"]:
        # Cas L1 typique (annuaire de partenariats, alumni) : marqueurs
        # rétrospectifs répétés, aucun verbe d'appel. Plafond bas.
        capped = min(original_conf, 0.2)
    elif signal["score"] < 0.3:
        capped = min(original_conf, 0.5)   # sous 0.70 (actuel ET cible)
    elif signal["score"] < 0.5:
        capped = min(original_conf, 0.65)  # signal ambigu : sous 0.70, à instruire manuellement
    else:
        capped = original_conf

    if capped < original_conf:
        result["reasoning"] = (
            f"{result['reasoning']} | garde-fou candidature ouverte : "
            f"confidence {original_conf:.2f}→{capped:.2f} "
            f"(signal={signal['score']:.2f}, verbe={signal['has_verb']}, "
            f"rétro_hits={signal['retrospective_hits']})"
        )
        result["confidence"] = capped

    result["open_call_signal"] = signal
    return result


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
        result = {
            "type": top_type,
            "confidence": min(0.95, top_score),
            "method": "heuristic",
            "reasoning": f"Mots-clés '{top_type}' dominants ({top_score:.2f}, marge {margin:.2f}).",
            "scores": scores,
        }
        return _apply_open_call_guardrail(result, full_text)

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
        result = {
            "type": parsed.get("type", "unknown"),
            "confidence": float(parsed.get("confidence", 0.5)),
            "method": "claude",
            "reasoning": parsed.get("reasoning", ""),
            "scores": scores,
        }
        return _apply_open_call_guardrail(result, full_text)
    except Exception as e:
        result = {
            "type": top_type,
            "confidence": top_score,
            "method": "heuristic_fallback",
            "reasoning": f"Claude indisponible ({e}); heuristique conservée.",
            "scores": scores,
        }
        return _apply_open_call_guardrail(result, full_text)


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

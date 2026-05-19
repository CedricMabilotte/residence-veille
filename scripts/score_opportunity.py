#!/usr/bin/env python3
"""
score_opportunity.py — Scoring d'une fiche opportunité.

Applique les règles définies dans config/concepts.yml :
  - filtres durs (date expirée, discipline incompatible, anti-concept) → 0
  - score de base via Claude Haiku sur titre + opportunité + éligibilité
  - bonus profil interne (Leloup) — SILENCIEUX (champ _interne_affinite)
  - bonus track record organisme (≥ 3 éditions du même type)

Le scoreur ne modifie PAS la fiche en place : il retourne {score, breakdown}.
"""

from __future__ import annotations

import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import organisme_manager

CLAUDE_TIMEOUT_SEC = 60
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


def _parse_date(s: str | None) -> _dt.date | None:
    if not s:
        return None
    try:
        return _dt.date.fromisoformat(s[:10])
    except Exception:
        return None


def hard_filters(fiche: dict) -> tuple[bool, str]:
    """Retourne (passe, raison_si_filtré)."""
    cand = fiche.get("candidature") or {}
    elig = fiche.get("eligibilite") or {}

    date_lim = _parse_date(cand.get("date_limite"))
    if date_lim and date_lim < _dt.date.today():
        return False, "date_limite passée"

    if fiche.get("type") not in {"residence", "bourse", "prix", "exposition"}:
        return False, "type non reconnu"

    disciplines = [d.lower() for d in (elig.get("disciplines") or [])]
    if disciplines and not any(
        any(kw in d for kw in ("plastique", "visual", "installation", "sculpture",
                                "textile", "dessin", "photo", "peinture", "performance",
                                "vidéo", "video", "edition", "art"))
        for d in disciplines
    ):
        return False, "discipline incompatible"

    # Pay-to-play : fee élevé sans dotation
    fee = ((cand.get("frais_inscription") or {}).get("montant") or 0) or 0
    if fee and fee > 100:
        # tolérance si dotation explicite > 5x fee
        dotation = 0
        cb = fiche.get("conditions_bourse") or {}
        cp = fiche.get("conditions_prix") or {}
        if cb:
            dotation = ((cb.get("montant") or {}).get("montant") or 0)
        elif cp:
            dotation = (((cp.get("dotation") or {}).get("montant") or {}).get("montant") or 0)
        if not dotation or dotation < fee * 5:
            return False, f"fee {fee}€ sans dotation proportionnée"

    return True, ""


def profil_interne_bonus(fiche: dict) -> tuple[int, list[str]]:
    """Bonus +1 silencieux si signaux du profil interne détectés."""
    blob = json.dumps(fiche, ensure_ascii=False).lower()
    signaux_detectes = []
    signaux = {
        "rural": ["rural", "campagne", "campesino", "paysan", "village"],
        "textile": ["textile", "fibre", "tissu", "feutre", "wool", "laine", "lana"],
        "collectif": ["collectif", "collective", "colectivo", "communautaire", "community"],
        "matériaux locaux": ["matériaux locaux", "local materials", "materia local"],
        "long séjour": [],  # géré séparément si type=residence
    }
    for tag, kws in signaux.items():
        if any(kw in blob for kw in kws):
            signaux_detectes.append(tag)

    # Durée longue pour résidences
    if fiche.get("type") == "residence":
        duree = (fiche.get("conditions_residence") or {}).get("duree") or {}
        if (duree.get("semaines") or 0) >= 4:
            signaux_detectes.append("long séjour")

    bonus = 1 if len(signaux_detectes) >= 2 else 0
    return bonus, signaux_detectes


def claude_base_score(fiche: dict) -> tuple[int, str]:
    """Demande à Claude un score 0-10 sur la qualité/pertinence de la fiche."""
    nom = (fiche.get("opportunite") or {}).get("nom", "")
    org = (fiche.get("opportunite") or {}).get("organisme", "")
    type_id = fiche.get("type", "")
    disciplines = (fiche.get("eligibilite") or {}).get("disciplines", [])

    prompt = f"""Tu notes la pertinence d'une fiche d'opportunité pour plasticien·nes.

Type : {type_id}
Nom : {nom}
Organisme : {org}
Disciplines acceptées : {', '.join(disciplines) or 'non précisé'}

Échelle :
  9-10 : opportunité phare clairement ouverte aux plasticien·nes, conditions correctes
  7-8  : opportunité utile, conditions documentées
  5-6  : tangentielle (discipline acceptée mais pas centrale, infos partielles)
  0-4  : peu utile ou hors-sujet

Réponds en JSON : {{"score": 0-10, "raison": "phrase brève"}}
"""
    try:
        raw = _call_claude(prompt)
        parsed = json.loads(raw)
        return int(parsed.get("score", 5)), parsed.get("raison", "")
    except Exception:
        return 5, "Claude indisponible — score neutre par défaut"


def score_fiche(fiche: dict) -> dict:
    """
    Retourne un dict de scoring (NON merge avec la fiche, c'est watch.py qui décide).
    {
      score: int 0-10,
      base_score: int,
      base_reason: str,
      bonus_profil_interne: int,
      signaux_profil_interne: [str],
      bonus_track_record: int,
      hard_filter_pass: bool,
      hard_filter_reason: str,
    }
    """
    passe, raison = hard_filters(fiche)
    if not passe:
        return {
            "score": 0,
            "base_score": 0,
            "base_reason": raison,
            "bonus_profil_interne": 0,
            "signaux_profil_interne": [],
            "bonus_track_record": 0,
            "hard_filter_pass": False,
            "hard_filter_reason": raison,
        }

    base, raison_base = claude_base_score(fiche)
    bonus_interne, signaux = profil_interne_bonus(fiche)

    # Track record bonus
    organisme_uid = ((fiche.get("opportunite") or {}).get("organisme_uid")) or None
    track_bonus = 0
    if organisme_uid:
        track_bonus = organisme_manager.track_record_bonus(organisme_uid, fiche.get("type"))

    total = min(10, base + bonus_interne + track_bonus)
    return {
        "score": total,
        "base_score": base,
        "base_reason": raison_base,
        "bonus_profil_interne": bonus_interne,
        "signaux_profil_interne": signaux,
        "bonus_track_record": track_bonus,
        "hard_filter_pass": True,
        "hard_filter_reason": "",
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: score_opportunity.py <fiche.yml>", file=sys.stderr)
        sys.exit(2)
    fiche = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))
    result = score_fiche(fiche)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

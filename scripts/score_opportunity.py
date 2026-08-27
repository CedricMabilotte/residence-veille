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
import claude_guard
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import organisme_manager

CRITERES_PATH = ROOT / "config" / "criteres.yml"

CLAUDE_TIMEOUT_SEC = 60
CLAUDE_MODEL = "claude-haiku-4-5"
CLAUDE_FLAGS = [
    "--output-format", "text",
    "--no-session-persistence",
    "--disable-slash-commands",
    "--tools", "",
    "--dangerously-skip-permissions",
]

# Valeur numérique par statut de critère (barème config/criteres.yml).
STATUT_VALEUR = {"oui": 1.0, "partiel": 0.5, "non": 0.0, "inconnu": 0.0}

_BAREME_CACHE: dict | None = None


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
    # Resserré le 2026-08-02 (leçon L8) : le mot-clé générique "art" acceptait
    # à tort des disciplines non-pratique — ex. "critique d'art" (fiche
    # Bridges/AICA, réservée aux critiques membres AICA, pas aux plasticien·nes
    # praticien·nes) passait le filtre uniquement parce que "critique d'art"
    # contient la sous-chaîne "art". Retiré ; "plasticien" ajouté pour couvrir
    # les fiches qui disent "artiste plasticien·ne" sans dire "plastique".
    # Les disciplines de pratique (installation, sculpture, textile...)
    # continuent de matcher sur leurs mots-clés propres.
    if disciplines and not any(
        any(kw in d for kw in ("plastique", "plasticien", "visual", "installation",
                                "sculpture", "textile", "dessin", "photo", "peinture",
                                "performance", "vidéo", "video", "edition"))
        for d in disciplines
    ):
        return False, "discipline incompatible (pratique non-plastique, ex. critique/théorie/commissariat)"

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


def _load_bareme() -> dict:
    """Charge config/criteres.yml (caché en mémoire process)."""
    global _BAREME_CACHE
    if _BAREME_CACHE is None:
        if CRITERES_PATH.exists():
            _BAREME_CACHE = yaml.safe_load(CRITERES_PATH.read_text(encoding="utf-8")) or {}
        else:
            _BAREME_CACHE = {}
    return _BAREME_CACHE


def _fiche_public_view(fiche: dict) -> dict:
    """Fiche sans les champs internes (préfixés _) — c'est ce qu'on donne à
    Claude pour évaluer le barème public. Le barème ne doit jamais s'appuyer
    sur _interne_affinite (qui n'existe d'ailleurs qu'après scoring)."""
    return {k: v for k, v in fiche.items() if not k.startswith("_")}


def evaluate_bareme(fiche: dict, bareme: dict | None = None) -> tuple[float, list[dict]]:
    """
    Évalue la fiche contre config/criteres.yml : pour chaque critère des
    familles applicables au type de la fiche, demande à Claude un statut
    (oui/non/partiel/inconnu) + une citation justificative (un champ précis
    de la fiche, faute de texte source brut conservé — voir note dans
    INSTRUCTION-DEMARRAGE.md, "barème public qualifié plus finement").

    Retourne (qualite_criteres 0-2, criteres_programme) où criteres_programme
    est une liste plate [{"id", "rempli", "justification", "poids", "famille"}, ...]
    — c'est le schéma déjà attendu par generate_site.py::fiche_fields /
    render_fiche_item (champ `criteres_programme`, clés `id`/`rempli`/
    `justification`), qui existait déjà côté rendu avant que ce script ne le
    peuple jamais.
    """
    bareme = bareme if bareme is not None else _load_bareme()
    familles = (bareme.get("bareme") or {}).get("familles") or []
    type_id = fiche.get("type")

    applicables = [
        f for f in familles
        if not f.get("applicable_types") or type_id in f["applicable_types"]
    ]
    if not applicables:
        return 0.0, []

    criteres_flat = []
    for f in applicables:
        for c in f.get("criteres") or []:
            criteres_flat.append({**c, "_famille": f["id"]})

    if not criteres_flat:
        return 0.0, []

    liste_criteres = "\n".join(
        f'- id="{c["id"]}" (poids {c.get("poids", 1)}) : {c["label"]} — {c["definition"].strip()}'
        for c in criteres_flat
    )

    prompt = f"""Tu évalues une fiche d'opportunité pour plasticien·nes contre un barème
de critères factuels. Pour CHAQUE critère listé ci-dessous, donne un statut
parmi "oui" / "non" / "partiel" / "inconnu" (si l'information n'est pas
présente dans la fiche), et une citation courte (un champ + sa valeur dans la
fiche) qui justifie ce statut.

FICHE (JSON) :
{json.dumps(_fiche_public_view(fiche), ensure_ascii=False, indent=None)}

CRITÈRES À ÉVALUER :
{liste_criteres}

Réponds en JSON strict, un objet par id de critère :
{{"criteria": {{"<id>": {{"statut": "oui|non|partiel|inconnu", "citation": "..."}}}}}}
"""
    try:
        raw = _call_claude(prompt)
        parsed = json.loads(raw)
        resultats = parsed.get("criteria") or {}
    except Exception:
        resultats = {}  # fallback : tout "inconnu" ci-dessous

    criteres_programme: list[dict] = []
    poids_total = 0.0
    valeur_ponderee = 0.0
    for c in criteres_flat:
        cid = c["id"]
        r = resultats.get(cid) or {}
        statut = r.get("statut") if r.get("statut") in STATUT_VALEUR else "inconnu"
        citation = r.get("citation", "")
        poids = c.get("poids", 1)
        criteres_programme.append({
            "id": cid, "rempli": statut, "justification": citation,
            "poids": poids, "famille": c["_famille"],
        })
        poids_total += poids
        valeur_ponderee += poids * STATUT_VALEUR[statut]

    ratio = (valeur_ponderee / poids_total) if poids_total else 0.0
    qualite_criteres = round(ratio * 2, 2)  # échelle 0-2 (voir formule score_public)
    return qualite_criteres, criteres_programme


def claude_base_score(fiche: dict) -> tuple[int, str]:
    """Demande à Claude un score 0-7 (base_pertinence) sur la pertinence de la
    fiche. Échelle recalée le 2026-08-02 : le barème (evaluate_bareme ci-dessus)
    apporte désormais la composante "qualité" (0-2) séparément — cf.
    config/criteres.yml, score_public = base_pertinence (0-7) + qualite_criteres
    (0-2) + bonus_track_record (0-1)."""
    nom = (fiche.get("opportunite") or {}).get("nom", "")
    org = (fiche.get("opportunite") or {}).get("organisme", "")
    type_id = fiche.get("type", "")
    disciplines = (fiche.get("eligibilite") or {}).get("disciplines", [])

    prompt = f"""Tu notes la pertinence de base d'une fiche d'opportunité pour plasticien·nes
(hors qualité des conditions matérielles/administratives, évaluée séparément).

Type : {type_id}
Nom : {nom}
Organisme : {org}
Disciplines acceptées : {', '.join(disciplines) or 'non précisé'}

Échelle :
  6-7 : opportunité phare clairement ouverte aux plasticien·nes
  4-5 : opportunité utile, discipline centrale
  2-3 : tangentielle (discipline acceptée mais pas centrale, infos partielles)
  0-1 : peu utile ou hors-sujet

Réponds en JSON : {{"score": 0-7, "raison": "phrase brève"}}
"""
    try:
        raw = _call_claude(prompt)
        parsed = json.loads(raw)
        return int(parsed.get("score", 4)), parsed.get("raison", "")
    except Exception:
        return 4, "Claude indisponible — score neutre par défaut"


def score_fiche(fiche: dict) -> dict:
    """
    Retourne un dict de scoring (NON merge avec la fiche, c'est watch.py qui décide).
    {
      score: int 0-10,                    # score_public — AFFICHÉ, ne contient
                                           # jamais le bonus profil interne
      base_score: int,                    # 0-7, pertinence de base (Claude)
      base_reason: str,
      qualite_criteres: float,            # 0-2, dérivé du barème criteres.yml
      criteres_programme: list[dict],     # à écrire tel quel dans la fiche
                                           # (champ public "criteres_programme")
      bonus_profil_interne: int,          # informationnel — sert à remplir
                                           # _interne_affinite, JAMAIS sommé
                                           # dans "score" (corrigé 2026-08-02,
                                           # voir lecons-Residences-artistiques.md L9)
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
            "qualite_criteres": 0.0,
            "criteres_programme": [],
            "bonus_profil_interne": 0,
            "signaux_profil_interne": [],
            "bonus_track_record": 0,
            "hard_filter_pass": False,
            "hard_filter_reason": raison,
        }

    base, raison_base = claude_base_score(fiche)
    qualite_criteres, criteres_programme = evaluate_bareme(fiche)
    bonus_interne, signaux = profil_interne_bonus(fiche)

    # Track record bonus
    organisme_uid = ((fiche.get("opportunite") or {}).get("organisme_uid")) or None
    track_bonus = 0
    if organisme_uid:
        track_bonus = organisme_manager.track_record_bonus(organisme_uid, fiche.get("type"))

    # score_public = base_pertinence (0-7) + qualite_criteres (0-2)
    #              + bonus_track_record (0-1) — cf. config/criteres.yml.
    # Le bonus profil interne (silencieux, biais Leloup) N'ENTRE JAMAIS ici :
    # avant le 2026-08-02 il était ajouté à `total` par erreur, contredisant
    # la règle déjà écrite dans criteres.yml. Il reste disponible ci-dessous
    # pour alimenter le champ caché _interne_affinite uniquement.
    total = min(10, round(base + qualite_criteres + track_bonus))
    return {
        "score": total,
        "base_score": base,
        "base_reason": raison_base,
        "qualite_criteres": qualite_criteres,
        "criteres_programme": criteres_programme,
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

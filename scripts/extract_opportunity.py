#!/usr/bin/env python3
"""
extract_opportunity.py — Extraction structurée d'une fiche opportunité via Claude.

Prend en entrée :
  - title : titre de la page d'appel
  - body  : texte de la page (markdown ou texte brut)
  - url   : URL source
  - type  : déjà classifié (residence | bourse | prix | exposition)
  - lang  : langue détectée de la source (fr | en | es | autre)

Retourne un dict YAML-friendly conforme au schéma INSTRUCTION-DEMARRAGE.md §6.

Si lang ≠ fr → resume_fr.py est appelé en amont par watch.py pour produire
le résumé FR (le présent module n'effectue PAS la traduction).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

import yaml

CLAUDE_TIMEOUT_SEC = 180
CLAUDE_MODEL = "claude-haiku-4-5"
CLAUDE_FLAGS = [
    "--output-format", "text",
    "--no-session-persistence",
    "--disable-slash-commands",
    "--tools", "",
    "--dangerously-skip-permissions",
]

ROOT = Path(__file__).resolve().parent.parent
CRITERES_PATH = ROOT / "config" / "criteres.yml"


def _load_bareme() -> list[dict]:
    """Charge la liste à plat des critères du barème (config/criteres.yml)."""
    if not CRITERES_PATH.exists():
        return []
    data = yaml.safe_load(CRITERES_PATH.read_text(encoding="utf-8")) or {}
    criteres = []
    for famille in (data.get("bareme") or {}).get("familles", []):
        for c in famille.get("criteres", []):
            criteres.append({
                "id": c["id"],
                "label": c["label"],
                "definition": (c.get("definition") or "").strip(),
                "poids": c.get("poids", 1),
                "famille": famille.get("label", ""),
            })
    return criteres


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


def _uid(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:8]


# ── Prompts par type (le bloc spécifique change selon residence/bourse/prix/expo) ──

PROMPT_COMMON_HEADER = """Tu extrais les données structurées d'une page d'appel à candidature artistique.

Tu DOIS retourner UNIQUEMENT un objet JSON valide. Pas de markdown, pas de prose.

CONSIGNES STRICTES :
- **NOMS DE CHAMPS** : utilise EXACTEMENT les noms de champs du schéma ci-dessous,
  en français. JAMAIS de traduction : c'est `ville` (pas `ciudad`/`city`), `pays`
  (pas `pais`/`country`), `candidature` (pas `candidatura`/`application`),
  `langue_dossier`, `niveau_carriere`, `nationalite`, `disciplines`, etc.
- N'invente RIEN. Si une info n'est pas dans le texte, mets `null` (jamais "à confirmer", "non précisé").
- Pour `opportunite.nom` : prends le NOM COMPLET de l'opportunité tel qu'il apparaît
  dans le texte, pas juste le titre du PDF (par ex. "VI CONVOCATORIA DEL CENTRO DE
  RESIDENCIAS ARTÍSTICAS DE MATADERO MADRID" et non "BASES DE LA CONVOCATORIA").
- **DATE LIMITE** : recherche activement dans le texte des expressions comme
  "fecha límite", "deadline", "date limite", "plazo", "submissions close",
  "candidatures avant le", "before". Convertis en `YYYY-MM-DD`.
  Si la date n'apparaît REELLEMENT pas, mets `null` (sans inventer).
- Cite littéralement les chiffres (montants, dates, m²) sans les paraphraser.
- Si seul un mois est donné, prends le 1er du mois ; signale `date_limite_precision: "month"`.
- Devises : utilise les codes ISO (EUR, USD, GBP, etc.) majuscules.
- Si la page est en EN ou ES, garde le titre original dans `opportunite.nom`.
"""

PROMPT_SCHEMA_RESIDENCE = """
Schéma JSON à produire (type=residence) :

{
  "opportunite": {
    "nom": "...",
    "organisme": "...",
    "lieu": {"ville": "...", "pays": "...", "territoire": "..."}
  },
  "candidature": {
    "date_limite": "YYYY-MM-DD",
    "date_limite_precision": "day|month",
    "langue_dossier": ["fr", "en"],
    "frais_inscription": {"montant": 0, "devise": "EUR"},
    "pieces_demandees": ["..."],
    "url_candidature": "https://..."
  },
  "eligibilite": {
    "disciplines": ["..."],
    "niveau_carriere": "émergent·e|confirmé·e|tous",
    "age_max": null,
    "nationalite": "sans restriction|...",
    "residence_administrative": "sans restriction|..."
  },
  "conditions_residence": {
    "duree": {"semaines": null, "dates": "..."},
    "hebergement": true,
    "atelier": "...",
    "remuneration": {"montant": null, "devise": "EUR", "periodicite": "semaine|mois|forfait"},
    "voyage": {"pris_en_charge": false, "plafond": null, "devise": "EUR"},
    "restitution": "..."
  },
  "partenaires": ["organisme1", "organisme2"],
  "_meta": {
    "extracted_confidence": 0.0,
    "extracted_notes": "phrase brève sur la fiabilité"
  }
}
"""

PROMPT_SCHEMA_BOURSE = """
Schéma JSON à produire (type=bourse) :

{
  "opportunite": { "nom": "...", "organisme": "...", "lieu": {"ville": "...", "pays": "..."} },
  "candidature": { "date_limite": "YYYY-MM-DD", "langue_dossier": [...], "frais_inscription": {...}, "pieces_demandees": [...], "url_candidature": "..." },
  "eligibilite": { "disciplines": [...], "niveau_carriere": "...", "age_max": null, "nationalite": "...", "residence_administrative": "..." },
  "conditions_bourse": {
    "montant": {"montant": null, "devise": "EUR"},
    "finalite": "production|recherche|formation|mobilite",
    "calendrier_usage": "...",
    "obligations_rendu": ["..."]
  },
  "partenaires": [...],
  "_meta": { "extracted_confidence": 0.0, "extracted_notes": "..." }
}
"""

PROMPT_SCHEMA_PRIX = """
Schéma JSON à produire (type=prix) :

{
  "opportunite": { "nom": "...", "organisme": "...", "lieu": {"ville": "...", "pays": "..."} },
  "candidature": { "date_limite": "YYYY-MM-DD", "langue_dossier": [...], "frais_inscription": {...}, "pieces_demandees": [...], "url_candidature": "..." },
  "eligibilite": { "disciplines": [...], "niveau_carriere": "...", "age_max": null, "nationalite": "...", "residence_administrative": "..." },
  "conditions_prix": {
    "dotation": {
      "montant": {"montant": null, "devise": "EUR"},
      "exposition": false,
      "achat_oeuvre": false,
      "edition_catalogue": false
    },
    "jury_public": ["..."],
    "nb_laureats": 1,
    "editions_precedentes": ["..."]
  },
  "partenaires": [...],
  "_meta": { "extracted_confidence": 0.0, "extracted_notes": "..." }
}
"""

PROMPT_SCHEMA_EXPO = """
Schéma JSON à produire (type=exposition) :

{
  "opportunite": { "nom": "...", "organisme": "...", "lieu": {"ville": "...", "pays": "..."} },
  "candidature": { "date_limite": "YYYY-MM-DD", "langue_dossier": [...], "frais_inscription": {...}, "pieces_demandees": [...], "url_candidature": "..." },
  "eligibilite": { "disciplines": [...], "niveau_carriere": "...", "age_max": null, "nationalite": "...", "residence_administrative": "..." },
  "conditions_exposition": {
    "lieux": ["..."],
    "dates_exposition": "...",
    "format": "collective|personnelle|festival|biennale",
    "prise_en_charge": {
      "production": false,
      "transport": {"pris_en_charge": false, "plafond": null, "devise": "EUR"},
      "per_diem": false,
      "hebergement_vernissage": false
    }
  },
  "partenaires": [...],
  "_meta": { "extracted_confidence": 0.0, "extracted_notes": "..." }
}
"""

SCHEMAS = {
    "residence": PROMPT_SCHEMA_RESIDENCE,
    "bourse": PROMPT_SCHEMA_BOURSE,
    "prix": PROMPT_SCHEMA_PRIX,
    "exposition": PROMPT_SCHEMA_EXPO,
}


def _build_analyse_block(bareme: list[dict]) -> str:
    """Bloc de prompt : analyse rédigée + rubrique à savoir + lecture du barème."""
    criteres_lignes = "\n".join(
        f'    - id "{c["id"]}" — {c["label"]} : {c["definition"]}'
        for c in bareme
    )
    return f'''

EN PLUS du schéma ci-dessus, ajoute ces trois champs au MÊME niveau (racine du JSON) :

"analyse": {{
  "synthese": "3 à 5 phrases factuelles : ce que propose ce programme, à qui il
               s'adresse, ses conditions principales. Aucun jugement de valeur,
               aucune emphase. Cite les chiffres littéralement.",
  "pour_qui": "1 phrase : le profil d'artiste visé par ce programme."
}},

"a_savoir": [
  "Liste de signaux d'attention factuels, le cas échéant. Exemples : frais
   d'inscription élevés, première édition (organisme sans historique), dossier
   exigé dans une langue étrangère, durée très courte, restitution lourde
   attendue. Si rien à signaler, liste vide []."
],

"organisme_details": {{
  "site_web": "URL du site officiel de l'organisme porteur, si elle figure
               dans le texte (sinon null)",
  "adresse": "adresse postale de l'organisme si mentionnée (sinon null)",
  "ville": "ville de l'organisme si mentionnée (sinon null)",
  "contact_email": "email de contact si mentionné (sinon null)"
}},

"criteres_programme": [
  // Pour CHAQUE critère du barème ci-dessous, un objet :
  {{ "id": "<id du critère>", "rempli": "oui|non|partiel|inconnu",
     "justification": "courte citation ou paraphrase du texte source" }}
],

BARÈME (lis le programme contre chacun de ces critères) :
{criteres_lignes}
'''


_BAREME = _load_bareme()


def extract_opportunity(
    title: str,
    body: str,
    url: str,
    type_id: str,
    lang: str = "fr",
) -> dict:
    """Extrait la fiche structurée. Renvoie le dict prêt à dump en YAML."""
    if type_id not in SCHEMAS:
        raise ValueError(f"type_id inconnu : {type_id!r}")

    schema_prompt = SCHEMAS[type_id]
    analyse_block = _build_analyse_block(_BAREME) if _BAREME else ""
    prompt = (
        PROMPT_COMMON_HEADER
        + schema_prompt
        + analyse_block
        + f"\n\nURL source : {url}\nLangue détectée : {lang}\nTitre : {title}\n\nContenu :\n{body[:8000]}"
    )

    raw = _call_claude(prompt)
    data = json.loads(raw)

    # Compléter avec les champs uniformes
    fiche = {
        "uid": _uid(url),
        "type": type_id,
        "source_url": url,
        "fetched_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "score": None,            # sera rempli par score_opportunity.py
        "status": "ouverte",      # sera mis à jour par deadline_tracker.py
        **data,                   # opportunite, candidature, eligibilite, conditions_*, partenaires, _meta
    }
    fiche.setdefault("_meta", {})
    fiche["_meta"]["extracted_by"] = CLAUDE_MODEL
    fiche["_meta"]["extracted_at"] = fiche["fetched_at"]
    fiche["_meta"]["source_lang"] = lang

    return fiche


def main():
    if len(sys.argv) < 5:
        print(
            "Usage: extract_opportunity.py <title> <body> <url> <type> [lang]",
            file=sys.stderr,
        )
        sys.exit(2)
    fiche = extract_opportunity(
        sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4],
        sys.argv[5] if len(sys.argv) > 5 else "fr",
    )
    print(yaml.safe_dump(fiche, allow_unicode=True, sort_keys=False, width=120))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
organisme_manager.py — Gestion des fiches organismes (§13 de l'instruction).

Une fiche organisme = un index d'opportunités + un track record + un graphe
de partenariats. C'est la brique structurante pour :
  - la dédup inter-types
  - la prédiction des cycles annuels
  - le scoring de fiabilité (track record)
  - la veille "nouveaux entrants"

Stockage : organismes/{slug}.yml

API :
  - get_or_create(nom, pays?, url?) -> dict
  - attach_opportunity(organisme_uid, opp_uid, type, nom)
  - record_partnership(organisme_uid, partenaire_nom)
  - track_edition(organisme_uid, type, annee, fenetre?)
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import re
import sys
import unicodedata
from pathlib import Path
from typing import Optional

import yaml

ROOT = Path(__file__).resolve().parent.parent
ORGANISMES_DIR = ROOT / "organismes"

# ── Helpers ─────────────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    """Slug ASCII court, alphanumérique + tiret."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = nfkd.encode("ASCII", "ignore").decode("ASCII").lower()
    s = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    return s[:60] or "unknown"


def _uid(slug: str, pays: str | None = None) -> str:
    h = hashlib.md5(f"{slug}|{pays or ''}".encode()).hexdigest()[:8]
    return f"{slug}-{h}"


def _path_for(uid: str) -> Path:
    return ORGANISMES_DIR / f"{uid}.yml"


def _load(uid: str) -> Optional[dict]:
    p = _path_for(uid)
    if not p.exists():
        return None
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def _save(data: dict) -> None:
    ORGANISMES_DIR.mkdir(parents=True, exist_ok=True)
    p = _path_for(data["uid"])
    data.setdefault("_meta", {})
    data["_meta"]["last_updated"] = _dt.date.today().isoformat()
    p.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )


# ── API publique ────────────────────────────────────────────────────────────

def get_or_create(nom: str, pays: str | None = None, url: str | None = None) -> dict:
    """Récupère la fiche organisme par slug. Crée si absente."""
    slug = _slugify(nom)
    uid = _uid(slug, pays)
    existing = _load(uid)
    if existing:
        return existing

    today = _dt.date.today().isoformat()
    fiche = {
        "uid": uid,
        "nom_canonique": nom,
        "acronymes": [],
        "pays": pays,
        "type_organisme": None,
        "url_canonique": url,
        "urls_secondaires": [],
        "description_courte": None,
        "disciplines_proposees": [],
        "types_opportunites_habituels": [],
        "opportunites_liees": [],
        "track_record": {},
        "partenaires_mentionnes": [],
        "pages_surveillees": [],
        "_meta": {
            "first_seen": today,
            "last_updated": today,
            "status": "actif",
            "nouveaux_entrants": True,
        },
    }
    _save(fiche)
    return fiche


def attach_opportunity(
    organisme_uid: str,
    opp_uid: str,
    type_id: str,
    nom: str,
) -> None:
    """Ajoute une opportunité à l'index de l'organisme (dédup par opp_uid)."""
    fiche = _load(organisme_uid)
    if not fiche:
        return
    items = fiche.setdefault("opportunites_liees", [])
    if any(it.get("uid") == opp_uid for it in items):
        return
    items.append({"uid": opp_uid, "type": type_id, "nom": nom})
    habituels = fiche.setdefault("types_opportunites_habituels", [])
    if type_id not in habituels:
        habituels.append(type_id)
    _save(fiche)


def record_partnership(organisme_uid: str, partenaire_nom: str) -> None:
    """Incrémente le compteur de mentions d'un partenaire."""
    fiche = _load(organisme_uid)
    if not fiche:
        return
    partner_slug = _slugify(partenaire_nom)
    items = fiche.setdefault("partenaires_mentionnes", [])
    for it in items:
        if it.get("organisme_uid", "").startswith(partner_slug):
            it["occurrences"] = it.get("occurrences", 0) + 1
            _save(fiche)
            return
    items.append({"organisme_uid": partner_slug, "occurrences": 1, "nom_brut": partenaire_nom})
    _save(fiche)


def track_edition(
    organisme_uid: str,
    type_id: str,
    annee: str,
    fenetre: str | None = None,
) -> None:
    """Enregistre une édition pour calculer track_record + fiabilité de cycle."""
    fiche = _load(organisme_uid)
    if not fiche:
        return
    tr = fiche.setdefault("track_record", {})
    bucket = tr.setdefault(type_id, {"editions": [], "fiabilite_cycle": 0.0, "fenetre_annuelle": None})
    if annee not in bucket["editions"]:
        bucket["editions"].append(annee)
        bucket["editions"].sort()
    if fenetre:
        bucket["fenetre_annuelle"] = fenetre
    # Fiabilité simple : 0.5 à 1 édition, 0.7 à 2, 0.85 à 3, 0.95 à ≥ 4
    n = len(bucket["editions"])
    bucket["fiabilite_cycle"] = {1: 0.5, 2: 0.7, 3: 0.85}.get(n, 0.95 if n >= 4 else 0.5)
    _save(fiche)


def track_record_bonus(organisme_uid: str, type_id: str) -> int:
    """Retourne +1 si l'organisme a ≥ 3 éditions du même type, 0 sinon."""
    fiche = _load(organisme_uid)
    if not fiche:
        return 0
    tr = (fiche.get("track_record") or {}).get(type_id) or {}
    return 1 if len(tr.get("editions") or []) >= 3 else 0


def mark_status(organisme_uid: str, status: str) -> None:
    """status ∈ {actif, dormant, obsolete}"""
    fiche = _load(organisme_uid)
    if not fiche:
        return
    fiche.setdefault("_meta", {})["status"] = status
    _save(fiche)


# ── CLI utilitaire ──────────────────────────────────────────────────────────

def _cli():
    """Commandes de debug : list, show <uid>, create <nom> [pays]"""
    if len(sys.argv) < 2:
        print("Usage: organisme_manager.py {list|show <uid>|create <nom> [pays]}")
        sys.exit(2)
    cmd = sys.argv[1]
    if cmd == "list":
        ORGANISMES_DIR.mkdir(parents=True, exist_ok=True)
        for p in sorted(ORGANISMES_DIR.glob("*.yml")):
            d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            print(f"  {d.get('uid'):40s} {d.get('nom_canonique')}  ({d.get('pays')})")
    elif cmd == "show":
        d = _load(sys.argv[2])
        print(yaml.safe_dump(d, allow_unicode=True, sort_keys=False))
    elif cmd == "create":
        nom = sys.argv[2]
        pays = sys.argv[3] if len(sys.argv) > 3 else None
        d = get_or_create(nom, pays)
        print(f"Créé/trouvé : {d['uid']}")
    else:
        print(f"Commande inconnue : {cmd}")
        sys.exit(2)


if __name__ == "__main__":
    _cli()

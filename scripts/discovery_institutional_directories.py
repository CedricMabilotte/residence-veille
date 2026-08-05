#!/usr/bin/env python3
"""
discovery_institutional_directories.py — Crawl des annuaires institutionnels
et réseaux professionnels (§12.3/M).

Constat qui motive ce script : les mécanismes de découverte existants
(discovery_network_pages.py, discovery_partnerships.py, discovery_cycles.py...)
partent tous de sources ou d'organismes déjà connus. Aucun ne va chercher
activement en dessous du radar des gros agrégateurs internationaux — c'est
pourtant là que vivent les petites structures (centres d'art municipaux,
écoles d'art, associations régionales) qui n'apparaissent jamais sur e-flux
ou TransArtists.

Ce script lit discovery/annuaires.yml (liste éditable, vérifiée manuellement
— voir ce fichier pour la méthodologie), extrait les liens sortants de chaque
annuaire, filtre le bruit générique (réseaux sociaux, navigation) et les
domaines explicitement exclus par entrée, puis alimente
discovery/candidates.yml — la promotion en source suit ensuite la même
logique d'auto-promotion que les autres mécanismes (§12.5, discovery_audit.py).

Cadence : hebdomadaire (même step GH Actions que discovery_network_pages.py
et discovery_mastodon.py, gaté sur do_discovery_weekly).
"""

from __future__ import annotations

import datetime as _dt
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
ANNUAIRES_PATH = ROOT / "discovery" / "annuaires.yml"
CANDIDATES_PATH = ROOT / "discovery" / "candidates.yml"

HEADERS = {"User-Agent": "ResidenceBot/1.0 (mailto:cedric.mabilotte@gmail.com)"}
TIMEOUT = 20
DELAY = 1.0

LINK_RE = re.compile(r'href="(https?://[^"]+)"', re.IGNORECASE)

# Bruit générique à ignorer quel que soit l'annuaire : réseaux sociaux,
# outils de partage, CDN, et le domaine du ministère lui-même (déjà
# archi-couvert par sources.yml section K, pas la peine de le reproposer
# à chaque lien "voir aussi" d'une page gouvernementale).
DOMAINES_BRUIT = {
    "facebook.com", "www.facebook.com",
    "twitter.com", "x.com",
    "instagram.com", "www.instagram.com",
    "linkedin.com", "www.linkedin.com",
    "youtube.com", "www.youtube.com",
    "mastodon.social",
    "culture.gouv.fr", "www.culture.gouv.fr",
    "google.com", "www.google.com",
    "goo.gl", "bit.ly",
    # Boutons de partage — trouvés en test réel (2026-08-02) sur la page
    # UFISC : api.whatsapp.com/send?&text=... n'est pas un organisme, c'est
    # un lien de partage présent sur presque toutes les pages modernes.
    "api.whatsapp.com", "web.whatsapp.com", "wa.me",
    "t.me", "telegram.me",
    "pinterest.com", "www.pinterest.com",
    "reddit.com", "www.reddit.com",
    "tiktok.com", "www.tiktok.com",
    "bsky.app",
}


def _load_yaml(path: Path, default: dict) -> dict:
    if path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or default
    return default


def _load_candidates() -> dict:
    return _load_yaml(CANDIDATES_PATH, {"candidates": []})


def _save_candidates(data: dict) -> None:
    CANDIDATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    CANDIDATES_PATH.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )


def merge_candidate(data: dict, candidate: dict) -> bool:
    url = (candidate.get("url") or "").strip()
    if not url:
        return False
    for c in data.get("candidates", []):
        if c.get("url") == url:
            c["seen_count"] = (c.get("seen_count") or 1) + 1
            return False
    data.setdefault("candidates", []).append(candidate)
    return True


def extract_links(annuaire_url: str, domaine_exclu: list[str]) -> list[str]:
    """Récupère la page d'annuaire et retourne les domaines tiers distincts
    qu'elle référence (un lien par domaine, pas un par href)."""
    try:
        r = requests.get(annuaire_url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code != 200 or "text/html" not in r.headers.get("Content-Type", ""):
            return []
    except Exception:
        return []

    exclus = DOMAINES_BRUIT | {d.lower() for d in (domaine_exclu or [])}
    base_domain = urlparse(annuaire_url).netloc.lower()
    exclus.add(base_domain)

    vus: dict[str, str] = {}  # domaine -> première URL rencontrée
    for link in LINK_RE.findall(r.text):
        domain = urlparse(link).netloc.lower()
        if not domain or domain in exclus:
            continue
        vus.setdefault(domain, link)
    return list(vus.values())


def main():
    data = _load_yaml(ANNUAIRES_PATH, {"annuaires": []})
    annuaires = data.get("annuaires") or []
    if not annuaires:
        print("discovery_institutional_directories : aucune entrée dans discovery/annuaires.yml.")
        return

    cands = _load_candidates()
    now = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    n_added = 0

    for entry in annuaires:
        url = entry.get("url")
        label = entry.get("label", url)
        if not url:
            continue
        links = extract_links(url, entry.get("domaine_exclu") or [])
        print(f"  {label} → {len(links)} domaine(s) tiers repéré(s)")
        for link in links:
            cand = {
                "url": link,
                "type": "institutional_directory",
                "seen_count": 1,
                "found_from": {
                    "annuaire": label,
                    "annuaire_url": url,
                    "timestamp": now,
                },
            }
            if merge_candidate(cands, cand):
                n_added += 1
        time.sleep(DELAY)

    _save_candidates(cands)
    print(f"discovery_institutional_directories : {n_added} nouvelles URLs ajoutées aux candidats.")


if __name__ == "__main__":
    main()

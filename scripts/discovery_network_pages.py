#!/usr/bin/env python3
"""
discovery_network_pages.py — Crawl des pages "Réseau / Liens / Partenaires" (§12.3/C).

Pour chaque domaine d'organisme connu, on teste l'existence de pages
qui listent leurs pairs. Si trouvée, on extrait les domaines liés et on les
ajoute à discovery/candidates.yml.

Étendu le 2026-08-02 (recherche "petits réseaux") : en plus de partir des
organismes déjà validés dans organismes/*.yml, le script part aussi d'une
liste fixe de HUBS — des pages d'agrégateurs/fédérations qui listent PAR
NATURE des dizaines de petites structures (annuaire de membres), vérifiées
accessibles en session. Complémentaire de discovery_institutional_directories.py
(qui lit sa liste depuis discovery/annuaires.yml, éditable) : ici la liste est
courte et stable, codée en dur volontairement (les hubs des gros agrégateurs
changent rarement).
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
ORGANISMES_DIR = ROOT / "organismes"
CANDIDATES_PATH = ROOT / "discovery" / "candidates.yml"

# Mots à tester comme suffixes d'URL
NETWORK_PATHS = [
    "reseau", "réseau", "liens", "links", "partenaires", "partners",
    "network", "about/partners", "colaboradores", "asociados", "amigos",
    "credits", "soutiens", "support",
]

HEADERS = {"User-Agent": "ResidenceBot/1.0 (mailto:cedric.mabilotte@gmail.com)"}
TIMEOUT = 15
DELAY = 1.0

LINK_RE = re.compile(r'href="(https?://[^"]+)"', re.IGNORECASE)

# Bruit générique (boutons de partage, réseaux sociaux) — aligné avec
# discovery_institutional_directories.py suite au test réel du 2026-08-02
# (page UFISC : lien api.whatsapp.com/send capté à tort comme "organisme").
DOMAINES_BRUIT = {
    "facebook.com", "www.facebook.com",
    "twitter.com", "x.com",
    "instagram.com", "www.instagram.com",
    "linkedin.com", "www.linkedin.com",
    "youtube.com", "www.youtube.com",
    "mastodon.social",
    "google.com", "www.google.com",
    "goo.gl", "bit.ly",
    "api.whatsapp.com", "web.whatsapp.com", "wa.me",
    "t.me", "telegram.me",
    "pinterest.com", "www.pinterest.com",
    "reddit.com", "www.reddit.com",
    "tiktok.com", "www.tiktok.com",
    # Bruit CMS/thème (WordPress et cie) — trouvé en test réel sur Res Artis
    # /listings/, qui s'est avéré rendu en JS (résultats = credits de thème,
    # pas de membres réels). Filtré ici en attendant un fetch Playwright.
    "gmpg.org", "wordpress.org", "wp.com",
    "fonts.gstatic.com", "gstatic.com",
    "pixelgrade.com", "cookiedatabase.org",
    "jetpack.com", "gravatar.com", "automattic.com",
}

# Hubs vérifiés accessibles par recherche web le 2026-08-02 — ce sont déjà des
# pages d'annuaire de membres (pas besoin de tester des suffixes comme
# try_network_pages ci-dessous, l'URL est directement la bonne page).
#
# LIMITE CONSTATÉE EN TEST RÉEL (2026-08-02, fetch requests direct) : les deux
# hubs ci-dessous renvoient 0 lien membre exploitable en HTML statique — Res
# Artis /listings/ est rendu en JS (résultat = credits de thème WordPress),
# d.c.a /membres liste probablement les centres sans lien externe direct sur
# cette page agrégée (à vérifier page par page). Le mécanisme est correct et
# testé (cf. try_hub_links), mais ces deux entrées ont un rendement nul tant
# qu'elles ne sont pas migrées vers un fetch Playwright (comme e-flux dans
# sources.yml) — laissées en l'état comme point ouvert plutôt que masquées.
HUBS = [
    {
        "label": "Res Artis — Listings (annuaire des ~700 membres résidences)",
        "url": "https://resartis.org/listings/",
        "domaine_exclu": {"resartis.org"},
    },
    {
        "label": "d.c.a — membres (centres d'art contemporain, FR)",
        "url": "https://dca-art.com/les-centres-d-art-contemporain/membres",
        "domaine_exclu": {"dca-art.com", "www.dca-art.com"},
    },
]


def _load_candidates() -> dict:
    if CANDIDATES_PATH.exists():
        return yaml.safe_load(CANDIDATES_PATH.read_text(encoding="utf-8")) or {"candidates": []}
    return {"candidates": []}


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
    data["candidates"].append(candidate)
    return True


def try_network_pages(base_url: str) -> list[tuple[str, str]]:
    """Retourne [(network_page_url, found_link), ...] pour les pages réseau trouvées."""
    results = []
    for suffix in NETWORK_PATHS:
        candidate_url = urljoin(base_url.rstrip("/") + "/", suffix)
        try:
            r = requests.get(candidate_url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            if r.status_code != 200 or "text/html" not in r.headers.get("Content-Type", ""):
                continue
            links = LINK_RE.findall(r.text)
            base_domain = urlparse(base_url).netloc
            for link in links:
                link_domain = urlparse(link).netloc.lower()
                if link_domain and link_domain != base_domain and link_domain not in DOMAINES_BRUIT:
                    results.append((candidate_url, link))
        except Exception:
            continue
        time.sleep(DELAY)
    return results


def try_hub_links(hub: dict) -> list[str]:
    """Fetch direct d'une page hub (déjà une page d'annuaire), retourne les
    domaines tiers distincts qu'elle référence."""
    url = hub["url"]
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code != 200 or "text/html" not in r.headers.get("Content-Type", ""):
            return []
    except Exception:
        return []

    exclus = DOMAINES_BRUIT | set(hub.get("domaine_exclu") or set())
    vus: dict[str, str] = {}
    for link in LINK_RE.findall(r.text):
        domain = urlparse(link).netloc.lower()
        if not domain or domain in exclus:
            continue
        vus.setdefault(domain, link)
    return list(vus.values())


def main():
    ORGANISMES_DIR.mkdir(parents=True, exist_ok=True)
    data = _load_candidates()
    n_added = 0
    now = _dt.datetime.now().isoformat(timespec="seconds")

    for f in sorted(ORGANISMES_DIR.glob("*.yml")):
        d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        url = d.get("url_canonique")
        if not url:
            continue
        for net_page, found in try_network_pages(url):
            cand = {
                "url": found,
                "type": "network_page",
                "seen_count": 1,
                "found_from": {
                    "organisme_uid": d.get("uid"),
                    "page_reseau": net_page,
                    "timestamp": now,
                },
            }
            if merge_candidate(data, cand):
                n_added += 1

    for hub in HUBS:
        links = try_hub_links(hub)
        print(f"  hub {hub['label']} → {len(links)} domaine(s) tiers repéré(s)")
        for found in links:
            cand = {
                "url": found,
                "type": "network_hub",
                "seen_count": 1,
                "found_from": {
                    "hub": hub["label"],
                    "hub_url": hub["url"],
                    "timestamp": now,
                },
            }
            if merge_candidate(data, cand):
                n_added += 1
        time.sleep(DELAY)

    _save_candidates(data)
    print(f"discovery_network_pages : {n_added} nouvelles URLs ajoutées aux candidats.")


if __name__ == "__main__":
    main()

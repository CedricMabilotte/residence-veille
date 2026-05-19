#!/usr/bin/env python3
"""
discovery_network_pages.py — Crawl des pages "Réseau / Liens / Partenaires" (§12.3/C).

Pour chaque domaine d'organisme connu, on teste l'existence de pages
qui listent leurs pairs. Si trouvée, on extrait les domaines liés et on les
ajoute à discovery/candidates.yml.
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
                link_domain = urlparse(link).netloc
                if link_domain and link_domain != base_domain:
                    results.append((candidate_url, link))
        except Exception:
            continue
        time.sleep(DELAY)
    return results


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

    _save_candidates(data)
    print(f"discovery_network_pages : {n_added} nouvelles URLs ajoutées aux candidats.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
jsonld_event.py — Parser des balises Schema.org/Event embarquées dans le HTML.

Beaucoup de sites d'institutions publient leurs appels avec une balise
<script type="application/ld+json"> contenant un objet Event ou
Application/Application. On en extrait : name, startDate, endDate,
location, applicationDeadline, url, organizer.

Renvoyé sous une forme uniforme : liste de {url, title, text, context}.
"""

from __future__ import annotations

import json
import re
from typing import Iterable

JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


def _flatten(obj):
    """Yield tous les dicts dans un graphe JSON-LD (peut contenir @graph)."""
    if isinstance(obj, list):
        for item in obj:
            yield from _flatten(item)
    elif isinstance(obj, dict):
        graph = obj.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from _flatten(item)
        else:
            yield obj


def _is_opportunity_type(t) -> bool:
    if not t:
        return False
    if isinstance(t, list):
        return any(_is_opportunity_type(x) for x in t)
    s = str(t).lower()
    return any(k in s for k in ("event", "openingshours", "grant", "award", "competition", "exhibition", "creativework"))


def _extract_from_html(html: str, source_url: str) -> list[dict]:
    """Cœur du parser : extrait les items Event/Grant/Award du HTML JSON-LD."""
    items = []
    for match in JSONLD_RE.findall(html):
        try:
            data = json.loads(match)
        except json.JSONDecodeError:
            continue
        for obj in _flatten(data):
            if not _is_opportunity_type(obj.get("@type")):
                continue
            name = obj.get("name") or ""
            description = obj.get("description") or ""
            url = obj.get("url") or source_url
            organizer = obj.get("organizer")
            org_name = (
                organizer.get("name") if isinstance(organizer, dict) else (organizer or "")
            )
            deadline = (
                obj.get("applicationDeadline")
                or obj.get("startDate")
                or obj.get("validFrom")
                or ""
            )
            location = obj.get("location")
            loc_str = ""
            if isinstance(location, dict):
                loc_str = location.get("name") or ""
                addr = location.get("address") or {}
                if isinstance(addr, dict):
                    loc_str = f"{loc_str} {addr.get('addressLocality', '')} {addr.get('addressCountry', '')}".strip()

            context_lines = [
                f"Organisateur : {org_name}",
                f"Date limite / début : {deadline}",
                f"Lieu : {loc_str}",
                description,
            ]
            items.append({
                "url": url,
                "title": name,
                "text": "\n".join(c for c in context_lines if c),
                "context": description[:300],
                "extension": "jsonld",
                "link_text": name,
                "source_url": source_url,
                "page_title": name,
                "filename": (url.rsplit("/", 1)[-1] or "event")[:120],
            })
    return items


def find_documents(source: dict) -> list[dict]:
    """API conforme aux autres parsers : prend un dict source, fetch + parse."""
    import requests

    url = source.get("url")
    if not url:
        return []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ResidenceBot/1.0)"}
    try:
        r = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
        r.raise_for_status()
    except Exception as e:
        print(f"  ⚠  jsonld_event fetch échoué pour {url} : {e}")
        return []
    return _extract_from_html(r.text, url)

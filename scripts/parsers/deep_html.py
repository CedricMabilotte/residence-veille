#!/usr/bin/env python3
"""
deep_html.py — Parser HTML d'index/listing.

Depuis le refactor « zéro PDF » : ce parser n'effectue plus de crawl
2-niveaux à la recherche de fichiers. Une page-détail (l'annonce) EST
désormais l'item — on renvoie donc directement les liens vers ces pages,
et c'est `process_item` (watch.py) qui ira lire chaque page.

`deep_html` et `html` partagent la même logique d'extraction de liens
(module `_listing`). Le type `deep_html` est conservé pour compatibilité
avec config/sources.yml ; il accepte `max_pages` comme plafond de liens.
"""

from . import _listing


def find_documents(source: dict) -> list[dict]:
    base_url = source["url"]
    max_items = int(source.get("max_pages",
                               source.get("max_items_per_run",
                                          _listing.DEFAULT_MAX_ITEMS)))
    same_domain = not bool(source.get("allow_external"))

    html = _listing.fetch_html(base_url, timeout=int(source.get("timeout", 25)))
    if not html:
        return []

    items = _listing.extract_listing_items(
        html, base_url, max_items=max_items, same_domain_only=same_domain,
    )
    print(f"  ↳ deep_html : {len(items)} annonce(s) repérée(s)")
    return items


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://resartis.org/listings/"
    docs = find_documents({"url": url, "label": "Test", "max_pages": 20})
    print(f"→ {len(docs)} items")
    for d in docs[:8]:
        print(f"  - {d['title'][:70]}  {d['url']}")

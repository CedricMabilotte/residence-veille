#!/usr/bin/env python3
"""
html_static.py — Parser HTML statique.

Depuis le refactor « zéro PDF » : on ne cherche plus de fichiers
téléchargeables mais les **liens vers les pages d'annonce** (appels,
résidences, prix, expositions) présents sur une page d'index.

Fetch via requests (pas de rendu JS — voir playwright_parser pour ça).
"""

from . import _listing


def find_documents(source: dict) -> list[dict]:
    base_url = source["url"]
    max_items = int(source.get("max_pages",
                               source.get("max_items_per_run",
                                          _listing.DEFAULT_MAX_ITEMS)))
    same_domain = not bool(source.get("allow_external"))

    html = _listing.fetch_html(base_url, timeout=int(source.get("timeout", 20)))
    if not html:
        return []

    items = _listing.extract_listing_items(
        html, base_url, max_items=max_items, same_domain_only=same_domain,
    )
    print(f"  ↳ html : {len(items)} annonce(s) repérée(s)")
    return items


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.pollen-monflanquin.com/residences/"
    docs = find_documents({"url": url, "label": "Test"})
    print(f"→ {len(docs)} items")
    for d in docs[:8]:
        print(f"  - {d['title'][:70]}  {d['url']}")

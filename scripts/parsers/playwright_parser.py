#!/usr/bin/env python3
"""
playwright_parser.py — Parser pour les sites rendus en JavaScript.

Utilise Playwright (Chromium headless) pour exécuter le JS de la page, puis
extrait les **liens vers les pages d'annonce** via le module `_listing`
(même logique que html / deep_html).

Depuis le refactor « zéro PDF » : on ne cherche plus de fichiers
téléchargeables — une page-détail EST l'item.

Options dans config/sources.yml :
    - label: "e-flux — Announcements"
      url: "https://www.e-flux.com/announcements/"
      type: playwright
      wait_selector: "article"   # optionnel — attend ce sélecteur
      timeout_ms: 25000          # optionnel — timeout par page
      max_pages: 40              # optionnel — plafond de liens
"""

from __future__ import annotations

from . import _listing

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

DEFAULT_TIMEOUT = 25_000


def find_documents(source: dict) -> list[dict]:
    if not PLAYWRIGHT_AVAILABLE:
        print("  ⚠  Playwright non installé "
              "(pip install playwright && playwright install chromium)")
        return []

    base_url      = source["url"]
    label         = source.get("label", base_url)
    max_items     = int(source.get("max_pages",
                                   source.get("max_items_per_run",
                                              _listing.DEFAULT_MAX_ITEMS)))
    timeout_ms    = int(source.get("timeout_ms", DEFAULT_TIMEOUT))
    wait_selector = source.get("wait_selector")
    same_domain   = not bool(source.get("allow_external"))

    html = ""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            context = browser.new_context(user_agent=_listing.BROWSER_UA)
            page = context.new_page()
            try:
                page.goto(base_url, wait_until="domcontentloaded",
                          timeout=timeout_ms)
                if wait_selector:
                    try:
                        page.wait_for_selector(wait_selector, timeout=timeout_ms)
                    except Exception:
                        pass  # sélecteur facultatif
                page.wait_for_timeout(1800)  # laisse le JS lazy-loader peupler
                html = page.content()
            except Exception as e:
                print(f"  ⚠  playwright : échec sur {base_url} : {e}")
            finally:
                page.close()
        finally:
            browser.close()

    if not html:
        return []

    items = _listing.extract_listing_items(
        html, base_url, max_items=max_items, same_domain_only=same_domain,
    )
    print(f"  ↳ playwright : {len(items)} annonce(s) repérée(s) sur {label}")
    return items


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.e-flux.com/announcements/"
    docs = find_documents({"url": url, "label": "Test"})
    print(f"→ {len(docs)} items")
    for d in docs[:8]:
        print(f"  - {d['title'][:70]}  {d['url']}")

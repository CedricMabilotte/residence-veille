#!/usr/bin/env python3
"""
playwright_parser.py — Parser pour les sites JS-rendered.

Utilise Playwright (Chromium headless) pour exécuter le JS de la page, puis
extrait les liens vers PDF/EPUB/etc. à partir du DOM final.

Mode crawl 2-niveaux supporté via source["max_pages"] (suit les liens
internes 1 niveau de profondeur, comme deep_html).

Configuration dans config/sources.yml :
    - label: "Via Campesina FR"
      url: "https://viacampesina.org/fr/"
      type: playwright
      max_pages: 0       # 0 = pas de crawl, juste la page d'index
      wait_selector: "article"  # optionnel — attend qu'un sélecteur apparaisse
      timeout_ms: 20000  # optionnel — timeout par page (défaut : 25s)
"""

from pathlib import Path
from urllib.parse import urljoin, urlparse

# L'import playwright est lazy : ce module charge même si playwright n'est
# pas installé, on échoue au premier appel à find_documents()
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


DOC_EXTENSIONS = {".pdf", ".epub", ".txt", ".doc", ".docx"}
DEFAULT_TIMEOUT = 25_000
DEFAULT_MAX_PAGES = 0  # par défaut : pas de crawl 2-niveaux (coûteux)


def _extract_doc_links(html: str, base_url: str) -> list[tuple[str, str, str]]:
    """Liste les <a href> pointant vers un fichier doc. Retourne (url, text, context)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    seen, results = set(), []
    for a in soup.find_all("a", href=True):
        full_url = urljoin(base_url, a["href"])
        ext = Path(urlparse(full_url).path).suffix.lower()
        if ext not in DOC_EXTENSIONS or full_url in seen:
            continue
        seen.add(full_url)

        link_text = a.get_text(strip=True) or Path(urlparse(full_url).path).name
        parent    = a.find_parent(["p", "li", "div", "td", "article"])
        context   = parent.get_text(" ", strip=True)[:400] if parent else link_text
        results.append((full_url, link_text, context))
    return results


def _find_internal_links(html: str, base_url: str, max_count: int) -> list[str]:
    """Récupère jusqu'à max_count liens internes (même domaine, pas docs)."""
    from bs4 import BeautifulSoup
    soup    = BeautifulSoup(html, "html.parser")
    domain  = urlparse(base_url).netloc.lower()
    links, seen = [], set()
    for a in soup.find_all("a", href=True):
        full_url = urljoin(base_url, a["href"]).split("#")[0]
        if not full_url.startswith(("http://", "https://")):
            continue
        if urlparse(full_url).netloc.lower() != domain:
            continue
        ext = Path(urlparse(full_url).path).suffix.lower()
        if ext in DOC_EXTENSIONS:
            continue
        if full_url == base_url or full_url in seen:
            continue
        seen.add(full_url)
        links.append(full_url)
        if len(links) >= max_count:
            break
    return links


def find_documents(source: dict) -> list[dict]:
    if not PLAYWRIGHT_AVAILABLE:
        print("  ⚠  Playwright n'est pas installé. "
              "Installer : pip install playwright && playwright install chromium")
        return []

    base_url      = source["url"]
    label         = source.get("label", base_url)
    max_pages     = int(source.get("max_pages", DEFAULT_MAX_PAGES))
    timeout_ms    = int(source.get("timeout_ms", DEFAULT_TIMEOUT))
    wait_selector = source.get("wait_selector")

    docs_seen: set[str] = set()
    all_docs: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True,
                                     args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            context = browser.new_context(
                user_agent="Mozilla/5.0 (compatible; LibraryBot/1.0)"
            )

            def _scrape_page(url: str, is_index: bool) -> tuple[str, str]:
                """Retourne (html, page_title) ou ('','') sur erreur."""
                page = context.new_page()
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    if wait_selector:
                        try:
                            page.wait_for_selector(wait_selector, timeout=timeout_ms)
                        except Exception:
                            pass  # selector facultatif
                    # petit délai pour laisser le JS lazy-loader peupler le DOM
                    page.wait_for_timeout(1500)
                    return page.content(), page.title() or urlparse(url).netloc
                except Exception as e:
                    print(f"  ⚠  playwright : échec sur {url} : {e}")
                    return "", ""
                finally:
                    page.close()

            # Niveau 1 : page d'index
            html, page_title = _scrape_page(base_url, is_index=True)
            if not html:
                return []

            for full_url, link_text, context_ in _extract_doc_links(html, base_url):
                if full_url in docs_seen:
                    continue
                docs_seen.add(full_url)
                ext = Path(urlparse(full_url).path).suffix.lower().lstrip(".")
                all_docs.append({
                    "url":        full_url,
                    "filename":   Path(urlparse(full_url).path).name or "document",
                    "extension":  ext,
                    "link_text":  link_text,
                    "context":    context_,
                    "page_title": page_title,
                    "source_url": base_url,
                })

            # Niveau 2 (optionnel)
            if max_pages > 0:
                article_links = _find_internal_links(html, base_url, max_pages)
                print(f"  ↳ playwright : crawl de {len(article_links)} sous-pages "
                      f"depuis {label}")
                for url in article_links:
                    html_sub, _ = _scrape_page(url, is_index=False)
                    if not html_sub:
                        continue
                    for full_url, link_text, context_ in _extract_doc_links(html_sub, url):
                        if full_url in docs_seen:
                            continue
                        docs_seen.add(full_url)
                        ext = Path(urlparse(full_url).path).suffix.lower().lstrip(".")
                        all_docs.append({
                            "url":        full_url,
                            "filename":   Path(urlparse(full_url).path).name or "document",
                            "extension":  ext,
                            "link_text":  link_text,
                            "context":    context_,
                            "page_title": page_title,
                            "source_url": base_url,
                        })

        finally:
            browser.close()

    print(f"  ↳ playwright : {len(all_docs)} docs total")
    return all_docs


if __name__ == "__main__":
    import sys
    test = {
        "url":        "https://viacampesina.org/fr/",
        "label":      "Via Campesina FR",
        "max_pages":  5,
        "timeout_ms": 30000,
    }
    print(f"=== Test playwright sur {test['label']} ===")
    docs = find_documents(test)
    print(f"\n→ {len(docs)} docs")
    for d in docs[:5]:
        print(f"  - {d['filename']}  ({d['url']})")

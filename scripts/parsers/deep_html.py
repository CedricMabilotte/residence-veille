#!/usr/bin/env python3
"""
deep_html.py — Parser crawl 2-niveaux.

Beaucoup de sites (libcom, crimethinc, sproutdistro, cras31, federation-anarchiste,
portaloaca) listent leurs articles depuis une page d'index mais n'exposent les PDFs
QUE sur les pages-articles individuelles. Ce parser suit les liens internes d'une
page d'index, visite chaque page-article et y cherche les PDFs.

Limites :
- Visite max 30 pages-articles par run (configurable via source["max_pages"])
- Reste sur le même domaine
- N'explore que 1 niveau de profondeur
"""

import re
import requests
from pathlib import Path
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LibraryBot/1.0)"}
DOC_EXTENSIONS = {".pdf", ".epub", ".txt", ".doc", ".docx"}
DEFAULT_MAX_PAGES = 30

# Réduction des faux positifs : on cherche un parent "éditorial" (article/main)
# pour éviter de capturer du contexte de sidebar/footer/related-posts qui
# pollue le contexte vu par Claude.
ARTICLE_TAGS = ["article", "main"]
EXCLUDE_TAGS = ["aside", "nav", "footer", "header"]


def _editorial_scope(soup):
    """Retourne le scope éditorial principal de la page (article/main/role=article).

    Si aucun n'est trouvé, retourne le soup global (fallback).
    En présence d'un scope, on supprime au passage les blocs de bruit
    (aside/nav/footer/header) qui peuvent rester nichés dedans.
    """
    article = soup.find(ARTICLE_TAGS)
    if not article:
        article = soup.find(attrs={"role": "article"})
    if not article:
        return soup, False  # fallback : pas de scope éditorial identifié
    # On nettoie le scope éditorial des blocs de bruit éventuels imbriqués
    for tag in article.find_all(EXCLUDE_TAGS):
        tag.decompose()
    return article, True


def _dedup_by_filename(docs: list[dict]) -> list[dict]:
    """Dédup par (filename, link_text[:80]) en gardant le contexte le plus long.

    Beaucoup de pages affichent 2 fois le même PDF (en-tête + lien
    "télécharger"). On garde la variante au contexte le plus riche.
    """
    by_key: dict[tuple, dict] = {}
    for d in docs:
        key = (d["filename"], (d.get("link_text") or "")[:80])
        if key not in by_key or len(d.get("context", "")) > len(
            by_key[key].get("context", "")
        ):
            by_key[key] = d
    return list(by_key.values())


def _fetch(url: str, timeout: int = 15) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.text
    except requests.RequestException as e:
        print(f"  ⚠  deep_html : échec GET {url} : {e}")
        return None


def _same_domain(a: str, b: str) -> bool:
    return urlparse(a).netloc.lower() == urlparse(b).netloc.lower()


def _extract_docs(html: str, base_url: str, page_title: str,
                  source_url: str) -> list[dict]:
    """Trouve tous les liens vers .pdf/.epub/.txt/.doc dans la page courante.

    On limite la recherche au scope éditorial (article/main/role=article)
    quand il existe, pour éviter de capturer les liens et contextes des
    sidebars/footers/related-posts/headers — sources de faux positifs.
    """
    soup = BeautifulSoup(html, "html.parser")
    scope, has_scope = _editorial_scope(soup)
    docs, seen = [], set()
    for a in scope.find_all("a", href=True):
        full_url = urljoin(base_url, a["href"])
        ext = Path(urlparse(full_url).path).suffix.lower()
        if ext not in DOC_EXTENSIONS or full_url in seen:
            continue
        seen.add(full_url)

        link_text = a.get_text(strip=True) or Path(urlparse(full_url).path).name
        parent    = a.find_parent(["p", "li", "div", "td", "article"])
        context   = parent.get_text(" ", strip=True)[:400] if parent else link_text

        docs.append({
            "url":        full_url,
            "filename":   Path(urlparse(full_url).path).name or "document",
            "extension":  ext.lstrip("."),
            "link_text":  link_text,
            "context":    context,
            "page_title": page_title,
            "source_url": source_url,
        })
    return docs


def _find_article_links(html: str, base_url: str) -> list[str]:
    """Identifie les liens internes qui pointent vers des pages-articles.

    Heuristique : on garde les <a> qui (a) restent sur le même domaine,
    (b) ne sont pas eux-mêmes des PDFs, et (c) ne sont pas des liens de
    navigation génériques (mentions légales, contact, etc.).
    """
    soup  = BeautifulSoup(html, "html.parser")
    links = []
    seen  = set()
    blacklist = re.compile(
        r"(mentions[-_ ]legales|contact|about|qui[- _]sommes|faq|"
        r"rss|atom|login|inscription|signin|signup|cookie|privacy|"
        r"sitemap|search|recherche)",
        re.IGNORECASE,
    )

    for a in soup.find_all("a", href=True):
        full_url = urljoin(base_url, a["href"]).split("#")[0]
        if not full_url.startswith(("http://", "https://")):
            continue
        if not _same_domain(full_url, base_url):
            continue
        ext = Path(urlparse(full_url).path).suffix.lower()
        if ext in DOC_EXTENSIONS:
            continue  # déjà extrait en niveau 1
        if blacklist.search(urlparse(full_url).path):
            continue
        if full_url in seen or full_url == base_url:
            continue
        seen.add(full_url)
        links.append(full_url)

    return links


def find_documents(source: dict) -> list[dict]:
    """Point d'entrée pour le dispatcher.

    Suit jusqu'à `max_pages` liens internes depuis la page d'index et agrège
    tous les PDFs trouvés à la racine + sur les pages-articles.
    """
    base_url   = source["url"]
    max_pages  = int(source.get("max_pages", DEFAULT_MAX_PAGES))
    label      = source.get("label", base_url)

    html = _fetch(base_url)
    if not html:
        return []

    soup       = BeautifulSoup(html, "html.parser")
    page_title = (soup.title.string.strip()
                  if soup.title and soup.title.string
                  else urlparse(base_url).netloc)

    # Niveau 1 : PDFs directs sur la page d'index
    docs_seen = set()
    all_docs: list[dict] = []
    for d in _extract_docs(html, base_url, page_title, base_url):
        if d["url"] not in docs_seen:
            docs_seen.add(d["url"])
            all_docs.append(d)

    # Niveau 2 : suivre les liens internes
    article_links = _find_article_links(html, base_url)[:max_pages]
    print(f"  ↳ deep_html : crawl de {len(article_links)} sous-pages "
          f"depuis {label}")

    for i, article_url in enumerate(article_links, 1):
        article_html = _fetch(article_url, timeout=10)
        if not article_html:
            continue
        for d in _extract_docs(article_html, article_url, page_title, base_url):
            if d["url"] not in docs_seen:
                docs_seen.add(d["url"])
                all_docs.append(d)

    print(f"  ↳ deep_html : {len(all_docs)} docs total après crawl 2-niveaux")

    # Filtrage final : article-scope est déjà appliqué dans _extract_docs ;
    # ici on dédup par (filename, link_text) en gardant le contexte le plus
    # long — utile car les pages affichent souvent 2 fois le même PDF
    # (en-tête + lien « télécharger »).
    before = len(all_docs)
    all_docs = _dedup_by_filename(all_docs)
    print(f"  ↳ deep_html : {len(all_docs)} docs après filtrage "
          f"article-scope + dédup titre (était {before})")
    return all_docs


# ── Test ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    test_sources = [
        {"url": "https://cras31.info/", "label": "CRAS", "max_pages": 15},
        {"url": "https://libcom.org/library", "label": "libcom",
         "max_pages": 20},
    ]
    test = test_sources[int(sys.argv[1])] if len(sys.argv) > 1 else test_sources[0]
    print(f"=== Test deep_html sur {test['label']} ===")
    docs = find_documents(test)
    print(f"\n→ {len(docs)} docs trouvés")
    for d in docs[:5]:
        print(f"  - {d['filename']:40s}  {d['url']}")

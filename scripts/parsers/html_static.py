#!/usr/bin/env python3
"""
html_static.py — Parser HTML statique standard.

Scrape une page et liste tous les liens <a href> qui pointent vers un fichier
.pdf/.epub/.txt/.doc/.docx en HTML direct (sans suivre de lien interne).

C'est le parser par défaut, équivalent à l'ancienne fonction find_documents()
de watch.py.
"""

import requests
from pathlib import Path
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LibraryBot/1.0)"}
DOC_EXTENSIONS = {".pdf", ".epub", ".txt", ".doc", ".docx"}


def find_documents(source: dict) -> list[dict]:
    base_url = source["url"]
    label    = source.get("label", base_url)

    try:
        r = requests.get(base_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        html = r.text
    except requests.RequestException as e:
        print(f"  ⚠  html_static : impossible de charger {base_url} : {e}")
        return []

    soup = BeautifulSoup(html, "html.parser")
    page_title = (soup.title.string.strip()
                  if soup.title and soup.title.string
                  else urlparse(base_url).netloc)

    seen, docs = set(), []
    for a in soup.find_all("a", href=True):
        full_url = urljoin(base_url, a["href"])
        ext = Path(urlparse(full_url).path).suffix.lower()
        if ext not in DOC_EXTENSIONS or full_url in seen:
            continue
        seen.add(full_url)

        link_text = a.get_text(strip=True)
        parent    = a.find_parent(["p", "li", "div", "td", "article"])
        context   = parent.get_text(" ", strip=True)[:400] if parent else link_text

        docs.append({
            "url":        full_url,
            "filename":   Path(urlparse(full_url).path).name or "document",
            "extension":  ext.lstrip("."),
            "link_text":  link_text,
            "context":    context,
            "page_title": page_title,
            "source_url": base_url,
        })

    return docs


if __name__ == "__main__":
    docs = find_documents({"url": "https://infokiosques.net/", "label": "Test"})
    print(f"→ {len(docs)} docs trouvés")
    for d in docs[:5]:
        print(f"  - {d['filename']}")

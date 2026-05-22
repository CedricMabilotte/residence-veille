#!/usr/bin/env python3
"""
_listing.py — Cœur commun des parsers : extraction de liens d'annonces.

Modèle de la veille « Résidence » (refactor « zéro PDF ») : un item n'est
plus un fichier téléchargeable mais **le lien exact vers la page HTML de
l'annonce / appel** (résidence, bourse, prix, exposition).

Ce module fournit :
  - BROWSER_UA       : User-Agent navigateur réaliste (anti-blocage 403)
  - fetch_html()     : GET d'une page HTML (requests)
  - extract_listing_items() : depuis une page d'index, renvoie les liens
                              vers les pages-détail (= les annonces).

Le titre extrait est *provisoire* : `process_item` (watch.py) relit ensuite
la page de l'annonce et `extract_opportunity` en tire le vrai nom. Le parser
doit donc surtout fournir la bonne URL ; un titre approximatif suffit.

Contrat d'item :
    {url, title, link_text, text, context, page_title, source_url, extension}
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# User-Agent navigateur réaliste — l'ancien « LibraryBot/1.0 » se signalait
# comme robot et déclenchait des 403.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8,es;q=0.7",
}

# Extensions à ignorer : ce ne sont pas des pages d'annonce HTML.
ASSET_EXT = {
    ".pdf", ".epub", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".bmp",
    ".css", ".js", ".json", ".xml", ".rss", ".mp4", ".mp3", ".avi", ".mov",
}

# Liens de navigation / service à écarter.
NAV_BLACKLIST = re.compile(
    r"(mentions?[-_ ]?leg|cookie|privacy|confidential|/contact|newsletter|"
    r"\brss\b|/atom|sitemap|/login|signin|sign-in|signup|sign-up|/account|"
    r"/panier|/cart|/search|/recherche|wp-admin|wp-login|/feed/|/tag/|"
    r"/category/|/categorie/|/auteur|/author/|facebook\.com|twitter\.com|"
    r"x\.com/|instagram\.com|linkedin\.com|youtube\.com|tiktok\.com|"
    r"mailto:|tel:|javascript:|/cgu|/cookies|#)",
    re.IGNORECASE,
)
NOISE_TAGS = ["script", "style", "nav", "header", "footer", "aside", "form"]

DEFAULT_MAX_ITEMS = 40
MIN_TITLE_LEN = 6


def fetch_html(url: str, timeout: int = 25) -> str | None:
    """GET d'une page HTML avec UA navigateur. Retourne None sur échec."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout,
                          allow_redirects=True)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  ⚠  fetch échoué {url} : {e}")
        return None
    if "html" not in (r.headers.get("Content-Type") or "").lower():
        return None
    return r.text


def _content_scope(soup: BeautifulSoup):
    """Retourne le conteneur de contenu principal.

    Retire d'abord le bruit global (menus, pieds de page, scripts…). Choisit
    ensuite un conteneur principal (main/article/#content) *seulement s'il est
    assez riche en liens* — sinon on garde le <body> entier, car beaucoup de
    thèmes placent le vrai contenu hors d'un <main> trop étroit.
    """
    for tag in soup.find_all(NOISE_TAGS):
        tag.decompose()
    body = soup.body or soup
    for finder in (
        lambda: soup.find("main"),
        lambda: soup.find(attrs={"role": "main"}),
        lambda: soup.find(id=re.compile(r"content|main", re.I)),
        lambda: soup.find(class_=re.compile(
            r"listing|results|grid|cards|archive|posts|content", re.I)),
    ):
        node = finder()
        if node and len(node.find_all("a", href=True)) >= 5:
            return node
    return body


def _humanize_slug(path: str) -> str:
    """Transforme le dernier segment d'URL en titre lisible (repli)."""
    segs = [s for s in path.split("/") if s]
    if not segs:
        return ""
    slug = re.sub(r"\.\w+$", "", segs[-1])
    words = re.sub(r"[-_]+", " ", slug).strip()
    return words[:1].upper() + words[1:] if words else ""


def _derive_title(a, full_url: str) -> str:
    """Trouve un titre pour le lien : ancre, attribut, titre voisin, ou slug."""
    txt = a.get_text(" ", strip=True)
    if len(txt) >= MIN_TITLE_LEN:
        return txt[:200]
    for attr in ("aria-label", "title"):
        v = (a.get(attr) or "").strip()
        if len(v) >= MIN_TITLE_LEN:
            return v[:200]
    img = a.find("img")
    if img and len((img.get("alt") or "").strip()) >= MIN_TITLE_LEN:
        return img["alt"].strip()[:200]
    parent = a.find_parent(["li", "article", "div"])
    if parent:
        h = parent.find(["h1", "h2", "h3", "h4"])
        if h and len(h.get_text(" ", strip=True)) >= MIN_TITLE_LEN:
            return h.get_text(" ", strip=True)[:200]
    return _humanize_slug(urlparse(full_url).path) or txt


def _looks_like_detail(path: str) -> bool:
    """Heuristique : l'URL ressemble-t-elle à une page-détail (pas un menu) ?"""
    segs = [s for s in path.split("/") if s]
    if not segs:
        return False
    last = segs[-1]
    return ("-" in last) or len(last) >= 8 or len(segs) >= 2


def extract_listing_items(
    html: str,
    base_url: str,
    max_items: int = DEFAULT_MAX_ITEMS,
    same_domain_only: bool = True,
) -> list[dict]:
    """Depuis une page d'index, renvoie les liens vers les pages-détail.

    Heuristique généreuse : on garde les <a> du contenu principal pointant
    vers une autre page HTML du site et qui ressemblent à une page-détail
    (slug, sous-chemin) ou portent un intitulé riche. Le tri privilégie les
    sous-pages de l'index et les intitulés explicites ; `detect_type` (Claude,
    côté watch.py) écarte ensuite ce qui n'est pas une opportunité.

    Repli : si rien n'est trouvé, la page elle-même devient l'annonce.
    """
    soup = BeautifulSoup(html, "html.parser")
    page_title = (
        soup.title.string.strip()
        if soup.title and soup.title.string
        else urlparse(base_url).netloc
    )
    scope = _content_scope(soup)
    base_dom = urlparse(base_url).netloc.lower()
    base_norm = base_url.split("#")[0].rstrip("/")
    base_path = urlparse(base_norm).path.rstrip("/")

    scored: list[tuple[int, dict]] = []
    seen: set[str] = set()

    for a in scope.find_all("a", href=True):
        full = urljoin(base_url, a["href"]).split("#")[0].rstrip("/")
        if not full.startswith(("http://", "https://")):
            continue
        parsed = urlparse(full)
        if same_domain_only and parsed.netloc.lower() != base_dom:
            continue
        if Path(parsed.path).suffix.lower() in ASSET_EXT:
            continue
        if NAV_BLACKLIST.search(full):
            continue
        if full == base_norm or not parsed.path.strip("/"):
            continue
        if full in seen:
            continue

        anchor = a.get_text(" ", strip=True)
        if not (_looks_like_detail(parsed.path) or len(anchor) >= 12):
            continue
        seen.add(full)

        title = _derive_title(a, full)
        if len(title) < MIN_TITLE_LEN:
            continue

        parent = a.find_parent(["li", "article", "div", "td"])
        context = parent.get_text(" ", strip=True)[:400] if parent else title

        # Score de pertinence pour le tri (avant plafonnement).
        score = 0
        if base_path and parsed.path.startswith(base_path + "/"):
            score += 3
        if len(anchor) >= 20:
            score += 2
        elif len(anchor) >= 12:
            score += 1
        if "-" in (parsed.path.rstrip("/").rsplit("/", 1)[-1]):
            score += 1

        scored.append((score, {
            "url": full,
            "title": title,
            "link_text": title,
            "text": context,
            "context": context,
            "page_title": page_title,
            "source_url": base_url,
            "extension": "html",
        }))

    scored.sort(key=lambda t: t[0], reverse=True)
    items = [it for _, it in scored[:max_items]]

    # Repli : la page d'index est elle-même l'annonce.
    if not items:
        body_txt = scope.get_text(" ", strip=True)[:600]
        if len(body_txt) >= 80:
            items.append({
                "url": base_norm,
                "title": page_title,
                "link_text": page_title,
                "text": body_txt,
                "context": body_txt,
                "page_title": page_title,
                "source_url": base_url,
                "extension": "html",
            })

    return items

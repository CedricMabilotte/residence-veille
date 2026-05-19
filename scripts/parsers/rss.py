#!/usr/bin/env python3
"""
rss.py — Parser pour flux RSS/Atom.

Un flux RSS ne renvoie pas des PDFs mais des liens vers des articles HTML.
On capture ces liens comme « candidats » (titre + description) pour que le
scoreur Claude évalue la pertinence. Compatible avec l'API parser standard.

On gère RSS 2.0 ET Atom (deux dialectes XML les plus courants), en pur
stdlib via xml.etree.ElementTree.
"""

from __future__ import annotations

import datetime as _dt
import re
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import requests
import yaml

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LibraryBot/1.0)"}
TIMEOUT = 20
DEFAULT_MAX_ITEMS = 30
CONTEXT_MAX = 400

# Namespaces Atom
NS = {"atom": "http://www.w3.org/2005/Atom"}

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CANDIDATES = ROOT / "discovery" / "candidates.yml"


# ── Helpers ───────────────────────────────────────────────────────────────────
def _strip_html(s: str) -> str:
    """Strip basique : retire tags HTML et compresse les espaces."""
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:CONTEXT_MAX]


def _text(elem: Optional[ET.Element]) -> str:
    return (elem.text or "").strip() if elem is not None else ""


def _parse_rss(root: ET.Element) -> list[dict]:
    """Parse RSS 2.0 : <channel><item>...</item></channel>."""
    items: list[dict] = []
    for item in root.iter("item"):
        items.append({
            "link": _text(item.find("link")),
            "title": _text(item.find("title")),
            "description": _strip_html(_text(item.find("description"))),
        })
    return items


def _parse_atom(root: ET.Element) -> list[dict]:
    """Parse Atom : <feed><entry>...</entry></feed>."""
    items: list[dict] = []
    for entry in root.findall("atom:entry", NS):
        # Atom <link href="..."/> avec rel="alternate" (ou pas de rel).
        link = ""
        for ln in entry.findall("atom:link", NS):
            rel = ln.get("rel", "alternate")
            if rel == "alternate":
                link = ln.get("href", "")
                break
        title = _text(entry.find("atom:title", NS))
        summary = _strip_html(_text(entry.find("atom:summary", NS))
                              or _text(entry.find("atom:content", NS)))
        items.append({"link": link, "title": title, "description": summary})
    return items


# ── Écriture candidates.yml (merge idempotent) ────────────────────────────────
def _now_iso() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _today() -> str:
    return _dt.date.today().isoformat()


def _write_candidates(items: list[dict], source_label: str,
                      candidates_path: Path = DEFAULT_CANDIDATES) -> None:
    """Ajoute les liens RSS au fichier candidates.yml (type=rss)."""
    candidates_path.parent.mkdir(parents=True, exist_ok=True)
    if candidates_path.exists():
        with candidates_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}
    data.setdefault("candidates", [])

    for it in items:
        url = it["link"]
        if not url:
            continue
        new_cand = {
            "url": url,
            "type": "rss",
            "found_from": [{
                "source": f"RSS feed: {source_label}",
                "context": (it["title"] + " — " + it["description"])[:300],
                "timestamp": _now_iso(),
            }],
            "seen_count": 1,
            "domain": urlparse(url).netloc,
            "first_seen": _today(),
            "last_seen": _today(),
            "metadata": {"title": it["title"]},
            "suggested_action": "follow_one_time",
        }
        # merge idempotent
        merged = False
        for c in data["candidates"]:
            if c.get("url") == url:
                c["seen_count"] = c.get("seen_count", 1) + 1
                c["last_seen"] = _today()
                merged = True
                break
        if not merged:
            data["candidates"].append(new_cand)

    data["last_updated"] = _now_iso()
    data["total_candidates"] = len(data["candidates"])
    with candidates_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


# ── API parser standard ───────────────────────────────────────────────────────
def find_documents(source: dict) -> list[dict]:
    """Récupère un flux RSS/Atom et retourne ses items au format doc.
    NB: extension='html' (ce sont des articles, pas des PDFs)."""
    url = source.get("url", "")
    label = source.get("label", url)
    max_items = int(source.get("max_items", DEFAULT_MAX_ITEMS))
    if not url:
        return []

    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        content = r.content
    except requests.RequestException as e:
        print(f"  ⚠  rss : impossible de charger {url} : {e}")
        return []

    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        print(f"  ⚠  rss : XML invalide pour {url} : {e}")
        return []

    # Détection RSS vs Atom : tag racine.
    if root.tag.endswith("rss") or root.tag == "rss":
        items = _parse_rss(root)
    elif root.tag.endswith("feed"):
        items = _parse_atom(root)
    else:
        # Tentative : parfois rss est imbriqué.
        items = _parse_rss(root) or _parse_atom(root)

    items = items[:max_items]

    # Écrit aussi dans candidates.yml (best effort, on n'échoue pas si problème).
    try:
        _write_candidates(items, label)
    except (OSError, yaml.YAMLError) as e:
        print(f"  ⚠  rss : impossible d'écrire candidates.yml : {e}")

    docs: list[dict] = []
    for it in items:
        link = it["link"]
        if not link:
            continue
        docs.append({
            "url": link,
            "filename": (urlparse(link).path.rstrip("/").split("/")[-1]
                         or "article") + ".html",
            "extension": "html",
            "link_text": it["title"],
            "context": it["description"],
            "page_title": label,
            "source_url": url,
        })
    return docs


if __name__ == "__main__":
    test_feeds = [
        {"url": "https://reporterre.net/spip.php?page=backend",
         "label": "Reporterre"},
        {"url": "https://lundi.am/spip.php?page=backend",
         "label": "Lundi.am"},
        {"url": "https://ohlavache.fr/feed", "label": "Oh la vache"},
    ]
    for src in test_feeds:
        print(f"\n=== {src['label']} ({src['url']}) ===", file=sys.stderr)
        docs = find_documents(src)
        print(f"  → {len(docs)} items", file=sys.stderr)
        for d in docs[:3]:
            print(f"  - {d['link_text'][:80]}", file=sys.stderr)

#!/usr/bin/env python3
"""
probe_source.py — Teste une URL candidate comme source de la veille.

Depuis le refactor « zéro PDF » : on ne compte plus des fichiers
téléchargeables mais le nombre de **liens d'annonces HTML** que l'URL
expose (via le même extracteur que les parsers : parsers/_listing).

Usage :
  python scripts/probe_source.py <URL> [--id SOURCE_ID] [--label "LABEL"] \\
                                       [--type html|deep_html|playwright|rss|jsonld_event] \\
                                       [--language fr|en|es|de|multi] \\
                                       [--themes "theme1,theme2"]

Sans --id, l'URL n'est que testée (pas inscrite dans le registre).
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parsers import _listing  # noqa: E402

REGISTRY = Path(__file__).parent.parent / "docs-meta" / "SOURCES-REGISTRY.yml"


def probe_url(url: str) -> dict:
    """Retourne {ok, status, n_items, error?, hint?}."""
    try:
        r = requests.get(url, headers=_listing.HEADERS, timeout=20,
                          allow_redirects=True)
        r.raise_for_status()
    except requests.RequestException as e:
        status = getattr(getattr(e, "response", None), "status_code", 0) or 0
        return {"ok": False, "status": status, "n_items": 0, "error": str(e)}

    ctype = (r.headers.get("Content-Type") or "").lower()
    if "html" not in ctype:
        return {"ok": True, "status": r.status_code, "n_items": 0,
                "hint": f"contenu non-HTML ({ctype or 'inconnu'})"}

    items = _listing.extract_listing_items(r.text, url, max_items=60)
    n = len(items)

    hint = None
    if n <= 1:
        if re.search(r"__NEXT_DATA__|window\.__NUXT|data-reactroot|"
                     r"<script[^>]+(react|vue|angular|nuxt|next)", r.text, re.I):
            hint = "Page rendue en JS — utiliser type: playwright"
        elif re.search(r"<(rss|feed)\b", r.text, re.I):
            hint = "Flux RSS/Atom détecté — utiliser type: rss"
        elif re.search(r'application/ld\+json', r.text, re.I):
            hint = "Données Schema.org présentes — tester type: jsonld_event"

    return {"ok": True, "status": r.status_code, "n_items": n, "hint": hint}


def register(url: str, source_id: str, label: str, source_type: str,
             language: str, themes: list[str], n_items: int) -> None:
    """Ajoute ou met à jour l'entrée dans SOURCES-REGISTRY.yml."""
    if REGISTRY.exists():
        with open(REGISTRY, encoding="utf-8") as f:
            registry = yaml.safe_load(f) or {"sources": [], "meta": {}}
    else:
        registry = {"sources": [], "meta": {}}

    existing = next(
        (s for s in registry["sources"] if s.get("id") == source_id), None
    )

    entry = {
        "id":             source_id,
        "label":          label,
        "url":            url,
        "type":           source_type,
        "status":         "validated" if n_items >= 5 else "needs_review",
        "language":       language,
        "themes":         themes,
        "last_probe":     str(date.today()),
        "last_item_count": n_items,
    }

    if existing:
        existing.update(entry)
        action = "updated"
    else:
        registry["sources"].append(entry)
        action = "added"

    statuses = [s.get("status", "?") for s in registry["sources"]]
    registry["meta"] = {
        "last_updated":  str(date.today()),
        "total_sources": len(registry["sources"]),
        "validated":     statuses.count("validated"),
        "needs_review":  statuses.count("needs_review"),
        "rejected":      statuses.count("rejected"),
    }

    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY, "w", encoding="utf-8") as f:
        yaml.dump(registry, f, allow_unicode=True, sort_keys=False, width=120)

    print(f"→ Registre {action} : {source_id} "
          f"({n_items} annonces, status={entry['status']})")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("url")
    p.add_argument("--id")
    p.add_argument("--label", default="")
    p.add_argument("--type", default="html",
                   choices=["html", "deep_html", "playwright", "rss",
                            "jsonld_event"])
    p.add_argument("--language", default="fr")
    p.add_argument("--themes", default="")
    args = p.parse_args()

    print(f"\n🔍  Probe : {args.url}")
    result = probe_url(args.url)

    if not result["ok"]:
        print(f"  ❌  Erreur : {result['error']}")
        return 1

    print(f"  HTTP {result['status']}")
    print(f"  Annonces HTML repérées : {result['n_items']}")
    if result.get("hint"):
        print(f"  💡  Indice : {result['hint']}")

    if args.id:
        themes = [t.strip() for t in args.themes.split(",") if t.strip()]
        register(args.url, args.id, args.label or args.id,
                 args.type, args.language, themes, result["n_items"])
    else:
        print("  (pas d'--id fourni → registre non modifié)")

    return 0


if __name__ == "__main__":
    sys.exit(main())

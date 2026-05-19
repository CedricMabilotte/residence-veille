#!/usr/bin/env python3
"""
probe_source.py — Utilitaire pour tester une URL candidate et l'ajouter
au registre SOURCES-REGISTRY.yml.

Usage :
  python scripts/probe_source.py <URL> [--id SOURCE_ID] [--label "LABEL"] \\
                                       [--type html|deep_html|opds|archive_org|hal] \\
                                       [--language fr|en|es|de|multi] \\
                                       [--themes "theme1,theme2"]

Sans --id, l'URL n'est que testée (pas inscrite dans le registre).
"""

import argparse
import sys
import yaml
import requests
import re
from pathlib import Path
from datetime import date

REGISTRY = Path(__file__).parent.parent / "docs-meta" / "SOURCES-REGISTRY.yml"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LibraryBot/1.0)"}
DOC_EXT_RE = re.compile(r'href="[^"]+\.(pdf|epub|txt|docx?)"', re.IGNORECASE)


def probe_url(url: str) -> dict:
    """Retourne {ok, status, doc_count, error?, hint?}."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except requests.RequestException as e:
        return {"ok": False, "status": 0, "doc_count": 0, "error": str(e)}

    body = r.text
    doc_count = len(DOC_EXT_RE.findall(body))

    hint = None
    if doc_count == 0:
        # Heuristiques pour deviner le bon parser
        if re.search(r"<script[^>]+(react|vue|angular|nuxt|next)", body, re.I):
            hint = "JS-rendered (Playwright requis)"
        elif re.search(r"<opds|<feed[^>]+atom", body, re.I):
            hint = "OPDS feed détecté — utiliser type: opds"
        elif "advancedsearch.php" in url or "output=json" in url:
            hint = "API Archive.org JSON — utiliser type: archive_org"
        elif "archives-ouvertes.fr" in url:
            hint = "API HAL JSON — utiliser type: hal"
        elif re.search(r"/IMG/pdf/|/files/|wp-content/uploads", body):
            hint = "PDFs présents mais pas en racine — utiliser type: deep_html"

    return {"ok": True, "status": r.status_code, "doc_count": doc_count, "hint": hint}


def register(url: str, source_id: str, label: str, source_type: str,
             language: str, themes: list[str], doc_count: int) -> None:
    """Ajoute ou met à jour l'entrée dans SOURCES-REGISTRY.yml."""
    with open(REGISTRY, encoding="utf-8") as f:
        registry = yaml.safe_load(f) or {"sources": [], "meta": {}}

    existing = next(
        (s for s in registry["sources"] if s.get("id") == source_id), None
    )

    entry = {
        "id":              source_id,
        "label":           label,
        "url":             url,
        "type":            source_type,
        "status":          "validated" if doc_count >= 5 else "needs_parser",
        "language":        language,
        "themes":          themes,
        "last_probe":      str(date.today()),
        "last_doc_count":  doc_count,
    }

    if existing:
        existing.update(entry)
        action = "updated"
    else:
        registry["sources"].append(entry)
        action = "added"

    # Mise à jour des stats meta
    statuses = [s.get("status", "?") for s in registry["sources"]]
    registry["meta"] = {
        "last_updated":   str(date.today()),
        "total_sources":  len(registry["sources"]),
        "active":         statuses.count("active"),
        "validated":      statuses.count("validated"),
        "needs_parser":   statuses.count("needs_parser"),
        "js_only":        statuses.count("js_only"),
        "rejected":       statuses.count("rejected"),
    }

    with open(REGISTRY, "w", encoding="utf-8") as f:
        yaml.dump(registry, f, allow_unicode=True, sort_keys=False, width=120)

    print(f"→ Registre {action} : {source_id} ({doc_count} docs, status={entry['status']})")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("url")
    p.add_argument("--id")
    p.add_argument("--label", default="")
    p.add_argument("--type", default="html",
                   choices=["html", "deep_html", "opds", "archive_org", "hal", "playwright"])
    p.add_argument("--language", default="fr")
    p.add_argument("--themes", default="")
    args = p.parse_args()

    print(f"\n🔍  Probe : {args.url}")
    result = probe_url(args.url)

    if not result["ok"]:
        print(f"  ❌  Erreur : {result['error']}")
        return 1

    print(f"  HTTP {result['status']}")
    print(f"  Documents (.pdf/.epub/.txt/.doc) trouvés : {result['doc_count']}")
    if result["hint"]:
        print(f"  💡  Indice : {result['hint']}")

    if args.id:
        themes = [t.strip() for t in args.themes.split(",") if t.strip()]
        register(args.url, args.id, args.label or args.id,
                 args.type, args.language, themes, result["doc_count"])
    else:
        print("  (pas d'--id fourni → registre non modifié)")

    return 0


if __name__ == "__main__":
    sys.exit(main())

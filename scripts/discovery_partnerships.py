#!/usr/bin/env python3
"""
discovery_partnerships.py — Graphe de partenariats (§12.3/B).

Scan toutes les fiches dans appels/ et archive/, agrège les partenaires
mentionnés, et propose les organismes peu connus mais souvent cités
comme candidats à instruire.

Sortie : discovery/organismes-graph.yml
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
APPELS_DIR = ROOT / "appels"
ARCHIVE_DIR = ROOT / "archive"
ORGANISMES_DIR = ROOT / "organismes"
GRAPH_PATH = ROOT / "discovery" / "organismes-graph.yml"


def iter_fiches():
    for base in (APPELS_DIR, ARCHIVE_DIR):
        for type_dir in ("residence", "bourse", "prix", "exposition"):
            d = base / type_dir
            if d.exists():
                yield from sorted(d.glob("*.yml"))


def main():
    counter: Counter[str] = Counter()
    edges: list[tuple[str, str]] = []  # (organisme principal, partenaire)

    for path in iter_fiches():
        fiche = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        org = (fiche.get("opportunite") or {}).get("organisme")
        for p in fiche.get("partenaires") or []:
            if not p:
                continue
            counter[p] += 1
            if org and p != org:
                edges.append((org, p))

    # Connus = organismes ayant déjà une fiche
    ORGANISMES_DIR.mkdir(parents=True, exist_ok=True)
    known_names = set()
    for f in ORGANISMES_DIR.glob("*.yml"):
        d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        known_names.add((d.get("nom_canonique") or "").lower())

    candidats = [
        {"nom": name, "occurrences": n}
        for name, n in counter.most_common()
        if name.lower() not in known_names and n >= 3
    ]

    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    GRAPH_PATH.write_text(
        yaml.safe_dump(
            {
                "edges_count": len(edges),
                "partenaires_distincts": len(counter),
                "candidats_a_instruire": candidats[:50],
            },
            allow_unicode=True, sort_keys=False, width=120,
        ),
        encoding="utf-8",
    )
    print(f"discovery_partnerships : {len(counter)} partenaires distincts, "
          f"{len(candidats)} candidats ≥ 3 mentions.")


if __name__ == "__main__":
    main()

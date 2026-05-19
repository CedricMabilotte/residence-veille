#!/usr/bin/env python3
"""
discovery_editions_archive.py — Patterns d'URL "lauréat·es par année" (§12.3/H).

Quand une fiche contient une URL de type /laureats/2024 ou /winners/2024
ou /laureados/2024 :
  - capture le pattern d'URL dans discovery/url-patterns.yml
  - prédit les URL d'éditions passées et futures à tester
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
APPELS_DIR = ROOT / "appels"
ARCHIVE_DIR = ROOT / "archive"
PATTERNS_PATH = ROOT / "discovery" / "url-patterns.yml"

EDITION_RE = re.compile(
    r"(https?://[^/]+/[^?#]*?/(laureats|laur[eé]ats|winners|laureados|laureati|gewinner|edition)s?/(20\d{2}|19\d{2}))",
    re.IGNORECASE,
)


def _load_patterns() -> dict:
    if PATTERNS_PATH.exists():
        return yaml.safe_load(PATTERNS_PATH.read_text(encoding="utf-8")) or {"patterns": []}
    return {"patterns": []}


def _save_patterns(data: dict) -> None:
    PATTERNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PATTERNS_PATH.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )


def extract_patterns(fiche_path: Path) -> list[dict]:
    """Cherche les URLs match dans le YAML (source_url, partenaires liens HTML…)."""
    text = fiche_path.read_text(encoding="utf-8")
    matches = EDITION_RE.findall(text)
    out = []
    for full, kw, year in matches:
        template = full.rsplit("/", 1)[0] + "/{YEAR}"
        out.append({"template": template, "exemple_url": full, "annee_vue": year})
    return out


def main():
    data = _load_patterns()
    patterns = data.setdefault("patterns", [])
    seen_templates = {p["template"] for p in patterns}
    n_new = 0

    for base in (APPELS_DIR, ARCHIVE_DIR):
        for type_dir in ("residence", "bourse", "prix", "exposition"):
            d = base / type_dir
            if not d.exists():
                continue
            for f in sorted(d.glob("*.yml")):
                for entry in extract_patterns(f):
                    if entry["template"] in seen_templates:
                        continue
                    # Suggestions d'URLs futures (3 prochaines années)
                    base_year = int(entry["annee_vue"])
                    entry["suggestions_a_tester"] = [
                        entry["template"].replace("{YEAR}", str(base_year + i))
                        for i in (-2, -1, 1, 2, 3)
                    ]
                    patterns.append(entry)
                    seen_templates.add(entry["template"])
                    n_new += 1

    _save_patterns(data)
    print(f"discovery_editions_archive : {n_new} nouveau(x) pattern(s) URL capturé(s).")


if __name__ == "__main__":
    main()

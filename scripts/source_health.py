#!/usr/bin/env python3
"""
source_health.py — Génère un rapport SOURCE-HEALTH.md à partir de
SOURCES-REGISTRY.yml + dernier rapport de run.

Sortie : docs-meta/SOURCE-HEALTH.md (régénéré à chaque appel).

Usage :
  python scripts/source_health.py
"""

import yaml
import json
from pathlib import Path
from datetime import datetime, date

REPO     = Path(__file__).parent.parent
REGISTRY = REPO / "docs-meta" / "SOURCES-REGISTRY.yml"
REPORTS  = REPO / "reports"
OUTPUT   = REPO / "docs-meta" / "SOURCE-HEALTH.md"


def latest_run_stats() -> dict | None:
    """Retourne {date, source_label: {found, downloaded, mean_score}} ou None."""
    runs = sorted(REPORTS.glob("run_*.json"))
    if not runs:
        return None
    latest = json.loads(runs[-1].read_text(encoding="utf-8"))

    by_source: dict[str, dict] = {}
    for r in latest.get("results", []):
        label = r.get("source", "?")
        bucket = by_source.setdefault(
            label, {"found": 0, "downloaded": 0, "scores": []}
        )
        bucket["found"] += 1
        if r.get("downloaded"):
            bucket["downloaded"] += 1
        bucket["scores"].append(r.get("score", 0))

    for s in by_source.values():
        s["mean_score"] = round(sum(s["scores"]) / len(s["scores"]), 1) if s["scores"] else 0
        del s["scores"]

    return {"date": latest.get("date", "?"), "by_source": by_source}


def main() -> None:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    stats    = latest_run_stats()

    lines = [
        "# Source Health Report",
        "",
        f"*Généré le {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*",
        "",
    ]

    # Méta
    m = registry.get("meta", {})
    lines += [
        "## Vue d'ensemble",
        "",
        f"- Total de sources recensées : **{m.get('total_sources', 0)}**",
        f"- En production (`active`)    : **{m.get('active', 0)}**",
        f"- Validées (`validated`)      : **{m.get('validated', 0)}**",
        f"- Nécessitent parser dédié    : **{m.get('needs_parser', 0)}**",
        f"- JS-only (Playwright requis) : **{m.get('js_only', 0)}**",
        f"- Rejetées                    : **{m.get('rejected', 0)}**",
        "",
    ]

    # Stats du dernier run
    if stats:
        lines += [
            "## Performance du dernier run",
            "",
            f"*Date : {stats['date']}*",
            "",
            "| Source | Trouvés | Téléchargés | Score moyen |",
            "|--------|---------|-------------|-------------|",
        ]
        for label, s in sorted(stats["by_source"].items(),
                               key=lambda kv: -kv[1]["downloaded"]):
            lines.append(
                f"| {label} | {s['found']} | {s['downloaded']} | {s['mean_score']}/10 |"
            )
        lines.append("")

    # Liste par status
    by_status: dict[str, list] = {}
    for s in registry.get("sources", []):
        by_status.setdefault(s.get("status", "?"), []).append(s)

    for status, label_emoji in [
        ("active",       "✅ Actives (en production)"),
        ("validated",    "🟢 Validées (prêtes à activer)"),
        ("needs_parser", "🟡 Nécessitent parser spécialisé"),
        ("js_only",      "🟠 JS-only (Playwright requis)"),
        ("dead",         "💀 Mortes"),
        ("rejected",     "🔴 Rejetées"),
    ]:
        sources = by_status.get(status, [])
        if not sources:
            continue
        lines += [f"## {label_emoji} ({len(sources)})", ""]
        for s in sources:
            line = f"- **{s.get('label', s.get('id', '?'))}** [{s.get('language', '?')}, type={s.get('type', '?')}]"
            if s.get("last_doc_count") is not None:
                line += f" — {s['last_doc_count']} docs (probe: {s.get('last_probe', '?')})"
            lines.append(line)
            lines.append(f"  - `{s['url']}`")
            if s.get("themes"):
                lines.append(f"  - Thèmes : {', '.join(s['themes'])}")
            if s.get("notes"):
                lines.append(f"  - 📝 {s['notes']}")
        lines.append("")

    # Roadmap
    lines += [
        "## Roadmap d'activation",
        "",
        "Sources `validated` à activer dans `config/sources.yml` :",
    ]
    for s in by_status.get("validated", []):
        lines.append(f"- [ ] {s.get('label', s.get('id', '?'))}")
    lines += [
        "",
        "Parsers à implémenter pour débloquer les sources `needs_parser` :",
    ]
    needed_parsers = sorted({s.get("type", "?") for s in by_status.get("needs_parser", [])})
    for t in needed_parsers:
        count = sum(1 for s in by_status.get("needs_parser", []) if s.get("type") == t)
        lines.append(f"- [ ] `{t}` ({count} source{'s' if count > 1 else ''})")
    lines.append("")

    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"→ Rapport écrit : {OUTPUT.relative_to(REPO)}")
    print(f"  Sources : {m.get('total_sources', 0)} total, {m.get('active', 0)} actives, "
          f"{m.get('validated', 0)} validées, {m.get('needs_parser', 0)} en attente de parser")


if __name__ == "__main__":
    main()

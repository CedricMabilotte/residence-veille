#!/usr/bin/env python3
"""
discovery_llm_suggest.py — Suggesteur de nouvelles sources via Claude.

À exécuter une fois par mois (cron). Construit un contexte court à partir du
catalog actuel + ontologie + sources existantes, demande à Claude
(claude-haiku-4-5, via claude -p) de proposer N nouvelles sources possibles,
parse la réponse JSON et :
  - ajoute les suggestions à discovery/candidates.yml (type=llm_suggestion)
  - écrit un rapport Markdown lisible dans discovery/reports/.
"""

from __future__ import annotations

import json
import subprocess
import claude_guard
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import yaml

# ── Réutilise EXACTEMENT le pattern Claude de synopsis_enricher.py ────────────
CLAUDE_TIMEOUT_SEC = 240
CLAUDE_MODEL = "claude-haiku-4-5"
CLAUDE_FLAGS = [
    "--output-format", "text",
    "--no-session-persistence",
    "--disable-slash-commands",
    "--tools", "",
    "--dangerously-skip-permissions",
]


def _call_claude(prompt: str, timeout: int = CLAUDE_TIMEOUT_SEC) -> str:
    """Wrapper subprocess identique à synopsis_enricher._call_claude."""
    claude_guard.guard_before_call()
    result = subprocess.run(
        ["claude", "-p", prompt, "--model", CLAUDE_MODEL] + CLAUDE_FLAGS,
        capture_output=True, text=True, timeout=timeout,
        cwd="/tmp", stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        claude_guard.check_result(result.stdout, result.stderr)
        raise RuntimeError(
            f"claude exit {result.returncode} — "
            f"stdout={result.stdout[:200]} stderr={result.stderr[:200]}"
        )
    raw = result.stdout.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]
    return raw.strip()


# ── Helpers candidates.yml (autonomes — n'importe pas d'autre module) ────────
def _load_candidates(path: Path) -> dict:
    if not path.exists():
        return {"candidates": []}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {"candidates": []}


def _save_candidates(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )


def _merge_candidate(data: dict, candidate: dict) -> bool:
    """Ajoute si l'URL n'existe pas déjà. Retourne True si ajouté."""
    url = candidate.get("url", "").strip()
    if not url:
        return False
    for c in data.get("candidates", []):
        if c.get("url") == url:
            return False
    data.setdefault("candidates", []).append(candidate)
    return True


# ── Construction du contexte ──────────────────────────────────────────────────
def build_context(catalog_path: Path, concepts_path: Path,
                  sources_path: Path) -> dict:
    """Top 20 docs (score décroissant), mots-clés, sources actives, gaps évidents."""
    catalog = json.loads(catalog_path.read_text(encoding="utf-8")) \
        if catalog_path.exists() else {"docs": {}}
    concepts = yaml.safe_load(concepts_path.read_text(encoding="utf-8")) \
        if concepts_path.exists() else {}
    sources_cfg = yaml.safe_load(sources_path.read_text(encoding="utf-8")) \
        if sources_path.exists() else {}

    docs = list(catalog.get("docs", {}).values())
    docs_sorted = sorted(docs, key=lambda d: d.get("latest_score", 0), reverse=True)
    top_docs = [
        {
            "title": d.get("filename", "")[:80],
            "score": d.get("latest_score"),
            "source": d.get("source"),
        }
        for d in docs_sorted[:20]
    ]

    source_counter = Counter(d.get("source", "?") for d in docs)
    score_distribution = Counter(d.get("latest_score", 0) for d in docs)

    return {
        "ontology": concepts.get("ontology", {}),
        "editorial": concepts.get("editorial", {}),
        "active_sources": [
            {"label": s.get("label"), "url": s.get("url"), "type": s.get("type", "html")}
            for s in sources_cfg.get("sources", [])
        ],
        "keywords": sources_cfg.get("keywords", []),
        "catalog_stats": {
            "total_docs": len(docs),
            "by_source": dict(source_counter.most_common(20)),
            "score_distribution": dict(sorted(score_distribution.items())),
            "high_score_count": sum(1 for d in docs if d.get("latest_score", 0) >= 7),
        },
        "top_docs": top_docs,
    }


def suggest_new_sources(context: dict, n_suggestions: int = 10) -> dict:
    """Appelle claude -p avec un prompt structuré, parse la réponse JSON."""
    ontology = context.get("ontology", {})
    cores = [c.get("name") for c in ontology.get("core_concepts", []) or []]
    active_labels = [s["label"] for s in context.get("active_sources", [])]
    top_titles = [f"  - [{d['score']}] {d['title']}" for d in context["top_docs"][:15]]

    prompt = f"""Tu es un assistant de veille documentaire stratégique.

THÉMATIQUE :
Concepts centraux : {', '.join(cores)}
Mots-clés actifs : {', '.join(context.get('keywords', [])[:30])}

SOURCES DÉJÀ SURVEILLÉES ({len(active_labels)}) :
{chr(10).join('  - ' + s for s in active_labels)}

STATS CATALOG :
  Docs totaux : {context['catalog_stats']['total_docs']}
  Docs pertinents (≥7) : {context['catalog_stats']['high_score_count']}
  Distribution scores : {context['catalog_stats']['score_distribution']}

TOP DOCS (par score) :
{chr(10).join(top_titles)}

MISSION : propose {n_suggestions} nouvelles sources documentaires (sites,
bibliothèques numériques, archives, flux RSS, APIs) qui complèteraient cette
veille. Évite les doublons avec les sources actives. Pense angles morts :
langues sous-représentées, géographies absentes, sous-thèmes manquants,
formats peu exploités.

Réponds par UN SEUL objet JSON (pas de balise markdown) :

{{
  "suggestions": [
    {{
      "url": "https://...",
      "type": "html | rss | api | other",
      "rationale": "pourquoi cette source compléterait la veille",
      "expected_yield": "low | medium | high",
      "confidence": 0.7
    }}
  ],
  "blind_spots_identified": ["..."],
  "recommended_keywords_to_add": ["..."]
}}"""

    try:
        raw = _call_claude(prompt)
        return json.loads(raw)
    except json.JSONDecodeError as e:
        return {"error": f"json_parse: {e}", "raw_response": raw[:500]}
    except Exception as e:
        return {"error": f"claude_call: {e}"}


def _write_report(report_path: Path, context: dict, suggestions: dict) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Rapport LLM-suggest — {now}",
        "",
        f"Catalog : **{context['catalog_stats']['total_docs']}** docs, "
        f"**{context['catalog_stats']['high_score_count']}** pertinents (≥7).",
        f"Sources actives : **{len(context.get('active_sources', []))}**.",
        "",
        "## Suggestions",
        "",
    ]
    for i, s in enumerate(suggestions.get("suggestions", []), 1):
        lines += [
            f"### {i}. {s.get('url', '?')}",
            f"- **type** : `{s.get('type', '?')}`",
            f"- **yield attendu** : {s.get('expected_yield', '?')} "
            f"(conf. {s.get('confidence', '?')})",
            f"- **rationale** : {s.get('rationale', '')}",
            "",
        ]
    if suggestions.get("blind_spots_identified"):
        lines.append("## Angles morts identifiés")
        for b in suggestions["blind_spots_identified"]:
            lines.append(f"- {b}")
        lines.append("")
    if suggestions.get("recommended_keywords_to_add"):
        lines.append("## Mots-clés recommandés à ajouter")
        for k in suggestions["recommended_keywords_to_add"]:
            lines.append(f"- `{k}`")
    if "error" in suggestions:
        lines += ["", "## Erreur", f"```\n{suggestions['error']}\n```"]
    report_path.write_text("\n".join(lines), encoding="utf-8")


def run(catalog_path: Path, candidates_path: Path,
        report_path: Path,
        concepts_path: Path | None = None,
        sources_path: Path | None = None,
        n_suggestions: int = 10) -> dict:
    """Pipeline complet — retourne {added: int, total_suggested: int, error?}."""
    root = catalog_path.parent.parent
    concepts_path = concepts_path or root / "config" / "concepts.yml"
    sources_path = sources_path or root / "config" / "sources.yml"

    ctx = build_context(catalog_path, concepts_path, sources_path)
    suggestions = suggest_new_sources(ctx, n_suggestions=n_suggestions)
    _write_report(report_path, ctx, suggestions)

    if "error" in suggestions:
        return {"error": suggestions["error"], "added": 0, "total_suggested": 0}

    cands = _load_candidates(candidates_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    added = 0
    for s in suggestions.get("suggestions", []):
        cand = {
            "url": s.get("url"),
            "type": "llm_suggestion",
            "source_type": s.get("type"),
            "rationale": s.get("rationale"),
            "expected_yield": s.get("expected_yield"),
            "confidence": s.get("confidence"),
            "discovered_at": now_iso,
        }
        if _merge_candidate(cands, cand):
            added += 1
    _save_candidates(candidates_path, cands)

    return {
        "added": added,
        "total_suggested": len(suggestions.get("suggestions", [])),
        "blind_spots": suggestions.get("blind_spots_identified", []),
        "report": str(report_path),
    }


if __name__ == "__main__":
    root = Path(__file__).parent.parent
    out = run(
        catalog_path=root / "synopsis" / "catalog.json",
        candidates_path=root / "discovery" / "candidates.yml",
        report_path=root / "discovery" / "reports"
        / f"llm_suggest_{datetime.now().strftime('%Y-%m-%d')}.md",
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))

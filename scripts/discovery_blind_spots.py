#!/usr/bin/env python3
"""
discovery_blind_spots.py — Diagnostic d'angles morts via stats + Claude.

Analyse le catalog actuel pour identifier ce qui manque :
  - distribution par langue (heuristique sur titre/matched_keywords)
  - distribution par source
  - distribution par décennie (publication year heuristique)
  - sous-thèmes peu représentés (vs ontology.core_concepts)
  - sources qui n'ont jamais ramené de doc ≥ 7
Puis demande à Claude un diagnostic actionnable et écrit un rapport Markdown.
"""

from __future__ import annotations

import json
import re
import subprocess
import claude_guard
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

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
    """Wrapper subprocess identique à synopsis_enricher."""
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


# Heuristique langue par mots fréquents dans le titre/filename
_LANG_HINTS = {
    "fr": ["de la", "des", "les ", "communs", "terre", "paysann", "réforme",
           "propriété", "agraire", "anarchi", "société"],
    "en": ["the ", " and ", "land", "peasant", "commons", "rural",
           "agrarian", "of the", "movement"],
    "es": ["tierra", "campesin", "comunes", "agrari", "movimiento", " de la ",
           " del ", "soberanía"],
    "de": ["die ", "der ", "und ", "deutsch", "boden", "agrar"],
    "pt": ["terra ", "camponê", "agrári", "movimento"],
}


def _guess_language(text: str) -> str:
    t = text.lower()
    scores = {lang: sum(1 for h in hints if h in t)
              for lang, hints in _LANG_HINTS.items()}
    best_lang, best_score = max(scores.items(), key=lambda x: x[1])
    return best_lang if best_score >= 1 else "unknown"


_YEAR_RE = re.compile(r"\b(18\d{2}|19\d{2}|20\d{2})\b")


def _guess_decade(text: str) -> str | None:
    m = _YEAR_RE.search(text)
    if not m:
        return None
    return f"{m.group(0)[:3]}0s"


def compute_coverage_stats(catalog_path: Path) -> dict:
    """Stats de couverture : langue, source, décennie, sous-thèmes, sources stériles."""
    catalog = json.loads(catalog_path.read_text(encoding="utf-8")) \
        if catalog_path.exists() else {"docs": {}}
    docs = list(catalog.get("docs", {}).values())

    by_lang = Counter()
    by_source = Counter()
    by_decade = Counter()
    high_score_by_source = defaultdict(int)
    runs_by_source = defaultdict(int)

    for d in docs:
        title = (d.get("filename") or "") + " " + \
                (d.get("enrichment", {}).get("summary", "") if isinstance(
                    d.get("enrichment"), dict) else "")
        by_lang[_guess_language(title)] += 1
        src = d.get("source", "?")
        by_source[src] += 1
        runs_by_source[src] += 1
        if d.get("latest_score", 0) >= 7:
            high_score_by_source[src] += 1
        dec = _guess_decade(title)
        if dec:
            by_decade[dec] += 1

    sterile_sources = sorted(
        [s for s, n in runs_by_source.items()
         if n >= 3 and high_score_by_source.get(s, 0) == 0]
    )

    return {
        "total_docs": len(docs),
        "by_language": dict(by_lang.most_common()),
        "by_source": dict(by_source.most_common()),
        "by_decade": dict(sorted(by_decade.items())),
        "high_score_by_source": dict(high_score_by_source),
        "sterile_sources": sterile_sources,
    }


def _identify_undercovered_themes(stats: dict, concepts: dict) -> list[str]:
    """Sous-thèmes peu représentés : core_concepts sans hits récents."""
    # Naïf : on retourne tous les core_concepts (Claude pondère ensuite)
    return [c.get("name") for c in
            concepts.get("ontology", {}).get("core_concepts", []) or []]


def diagnose_with_claude(stats: dict, concepts_path: Path) -> dict:
    """Envoie les stats à Claude pour diagnostic actionnable."""
    concepts = yaml.safe_load(concepts_path.read_text(encoding="utf-8")) \
        if concepts_path.exists() else {}
    cores = _identify_undercovered_themes(stats, concepts)
    declared_langs = concepts.get("project", {}).get("languages", []) or []

    prompt = f"""Tu es un consultant en veille documentaire. Tu reçois les
statistiques de couverture d'un catalog et tu dois identifier les angles morts
en proposant des actions CONCRÈTES (URLs ou types de sources précises).

LANGUES DÉCLARÉES DANS LE PROJET : {declared_langs}

CONCEPTS CENTRAUX DE LA THÉMATIQUE :
{chr(10).join('  - ' + c for c in cores)}

STATS DE COUVERTURE :
  Total docs : {stats['total_docs']}
  Par langue (heuristique) : {stats['by_language']}
  Par décennie (heuristique) : {stats['by_decade']}
  Top sources : {dict(list(stats['by_source'].items())[:10])}
  Docs ≥ 7 par source : {stats['high_score_by_source']}
  Sources stériles (≥3 scans, 0 doc pertinent) : {stats['sterile_sources']}

MISSION : identifie 4-6 angles morts et pour CHACUN, propose 1-2 sources
concrètes (URLs réelles ou types précis : "RSS de X", "API Y", "bibliothèque Z")
qui combleraient le manque. Sois critique sur les sources stériles.

Réponds par UN SEUL objet JSON (pas de balise markdown) :

{{
  "blind_spots": [
    {{
      "axis": "langue | géo | thème | période | format",
      "description": "constat précis chiffré",
      "severity": "low | medium | high",
      "suggested_sources": [
        {{"url_or_type": "...", "rationale": "...", "type": "html|rss|api|other"}}
      ]
    }}
  ],
  "sterile_sources_verdict": [
    {{"source": "...", "recommendation": "keep | review | drop", "reason": "..."}}
  ],
  "summary": "synthèse 3-4 phrases sur l'état général de la couverture"
}}"""

    try:
        raw = _call_claude(prompt)
        return json.loads(raw)
    except json.JSONDecodeError as e:
        return {"error": f"json_parse: {e}", "raw_response": raw[:500]}
    except Exception as e:
        return {"error": f"claude_call: {e}"}


def _write_report(report_path: Path, stats: dict, diagnosis: dict) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Diagnostic d'angles morts — {now}",
        "",
        f"Catalog : **{stats['total_docs']}** docs.",
        "",
        "## Stats de couverture",
        "",
        f"- Par langue : `{stats['by_language']}`",
        f"- Par décennie : `{stats['by_decade']}`",
        f"- Sources stériles (≥3 scans, 0 doc ≥7) : "
        f"{stats['sterile_sources'] or '_aucune_'}",
        "",
    ]
    if "summary" in diagnosis:
        lines += ["## Synthèse", "", diagnosis["summary"], ""]
    for i, bs in enumerate(diagnosis.get("blind_spots", []), 1):
        lines += [
            f"### Angle mort {i} — {bs.get('axis', '?')} "
            f"({bs.get('severity', '?')})",
            "",
            bs.get("description", ""),
            "",
            "**Sources suggérées :**",
        ]
        for s in bs.get("suggested_sources", []):
            lines.append(
                f"- `{s.get('type', '?')}` — {s.get('url_or_type', '')} "
                f"→ {s.get('rationale', '')}"
            )
        lines.append("")
    if diagnosis.get("sterile_sources_verdict"):
        lines += ["## Verdict sources stériles", ""]
        for v in diagnosis["sterile_sources_verdict"]:
            lines.append(
                f"- **{v.get('source')}** → `{v.get('recommendation')}` "
                f"({v.get('reason', '')})"
            )
    if "error" in diagnosis:
        lines += ["", "## Erreur", f"```\n{diagnosis['error']}\n```"]
    report_path.write_text("\n".join(lines), encoding="utf-8")


# ── Helpers candidates.yml (autonomes) ───────────────────────────────────────
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
    url = candidate.get("url", "").strip()
    if not url:
        return False
    for c in data.get("candidates", []):
        if c.get("url") == url:
            return False
    data.setdefault("candidates", []).append(candidate)
    return True


def run(catalog_path: Path, concepts_path: Path,
        report_path: Path,
        candidates_path: Path | None = None) -> dict:
    """Pipeline complet — diagnostic + rapport + ajout aux candidats si URL."""
    stats = compute_coverage_stats(catalog_path)
    diagnosis = diagnose_with_claude(stats, concepts_path)
    _write_report(report_path, stats, diagnosis)

    added = 0
    if candidates_path and "blind_spots" in diagnosis:
        cands = _load_candidates(candidates_path)
        now_iso = datetime.now(timezone.utc).isoformat()
        for bs in diagnosis["blind_spots"]:
            for s in bs.get("suggested_sources", []):
                url_or_type = s.get("url_or_type", "")
                # On n'ajoute que si on a une vraie URL
                if not url_or_type.startswith("http"):
                    continue
                cand = {
                    "url": url_or_type,
                    "type": "blind_spot",
                    "source_type": s.get("type"),
                    "axis": bs.get("axis"),
                    "rationale": s.get("rationale"),
                    "severity": bs.get("severity"),
                    "discovered_at": now_iso,
                }
                if _merge_candidate(cands, cand):
                    added += 1
        _save_candidates(candidates_path, cands)

    return {
        "stats": stats,
        "added": added,
        "blind_spots_count": len(diagnosis.get("blind_spots", [])),
        "report": str(report_path),
        "error": diagnosis.get("error"),
    }


if __name__ == "__main__":
    root = Path(__file__).parent.parent
    out = run(
        catalog_path=root / "synopsis" / "catalog.json",
        concepts_path=root / "config" / "concepts.yml",
        report_path=root / "discovery" / "reports"
        / f"blind_spots_{datetime.now().strftime('%Y-%m-%d')}.md",
        candidates_path=root / "discovery" / "candidates.yml",
    )
    print(json.dumps({k: v for k, v in out.items() if k != "stats"},
                     ensure_ascii=False, indent=2))

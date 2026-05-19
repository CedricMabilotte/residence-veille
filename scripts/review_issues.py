#!/usr/bin/env python3
"""
review_issues.py — Triage des suggestions communautaires (GitHub issues).

Lit les issues ouvertes du repo (par défaut CedricMabilotte/veille-documentaire)
taguées `nouvelle-source` ou `correction-scoring`.

  - nouvelle-source     : extrait l'URL, lance probe_source.py, ajoute le
                          candidat à discovery/candidates.yml + commente
                          l'issue avec le rapport probe.
  - correction-scoring  : ajoute l'info à feedback.json (à la racine du repo).

Utilise `gh` CLI via subprocess. L'issue reste ouverte pour décision humaine.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

DEFAULT_REPO = "CedricMabilotte/veille-documentaire"

# URL extraite du body : 1re URL http(s) non-image, non-issue, non-asset.
_URL_RE = re.compile(r"https?://[^\s)>\]\"']+", re.IGNORECASE)
_ISSUE_TPL_FIELDS = {
    "url":           re.compile(r"^\s*(?:\*\*)?URL(?:\*\*)?\s*[:\-]\s*(\S+)", re.I | re.M),
    "label":         re.compile(r"^\s*(?:\*\*)?Label(?:\*\*)?\s*[:\-]\s*(.+)$", re.I | re.M),
    "type":          re.compile(r"^\s*(?:\*\*)?Type(?:\*\*)?\s*[:\-]\s*(\w+)", re.I | re.M),
    "justification": re.compile(r"^\s*(?:\*\*)?Justification(?:\*\*)?\s*[:\-]\s*(.+)$", re.I | re.M),
    "doc_url":       re.compile(r"^\s*(?:\*\*)?Doc(?:\s*URL)?(?:\*\*)?\s*[:\-]\s*(\S+)", re.I | re.M),
    "old_score":     re.compile(r"^\s*(?:\*\*)?Score actuel(?:\*\*)?\s*[:\-]\s*(\d+)", re.I | re.M),
    "new_score":     re.compile(r"^\s*(?:\*\*)?Score proposé(?:\*\*)?\s*[:\-]\s*(\d+)", re.I | re.M),
}


def fetch_open_issues(repo: str = DEFAULT_REPO,
                      label: str | None = None) -> list[dict]:
    """Liste les issues ouvertes via `gh issue list ... --json ...`."""
    cmd = ["gh", "issue", "list", "--repo", repo, "--state", "open",
           "--json", "number,title,body,labels,url,author", "--limit", "100"]
    if label:
        cmd += ["--label", label]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=60, check=True)
        return json.loads(r.stdout or "[]")
    except subprocess.CalledProcessError as e:
        print(f"  gh error : {e.stderr[:300]}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"  gh error : {e}", file=sys.stderr)
        return []


def parse_source_suggestion(issue: dict) -> dict:
    """Extrait url, label, type, justification d'un body d'issue."""
    body = issue.get("body") or ""
    parsed: dict = {"issue_number": issue.get("number"),
                    "issue_url": issue.get("url"),
                    "title": issue.get("title", "")}
    for field, regex in _ISSUE_TPL_FIELDS.items():
        m = regex.search(body)
        if m:
            parsed[field] = m.group(1).strip()
    # Fallback : 1re URL trouvée si rien d'extrait
    if "url" not in parsed:
        urls = _URL_RE.findall(body)
        # filtre URLs github.com/issues etc.
        urls = [u for u in urls if "github.com" not in u]
        if urls:
            parsed["url"] = urls[0]
    return parsed


def probe_and_score(url: str) -> dict:
    """Lance scripts/probe_source.py <url> sans --id, parse stdout."""
    script = Path(__file__).parent / "probe_source.py"
    try:
        r = subprocess.run(
            [sys.executable, str(script), url],
            capture_output=True, text=True, timeout=60,
        )
        return {
            "ok": r.returncode == 0,
            "stdout": r.stdout,
            "stderr": r.stderr,
            "exit_code": r.returncode,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _comment_issue(repo: str, issue_number: int, comment_body: str) -> bool:
    """Ajoute un commentaire à l'issue via `gh issue comment`."""
    try:
        subprocess.run(
            ["gh", "issue", "comment", str(issue_number),
             "--repo", repo, "--body", comment_body],
            capture_output=True, text=True, timeout=30, check=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"  comment failed #{issue_number}: {e.stderr[:200]}",
              file=sys.stderr)
        return False


# ── Helpers candidates.yml + feedback.json ───────────────────────────────────
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


def _append_feedback(feedback_path: Path, entry: dict, kind: str) -> None:
    fb = {"corrections": [], "suggested_sources": []}
    if feedback_path.exists():
        fb = json.loads(feedback_path.read_text(encoding="utf-8")) or fb
    fb.setdefault(kind, []).append(entry)
    feedback_path.write_text(
        json.dumps(fb, ensure_ascii=False, indent=2), encoding="utf-8")


def run(repo: str = DEFAULT_REPO,
        candidates_path: Path | None = None,
        feedback_path: Path | None = None,
        report_path: Path | None = None) -> dict:
    """Pipeline : fetch issues, probe sources, ajoute candidats + feedback."""
    root = Path(__file__).parent.parent
    candidates_path = candidates_path or root / "discovery" / "candidates.yml"
    feedback_path = feedback_path or root / "feedback.json"
    report_path = report_path or (
        root / "discovery" / "reports"
        / f"review_issues_{datetime.now().strftime('%Y-%m-%d')}.md")

    source_issues = fetch_open_issues(repo, label="nouvelle-source")
    fix_issues = fetch_open_issues(repo, label="correction-scoring")

    cands = _load_candidates(candidates_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    report_lines = [f"# Triage issues — {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
    sources_added = 0
    corrections_added = 0

    # ── Nouvelles sources ──────────────────────────────────────────────
    report_lines += [f"## Nouvelles sources ({len(source_issues)})", ""]
    for issue in source_issues:
        parsed = parse_source_suggestion(issue)
        url = parsed.get("url")
        if not url:
            report_lines.append(
                f"- #{issue['number']} « {issue['title'][:60]} » → "
                "**pas d'URL extraite**")
            continue
        probe = probe_and_score(url)
        cand = {
            "url": url,
            "type": "community_suggestion",
            "source_type": parsed.get("type", "html"),
            "label": parsed.get("label"),
            "justification": parsed.get("justification"),
            "issue_number": issue.get("number"),
            "issue_url": issue.get("url"),
            "probe_ok": probe.get("ok"),
            "discovered_at": now_iso,
        }
        if _merge_candidate(cands, cand):
            sources_added += 1
        # Commente l'issue avec le rapport probe (≤4000 chars pour gh)
        comment = (
            "## Rapport probe automatique\n\n"
            f"```\n{(probe.get('stdout') or probe.get('error') or '')[:3000]}\n```\n\n"
            f"Candidat ajouté à `discovery/candidates.yml` "
            f"(type `community_suggestion`).\nIssue laissée ouverte pour décision."
        )
        _comment_issue(repo, issue["number"], comment)
        report_lines.append(
            f"- #{issue['number']} {url} → probe "
            f"{'OK' if probe.get('ok') else 'KO'}")

    # ── Corrections de scoring ─────────────────────────────────────────
    report_lines += ["", f"## Corrections scoring ({len(fix_issues)})", ""]
    for issue in fix_issues:
        parsed = parse_source_suggestion(issue)
        entry = {
            "issue_number": issue.get("number"),
            "issue_url": issue.get("url"),
            "doc_url": parsed.get("doc_url") or parsed.get("url"),
            "old_score": parsed.get("old_score"),
            "new_score": parsed.get("new_score"),
            "justification": parsed.get("justification"),
            "received_at": now_iso,
        }
        _append_feedback(feedback_path, entry, "corrections")
        corrections_added += 1
        report_lines.append(
            f"- #{issue['number']} {entry.get('doc_url', '?')} "
            f"→ {entry.get('old_score')} → {entry.get('new_score')}")
        _comment_issue(
            repo, issue["number"],
            "Correction enregistrée dans `feedback.json`. "
            "Elle sera prise en compte au prochain réajustement du scoreur.")

    _save_candidates(candidates_path, cands)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    return {
        "sources_added": sources_added,
        "corrections_added": corrections_added,
        "source_issues_seen": len(source_issues),
        "fix_issues_seen": len(fix_issues),
        "report": str(report_path),
    }


if __name__ == "__main__":
    out = run()
    print(json.dumps(out, ensure_ascii=False, indent=2))

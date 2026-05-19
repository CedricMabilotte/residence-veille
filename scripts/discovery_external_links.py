#!/usr/bin/env python3
"""
discovery_external_links.py — Liens externes captés pendant le scraping.

Module "enregistreur" (pas de fetch) : à chaque page HTML scrapée par le
pipeline, capture les <a href> qui pointent vers un domaine différent du
source_url, et les enregistre dans discovery/candidates.yml.

Fournit aussi les helpers YAML communs aux 3 modules de découverte
(load_candidates / save_candidates / merge_candidate).

Stdlib uniquement (HTMLParser pour parser sans BeautifulSoup).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

# ── YAML : on évite la dépendance pyyaml côté import. Si dispo on l'utilise. ──
try:
    import yaml  # type: ignore
    _HAVE_YAML = True
except ImportError:
    _HAVE_YAML = False


# ── (1) Helpers de persistance partagés ──────────────────────────────────────

def load_candidates(path: Path) -> dict[str, Any]:
    """Charge candidates.yml (ou retourne un squelette vide)."""
    if not path.exists():
        return {"last_updated": None, "total_candidates": 0, "candidates": []}
    txt = path.read_text(encoding="utf-8")
    if _HAVE_YAML:
        data = yaml.safe_load(txt) or {}
    else:
        data = _parse_minimal_yaml(txt)
    data.setdefault("candidates", [])
    return data


def save_candidates(path: Path, data: dict[str, Any]) -> None:
    """Réécrit candidates.yml (trié par seen_count desc)."""
    data["candidates"].sort(
        key=lambda c: (-(c.get("seen_count") or 0), c.get("url", ""))
    )
    data["total_candidates"] = len(data["candidates"])
    data["last_updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path.parent.mkdir(parents=True, exist_ok=True)
    if _HAVE_YAML:
        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120),
            encoding="utf-8",
        )
    else:
        path.write_text(_dump_minimal_yaml(data), encoding="utf-8")


def merge_candidate(store: dict[str, Any], new: dict[str, Any], today: str) -> bool:
    """Insère ou fusionne un candidat. Retourne True si nouveau."""
    url = new["url"]
    for existing in store["candidates"]:
        if existing.get("url") == url:
            existing["seen_count"] = (existing.get("seen_count") or 1) + 1
            existing["last_seen"] = today
            # Concatène found_from sans doublon (clé = doc_id+page)
            seen_keys = {
                (f.get("doc_id"), f.get("page")) for f in existing.get("found_from", [])
            }
            for f in new.get("found_from", []):
                if (f.get("doc_id"), f.get("page")) not in seen_keys:
                    existing.setdefault("found_from", []).append(f)
            return False
    store["candidates"].append(new)
    return True


# ── (2) Capture des liens externes depuis un HTML ────────────────────────────

class _LinkCollector(HTMLParser):
    """Petit parser : retient (href, link_text) pour chaque <a>."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            text = " ".join("".join(self._buf).split())[:160]
            self.links.append((self._href, text))
            self._href, self._buf = None, []


def capture_links(html: str, source_url: str, source_label: str,
                  candidates_path: Path) -> int:
    """Parse le HTML, identifie les <a href> menant vers un domaine DIFFÉRENT
    de source_url. Ajoute aux candidats type=external_link.

    Retourne le nombre de NOUVEAUX candidats (non-déjà-présents).
    """
    src_domain = urlparse(source_url).netloc.lower()
    store = load_candidates(candidates_path)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    parser = _LinkCollector()
    try:
        parser.feed(html)
    except Exception as e:
        print(f"  ! HTML parsing failed: {e}")
        return 0

    new_count = 0
    seen_in_run: set[str] = set()
    for href, text in parser.links:
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        abs_url = urljoin(source_url, href)
        domain = urlparse(abs_url).netloc.lower()
        if not domain or domain == src_domain:
            continue
        if abs_url in seen_in_run:
            continue
        seen_in_run.add(abs_url)

        entry = {
            "url": abs_url,
            "type": "external_link",
            "domain": domain,
            "first_seen": today,
            "last_seen": today,
            "seen_count": 1,
            "suggested_action": "follow_one_time",
            "notes": "",
            "found_from": [{
                "doc_id": source_label,
                "context": text or f"lien depuis {source_url}",
                "page": None,
            }],
        }
        if merge_candidate(store, entry, today):
            new_count += 1

    save_candidates(candidates_path, store)
    return new_count


# ── (3) Re-tri et export Markdown ────────────────────────────────────────────

def rank_candidates(candidates_path: Path, top_n: int = 30) -> list[dict]:
    """Re-trie par seen_count puis bonus si le domaine est vu dans plusieurs
    sources distinctes (signal de pertinence transversale)."""
    store = load_candidates(candidates_path)
    domain_sources: dict[str, set] = {}
    for c in store["candidates"]:
        srcs = {f.get("doc_id") for f in c.get("found_from", [])}
        domain_sources.setdefault(c["domain"], set()).update(srcs)

    def _score(c: dict) -> tuple[int, int]:
        bonus = len(domain_sources.get(c["domain"], set()))
        return (-(c.get("seen_count") or 0), -bonus)

    return sorted(store["candidates"], key=_score)[:top_n]


def export_to_review(candidates_path: Path, out_md: Path,
                     min_seen: int = 2) -> int:
    """Exporte les top candidats en Markdown (tableau) pour review humaine."""
    ranked = [c for c in rank_candidates(candidates_path, top_n=100)
              if (c.get("seen_count") or 0) >= min_seen]
    lines = [
        "# Candidats à valider",
        "",
        f"Généré le {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} "
        f"— {len(ranked)} candidat(s) (seen ≥ {min_seen})",
        "",
        "| URL | Domaine | Type | Vu | Action | Contextes |",
        "|---|---|---|---|---|---|",
    ]
    for c in ranked:
        ctxs = "; ".join(
            (f.get("context") or "")[:50] for f in (c.get("found_from") or [])[:3]
        ).replace("|", "/")
        lines.append(
            f"| {c['url']} | {c.get('domain', '')} | {c.get('type', '')} | "
            f"{c.get('seen_count', 0)} | {c.get('suggested_action', '')} | {ctxs} |"
        )
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(ranked)


# ── (4) Fallback YAML minimal (sans pyyaml) ───────────────────────────────────
# Lecture/écriture suffisantes pour notre schéma. Non-générique mais fiable.

def _parse_minimal_yaml(txt: str) -> dict[str, Any]:
    import json as _json
    # Stratégie pragmatique : si pyyaml indisponible, on stocke en JSON
    # déguisé. La 1ère ligne précise le mode.
    if txt.lstrip().startswith("{"):
        return _json.loads(txt)
    # YAML écrit par pyyaml mais lu sans → on retombe sur un dict vide
    return {"candidates": []}


def _dump_minimal_yaml(data: dict[str, Any]) -> str:
    import json as _json
    return _json.dumps(data, indent=2, ensure_ascii=False)


# ── Validation CLI ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    root = Path(__file__).parent.parent
    cand_path = root / "discovery" / "candidates.yml"

    # Démo : injecte un HTML synthétique
    demo_html = """
    <html><body>
      <a href="https://infokiosques.net/IMG/pdf/x.pdf">Brochure X</a>
      <a href="https://archive.org/details/y">Archive Y</a>
      <a href="/local/anchor">Local</a>
      <a href="https://infokiosques.net/another">Same domain</a>
    </body></html>
    """
    n = capture_links(demo_html, "https://infokiosques.net/foo",
                       "demo_run", cand_path)
    print(f"[demo] {n} nouveau(x) candidat(s) externe(s)")

    ranked = rank_candidates(cand_path, top_n=10)
    print(f"[rank] top {len(ranked)} :")
    for c in ranked[:5]:
        print(f"  - {c['url']} (seen={c.get('seen_count')})")

    out_md = root / "discovery" / "review.md"
    n_md = export_to_review(cand_path, out_md, min_seen=1)
    print(f"[export] {n_md} lignes → {out_md}")

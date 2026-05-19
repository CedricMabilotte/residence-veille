#!/usr/bin/env python3
"""Génère un digest hebdo des fiches scorées >= seuil et l'envoie (ou sauvegarde HTML)."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PALETTE = {
    "bg": "#f6efe4",      # crème
    "ink": "#3a2a1a",     # encre terre
    "accent": "#a8542a",  # terracotta
    "muted": "#7a6a55",
}


def _parse_run_date(s: str) -> datetime | None:
    """Parse une date au format 'YYYY-MM-DD_HH-MM' (tolérant)."""
    try:
        return datetime.strptime(s, "%Y-%m-%d_%H-%M")
    except Exception:
        return None


def _short_summary(doc: dict, max_chars: int = 280) -> str:
    """Récupère un résumé court depuis bulle/enrichment."""
    bulle_path = doc.get("bulle")
    if bulle_path:
        p = ROOT / bulle_path
        if p.exists():
            try:
                b = json.loads(p.read_text(encoding="utf-8"))
                t = b.get("teaser") or b.get("abstract_editorial", "")
                return (t[:max_chars] + "…") if len(t) > max_chars else t
            except Exception:
                pass
    enr = doc.get("enrichment", {}) or {}
    s = enr.get("summary", "") or doc.get("runs", [{}])[-1].get("raison", "")
    return (s[:max_chars] + "…") if len(s) > max_chars else s


def build_digest(catalog_path: Path, since_days: int = 7, min_score: int = 8) -> dict:
    """Construit le digest : sélectionne les docs scorés >= min_score vus depuis since_days."""
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    cutoff = datetime.now() - timedelta(days=since_days)
    items: list[dict[str, Any]] = []
    for doc in catalog.get("docs", {}).values():
        if int(doc.get("latest_score", 0)) < min_score:
            continue
        d = _parse_run_date(doc.get("latest_run", "") or doc.get("first_seen", ""))
        if d is None or d < cutoff:
            continue
        bulle = {}
        if doc.get("bulle"):
            bp = ROOT / doc["bulle"]
            if bp.exists():
                try:
                    bulle = json.loads(bp.read_text(encoding="utf-8"))
                except Exception:
                    bulle = {}
        items.append({
            "title": bulle.get("titre_accroche") or doc.get("meta", {}).get("pdf_title") or doc.get("filename", ""),
            "source": doc.get("source", ""),
            "score": doc.get("latest_score", 0),
            "summary_short": _short_summary(doc),
            "url": doc.get("url", ""),
            "cover": doc.get("cover", ""),
        })
    items.sort(key=lambda x: x["score"], reverse=True)
    digest = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "count": len(items),
        "items": items,
    }
    digest["html_body"] = _render_html(digest)
    digest["plain_body"] = _render_plain(digest)
    return digest


def _render_html(digest: dict) -> str:
    """Construit un HTML mailable avec styles inline."""
    p = PALETTE
    cards = []
    for it in digest["items"]:
        cover_html = ""
        if it["cover"]:
            cover_html = f'<img src="{it["cover"]}" alt="" style="width:100%;max-height:200px;object-fit:cover;border-radius:4px;margin-bottom:12px;">'
        cards.append(f"""
        <article style="background:#fff;border:1px solid {p['muted']}33;border-radius:6px;padding:20px;margin-bottom:18px;">
          {cover_html}
          <div style="font-size:12px;color:{p['muted']};letter-spacing:.05em;text-transform:uppercase;">{it['source']} — {it['score']}/10</div>
          <h2 style="font-family:'EB Garamond',Georgia,serif;font-size:22px;color:{p['ink']};margin:8px 0 12px;">{it['title']}</h2>
          <p style="font-family:Georgia,serif;color:{p['ink']};line-height:1.6;font-size:15px;">{it['summary_short']}</p>
          <p><a href="{it['url']}" style="color:{p['accent']};text-decoration:none;font-weight:600;">Lire le document &rarr;</a></p>
        </article>""")
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<title>Digest hebdo — biblio.actitude.org</title>
<style>body{{margin:0;padding:0;background:{p['bg']};}}</style></head>
<body style="background:{p['bg']};margin:0;padding:24px;font-family:Georgia,serif;color:{p['ink']};">
  <div style="max-width:680px;margin:0 auto;">
    <header style="text-align:center;padding:24px 0;border-bottom:1px solid {p['muted']}33;margin-bottom:24px;">
      <h1 style="font-family:'EB Garamond',Georgia,serif;font-size:32px;color:{p['ink']};margin:0;">Bibliothèque vivante</h1>
      <p style="color:{p['muted']};margin:6px 0 0;">Digest du {digest['date']} — {digest['count']} nouvelle(s) fiche(s)</p>
    </header>
    {''.join(cards) if cards else '<p style="text-align:center;color:'+p['muted']+';">Pas de nouvelle fiche cette semaine.</p>'}
    <footer style="text-align:center;color:{p['muted']};font-size:12px;padding:24px 0;border-top:1px solid {p['muted']}33;margin-top:24px;">
      <a href="https://biblio.actitude.org" style="color:{p['accent']};">biblio.actitude.org</a>
    </footer>
  </div>
</body></html>"""


def _render_plain(digest: dict) -> str:
    """Version texte brut du digest."""
    lines = [f"Bibliothèque vivante — Digest du {digest['date']}",
             f"{digest['count']} nouvelle(s) fiche(s) >= seuil", ""]
    for it in digest["items"]:
        lines += [f"[{it['score']}/10] {it['title']}",
                  f"  Source : {it['source']}",
                  f"  {it['summary_short']}",
                  f"  -> {it['url']}", ""]
    return "\n".join(lines)


def send_via_brevo(digest: dict, to_email: str, api_key: str) -> bool:
    """Envoie le digest via l'API Brevo."""
    try:
        import requests
    except ImportError:
        print("[newsletter] requests indisponible — envoi impossible", file=sys.stderr)
        return False
    payload = {
        "sender": {"name": "Bibliothèque vivante", "email": "noreply@actitude.org"},
        "to": [{"email": to_email}],
        "subject": f"Digest biblio — {digest['date']} — {digest['count']} fiche(s)",
        "htmlContent": digest["html_body"],
        "textContent": digest["plain_body"],
    }
    try:
        r = requests.post("https://api.brevo.com/v3/smtp/email",
                          headers={"api-key": api_key, "content-type": "application/json"},
                          json=payload, timeout=20)
        return r.status_code in (200, 201)
    except Exception as e:
        print(f"[newsletter] erreur Brevo: {e}", file=sys.stderr)
        return False


def save_html(digest: dict, out_path: Path) -> None:
    """Sauvegarde le HTML autonome."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(digest["html_body"], encoding="utf-8")


if __name__ == "__main__":
    # Validation : génère le digest sur le catalog existant et écrit le HTML.
    catalog = ROOT / "synopsis" / "catalog.json"
    if not catalog.exists():
        print(f"[newsletter] catalog introuvable: {catalog}", file=sys.stderr)
        sys.exit(1)
    digest = build_digest(catalog, since_days=30, min_score=8)
    out = ROOT / "dist" / "newsletter" / f"digest_{digest['date']}.html"
    save_html(digest, out)
    print(f"[newsletter] {digest['count']} fiche(s) — HTML écrit dans {out}")
    api_key = os.getenv("BREVO_API_KEY")
    to = os.getenv("NEWSLETTER_TO")
    if api_key and to:
        ok = send_via_brevo(digest, to, api_key)
        print(f"[newsletter] envoi Brevo: {'ok' if ok else 'échec'}")
    else:
        print("[newsletter] BREVO_API_KEY / NEWSLETTER_TO absents — envoi sauté")

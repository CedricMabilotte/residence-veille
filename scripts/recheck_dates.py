#!/usr/bin/env python3
"""
recheck_dates.py — Qualifier les fiches sans date limite (statut `indetermine`).

Chantier « candidature continue » (décision L3 d'août 2026, validé par Ced le
2026-11-18). Au 18 novembre, 30 fiches sur 38 étaient `indetermine` : le
catalogue ne pouvait pas distinguer une date manquante par erreur d'extraction,
un appel au fil de l'eau, une édition annuelle à venir, ou une page qui n'est
pas un appel (article sur les lauréats, édition passée).

Pour chaque fiche `indetermine` (les jamais re-vérifiées d'abord, puis les plus
anciennes), on relit la page source et on pose à Claude UNE question ciblée,
d'où un seul appel par fiche — budget par run : RECHECK_DATES_MAX (défaut 10).

Résultat appliqué à la fiche :
  - date_limite trouvée      → candidature.date_limite (+ precision)
  - candidature_continue     → candidature.candidature_continue = true
                               (deadline_tracker → statut `ouverte-continue`)
  - prochaine_edition        → candidature.prochaine_edition = "2027" / "2027-03"
                               (deadline_tracker → statut `edition-a-venir`)
  - pas_un_appel (conf ≥ .7) → fiche déplacée vers discovery/quarantine/{type}/
                               (jamais supprimée, convention L1)
  - rien trouvé              → reste `indetermine`, _meta.date_recheck daté
Puis deadline_tracker.py recalcule les statuts (étape suivante du workflow).

Variables d'env : RECHECK_DATES_MAX, DRY_RUN, CLAUDE_CODE_OAUTH_TOKEN.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import claude_guard  # noqa: E402
from extract_opportunity import CLAUDE_MODEL, CLAUDE_FLAGS  # noqa: E402

APPELS_DIR = ROOT / "appels"
QUARANTINE_DIR = ROOT / "discovery" / "quarantine"
REPORTS_DIR = ROOT / "reports"

DRY_RUN = os.getenv("DRY_RUN", "").lower() == "true"
MAX_FICHES = int(os.getenv("RECHECK_DATES_MAX") or 10)
CLAUDE_TIMEOUT_SEC = 90
MAX_BODY_CHARS = 12000

PROMPT = """Tu lis la page d'une opportunité artistique (résidence, bourse, prix ou appel à exposition)
pour répondre à UNE question : quand peut-on candidater ?

Réponds UNIQUEMENT par un objet JSON valide, sans markdown ni prose, avec EXACTEMENT ces champs :
{{
  "date_limite": "YYYY-MM-DD ou null",
  "date_limite_precision": "day | month | null",
  "candidature_continue": true/false,
  "prochaine_edition": "YYYY ou YYYY-MM ou null",
  "pas_un_appel": true/false,
  "confiance": 0.0-1.0,
  "indice": "la phrase exacte de la page qui justifie ta réponse, ou null"
}}

Règles :
- date_limite : la date de clôture des candidatures POUR UNE ÉDITION ENCORE OUVERTE à la date
  d'aujourd'hui ({today}). Une date passée n'est pas une date limite : mets null et, si la page
  annonce une prochaine édition, renseigne prochaine_edition.
- Si seul un mois est donné, prends le 1er du mois et precision = "month".
- candidature_continue = true seulement si la page dit explicitement que l'on peut candidater
  à tout moment / au fil de l'eau / « rolling » / « ongoing » / « en continu ».
- pas_un_appel = true si la page n'est PAS un appel à candidature : annonce des lauréats,
  compte rendu d'une édition passée, article de presse, page de présentation générale sans
  modalités de candidature, boutique, programme d'exposition.
- N'invente RIEN. Doute → null et confiance basse.

Titre : {title}
URL : {url}

Texte de la page :
\"\"\"
{body}
\"\"\"
"""


def _call_claude(prompt: str) -> dict:
    claude_guard.guard_before_call()
    result = subprocess.run(
        ["claude", "-p", prompt, "--model", CLAUDE_MODEL] + CLAUDE_FLAGS,
        capture_output=True, text=True, timeout=CLAUDE_TIMEOUT_SEC,
        cwd="/tmp", stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        claude_guard.check_result(result.stdout, result.stderr)
        raise RuntimeError(f"claude exit {result.returncode} — {result.stderr[:200]}")
    raw = result.stdout.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]
    return json.loads(raw.strip())


_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _html_to_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return soup.get_text(" ", strip=True)
    except Exception:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _fetch(url: str) -> str:
    """Page source, texte brut. Fetch DIRECT (pas le cache .cache/pages de watch.py :
    au premier passage du 2026-11-18, 7 fiches sur 10 ont lu une entrée de cache
    vide laissée par la veille du même run — « page illisible (0 chars) »).
    Repli Playwright quand le HTML statique est vide ou trop court (pages rendues
    en JS, murs anti-bot)."""
    text = ""
    try:
        import requests
        r = requests.get(url, timeout=30, allow_redirects=True,
                         headers={"User-Agent": _UA, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8,es;q=0.7"})
        if r.ok and "text/html" in (r.headers.get("Content-Type") or ""):
            text = _html_to_text(r.text)
    except Exception:
        text = ""
    if len(text) >= 400:
        return text
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            try:
                page = browser.new_context(user_agent=_UA).new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(1800)
                html = page.content()
            finally:
                browser.close()
        pw_text = _html_to_text(html)
        if len(pw_text) > len(text):
            text = pw_text
    except Exception:
        pass
    return text


def _iso_date(s) -> str | None:
    if not s or not isinstance(s, str):
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if not m:
        return None
    try:
        _dt.date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None
    return s[:10]


def candidates() -> list[Path]:
    """Fiches `indetermine`, jamais re-vérifiées d'abord, puis par ancienneté de
    la dernière vérification."""
    out = []
    for p in APPELS_DIR.rglob("*.yml"):
        try:
            f = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if f.get("status") != "indetermine":
            continue
        last = ((f.get("_meta") or {}).get("date_recheck") or {}).get("at") or ""
        out.append((last, p))
    out.sort(key=lambda t: t[0])
    return [p for _, p in out]


def apply(fiche: dict, res: dict, path: Path, today: str) -> str:
    """Applique le résultat ; retourne l'issue (texte court pour le rapport)."""
    cand = fiche.setdefault("candidature", {}) or {}
    fiche["candidature"] = cand
    meta = fiche.setdefault("_meta", {})
    conf = float(res.get("confiance") or 0)
    meta["date_recheck"] = {
        "at": today, "by": "recheck_dates.py", "confiance": conf,
        "indice": (res.get("indice") or None),
    }

    if res.get("pas_un_appel") and conf >= 0.7:
        meta["quarantine_reason"] = "pas un appel à candidature (re-vérification des dates)"
        meta["quarantined_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
        meta["quarantined_by"] = "recheck_dates.py"
        dest = QUARANTINE_DIR / fiche.get("type", "autre") / path.name
        if not DRY_RUN:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(yaml.safe_dump(fiche, allow_unicode=True, sort_keys=False, width=120),
                            encoding="utf-8")
            path.unlink()
        return "quarantaine (pas un appel)"

    dl = _iso_date(res.get("date_limite"))
    issue = "inchangé"
    if dl and dl >= today:
        cand["date_limite"] = dl
        if res.get("date_limite_precision") in ("day", "month"):
            cand["date_limite_precision"] = res["date_limite_precision"]
        issue = f"date limite {dl}"
    elif res.get("candidature_continue") and conf >= 0.6:
        cand["candidature_continue"] = True
        issue = "candidature continue"
    elif isinstance(res.get("prochaine_edition"), str) and re.match(r"^\d{4}(-\d{2})?$", res["prochaine_edition"]):
        cand["prochaine_edition"] = res["prochaine_edition"]
        issue = f"prochaine édition {res['prochaine_edition']}"

    if not DRY_RUN:
        path.write_text(yaml.safe_dump(fiche, allow_unicode=True, sort_keys=False, width=120),
                        encoding="utf-8")
    return issue


def main():
    today = _dt.date.today().isoformat()
    todo = candidates()
    print(f"→ {len(todo)} fiche(s) indéterminée(s), budget {MAX_FICHES} ce run (DRY_RUN={DRY_RUN})")
    records = []
    for path in todo[:MAX_FICHES]:
        fiche = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        title = (fiche.get("opportunite") or {}).get("nom") or path.stem
        url = fiche.get("source_url") or ""
        print(f"  · {title[:70]}")
        if claude_guard.session_limit_active():
            print("    ⏸  limite Claude — arrêt")
            break
        is_pdf = ".pdf" in url.lower()
        body = "" if is_pdf else (_fetch(url)[:MAX_BODY_CHARS] if url else "")
        if len(body) < 200:
            why = "source PDF (non relue)" if is_pdf else "page illisible"
            print(f"    ↳ {why} ({len(body)} chars) — reporté")
            fiche.setdefault("_meta", {})["date_recheck"] = {"at": today, "by": "recheck_dates.py",
                                                             "erreur": why}
            if not DRY_RUN:
                path.write_text(yaml.safe_dump(fiche, allow_unicode=True, sort_keys=False, width=120),
                                encoding="utf-8")
            records.append({"uid": fiche.get("uid"), "issue": why})
            continue
        try:
            res = _call_claude(PROMPT.format(today=today, title=title, url=url, body=body))
        except Exception as e:
            print(f"    ↳ ✗ Claude : {str(e)[:120]}")
            records.append({"uid": fiche.get("uid"), "issue": f"erreur: {str(e)[:80]}"})
            continue
        issue = apply(fiche, res, path, today)
        print(f"    ↳ {issue} (confiance {res.get('confiance')})")
        records.append({"uid": fiche.get("uid"), "titre": title, "issue": issue,
                        "confiance": res.get("confiance"), "indice": res.get("indice")})

    if not DRY_RUN and records:
        REPORTS_DIR.mkdir(exist_ok=True)
        out = REPORTS_DIR / f"recheck_dates_{today}.json"
        out.write_text(json.dumps({"date": today, "n_candidates": len(todo), "records": records},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ {len(records)} fiche(s) traitée(s), {len(todo) - len(records)} restante(s)")


if __name__ == "__main__":
    main()

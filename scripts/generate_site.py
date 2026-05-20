#!/usr/bin/env python3
"""
generate_site.py — Génère le site public « Résidence » à partir des fiches YAML.

Architecture (validée avec l'utilisateur) :
  - Catalogue unifié à facettes + recherche plein texte         → index.html
  - Fiche-item HTML dédiée par opportunité (orientée analyse)    → o/{uid}.html
  - Annuaire d'organismes                                        → organismes.html
  - Fiche organisme                                              → organisme/{slug}/
  - Archive consultable                                          → archive.html
  - À propos / Suggérer une source                               → a-propos.html, suggerer.html
  - Flux RSS ×5, calendar.ics, sitemap.xml, data.json, robots.txt, favicon.svg

Registre visuel : éditorial / revue. Tous les champs préfixés '_' sont
strippés (le bias profil interne n'est jamais publié).
"""

from __future__ import annotations

import datetime as _dt
import html
import json
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

import yaml

ROOT = Path(__file__).resolve().parent.parent
APPELS_DIR = ROOT / "appels"
ARCHIVE_DIR = ROOT / "archive"
ORGANISMES_DIR = ROOT / "organismes"
CRITERES_PATH = ROOT / "config" / "criteres.yml"
SITE_DIR = ROOT / "site"

TYPES = ["residence", "bourse", "prix", "exposition"]
TYPE_LABEL_FR = {
    "residence": "Résidence", "bourse": "Bourse",
    "prix": "Prix", "exposition": "Appel à exposition",
}
RSS_FILE = {"residence": "residences", "bourse": "bourses", "prix": "prix", "exposition": "expositions"}

# Endpoint du formulaire de suggestion (service tiers). À renseigner :
# créer un formulaire sur https://formspree.io et coller l'ID ci-dessous.
FORMSPREE_ID = "VOTRE_ID_FORMSPREE"
CONTACT_MAIL = "cedric.mabilotte@gmail.com"

# ─────────────────────────────────────────────────────────────────────────────
# CSS — registre éditorial / revue
# ─────────────────────────────────────────────────────────────────────────────
CSS = """
:root {
  --ink: #211d18; --muted: #6b6256; --faint: #978c7d;
  --paper: #f4f1e8; --card: #fffdf8; --line: #ddd5c4;
  --accent: #bc4c3a; --accent-dk: #8f3829; --gold: #b08431;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
  color: var(--ink); background: var(--paper); line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 1060px; margin: 0 auto; padding: 0 1.3rem 5rem; }
a { color: var(--accent-dk); }
a:hover { color: var(--accent); }

/* En-tête / masthead */
.masthead { border-bottom: 2px solid var(--ink); margin-bottom: .2rem; padding: 1.6rem 0 1rem; }
.masthead .brand { display: flex; align-items: baseline; gap: .8rem; text-decoration: none; color: var(--ink); }
.logo-mark {
  font-size: 1.9rem; font-weight: 700; letter-spacing: -.02em;
  border: 2px solid var(--accent); color: var(--accent);
  padding: .05rem .5rem; border-radius: 4px; line-height: 1;
}
.brand h1 { font-size: 1.75rem; margin: 0; font-weight: 700; letter-spacing: -.01em; }
.brand .baseline { font-size: .9rem; color: var(--muted); font-style: italic; }
.topnav { display: flex; gap: 1.4rem; flex-wrap: wrap; font-size: .92rem;
          font-family: -apple-system, system-ui, sans-serif; padding: .7rem 0 0; }
.topnav a { text-decoration: none; color: var(--muted); }
.topnav a:hover, .topnav a.active { color: var(--accent); }

/* Titres de section */
h2.sec { font-size: 1.05rem; font-family: -apple-system, system-ui, sans-serif;
         text-transform: uppercase; letter-spacing: .08em; color: var(--muted);
         border-bottom: 1px solid var(--line); padding-bottom: .35rem; margin: 2.4rem 0 1rem; }
h3 { font-size: 1.15rem; margin: 1.4rem 0 .5rem; }

/* Barre de filtres */
.toolbar { display: flex; gap: .8rem; flex-wrap: wrap; align-items: center;
           margin: 1.4rem 0; font-family: -apple-system, system-ui, sans-serif; }
.toolbar input, .toolbar select {
  font: inherit; font-size: .9rem; padding: .45rem .6rem;
  border: 1px solid var(--line); border-radius: 5px; background: var(--card); color: var(--ink);
}
.toolbar input[type=search] { flex: 1; min-width: 200px; }
.toolbar .count { color: var(--faint); font-size: .85rem; margin-left: auto; }

/* Catalogue : cartes */
.cards { list-style: none; padding: 0; margin: 0; display: grid; gap: .9rem; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 7px;
        padding: 1.1rem 1.3rem; transition: box-shadow .15s, border-color .15s; }
.card:hover { border-color: var(--accent); box-shadow: 0 3px 14px rgba(33,29,24,.07); }
.card .row1 { display: flex; gap: .6rem; align-items: center; flex-wrap: wrap;
              font-family: -apple-system, system-ui, sans-serif; }
.tag { font-size: .7rem; text-transform: uppercase; letter-spacing: .07em; font-weight: 600;
       padding: .18rem .55rem; border-radius: 3px; background: var(--ink); color: var(--paper); }
.tag.residence { background: #3b5b6b; }
.tag.bourse    { background: #6b5b3b; }
.tag.prix      { background: var(--accent); }
.tag.exposition{ background: #5b3b5b; }
.deadline { font-size: .85rem; color: var(--accent); font-weight: 600;
            font-family: -apple-system, system-ui, sans-serif; }
.card.indetermine .deadline { color: var(--faint); font-weight: normal; font-style: italic; }
.card h3 { margin: .5rem 0 .3rem; font-size: 1.18rem; line-height: 1.3; }
.card h3 a { text-decoration: none; color: var(--ink); }
.card h3 a:hover { color: var(--accent); }
.card .meta { font-size: .9rem; color: var(--muted);
              font-family: -apple-system, system-ui, sans-serif; }
.card .meta a { color: var(--muted); }
.score-pill { font-family: -apple-system, system-ui, sans-serif; font-size: .78rem;
              font-weight: 700; color: var(--gold); border: 1px solid var(--gold);
              border-radius: 20px; padding: .1rem .5rem; }

/* Fiche-item */
.fiche-head { margin: 1.5rem 0 1rem; }
.fiche-head h2 { font-size: 1.9rem; margin: .5rem 0 .4rem; line-height: 1.25; }
.fiche-head .sub { color: var(--muted); font-family: -apple-system, system-ui, sans-serif; font-size: .95rem; }
.enbref { background: var(--card); border: 1px solid var(--line); border-radius: 7px;
          padding: 1rem 1.3rem; margin: 1.2rem 0;
          font-family: -apple-system, system-ui, sans-serif; font-size: .92rem; }
.enbref dl { display: grid; grid-template-columns: max-content 1fr; gap: .35rem 1.2rem; margin: 0; }
.enbref dt { color: var(--faint); }
.enbref dd { margin: 0; }
.prose p { margin: .6rem 0; }
table.crit { width: 100%; border-collapse: collapse; font-size: .92rem;
             font-family: -apple-system, system-ui, sans-serif; }
table.crit td, table.crit th { border-bottom: 1px solid var(--line); padding: .5rem .4rem; text-align: left; vertical-align: top; }
table.crit th { color: var(--faint); font-weight: 600; font-size: .82rem; text-transform: uppercase; letter-spacing: .05em; }
.crit-oui { color: #4a7a3a; font-weight: 600; }
.crit-non { color: var(--faint); }
.crit-partiel { color: var(--gold); font-weight: 600; }
.crit-inconnu { color: var(--faint); font-style: italic; }
.asavoir { background: #fbf3e7; border-left: 3px solid var(--gold); border-radius: 4px;
           padding: .8rem 1.1rem; margin: 1rem 0; font-family: -apple-system, system-ui, sans-serif; font-size: .9rem; }
.asavoir ul { margin: .3rem 0; padding-left: 1.2rem; }
.cta { display: inline-block; background: var(--accent); color: var(--paper);
       text-decoration: none; padding: .6rem 1.2rem; border-radius: 5px; font-weight: 600;
       font-family: -apple-system, system-ui, sans-serif; font-size: .92rem; }
.cta:hover { background: var(--accent-dk); color: var(--paper); }
.backlink { font-family: -apple-system, system-ui, sans-serif; font-size: .88rem; }

/* Annuaire organismes */
.org-grid { list-style: none; padding: 0; margin: 1rem 0; display: grid;
            gap: .7rem; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); }
.org-card { background: var(--card); border: 1px solid var(--line); border-radius: 7px; padding: .9rem 1.1rem; }
.org-card a { text-decoration: none; }
.org-card .org-name { font-weight: 700; font-size: 1.05rem; }
.org-card .org-meta { font-size: .85rem; color: var(--muted);
                      font-family: -apple-system, system-ui, sans-serif; }

/* Formulaire */
form.suggest { background: var(--card); border: 1px solid var(--line); border-radius: 7px;
               padding: 1.3rem; max-width: 540px; font-family: -apple-system, system-ui, sans-serif; }
form.suggest label { display: block; font-size: .88rem; color: var(--muted); margin: .8rem 0 .25rem; }
form.suggest input, form.suggest textarea, form.suggest select {
  width: 100%; font: inherit; padding: .5rem .6rem; border: 1px solid var(--line);
  border-radius: 5px; background: var(--paper); }

/* Calendrier */
.cal-month { margin: 2rem 0 1rem; }
.cal-month h3 { font-size: 1.3rem; margin: 0 0 .6rem; padding-bottom: .3rem;
                border-bottom: 2px solid var(--ink); text-transform: capitalize; }
.cal-list { list-style: none; padding: 0; margin: 0; }
.cal-item { display: flex; gap: .9rem; align-items: baseline; padding: .55rem 0;
            border-bottom: 1px solid var(--line); font-family: -apple-system, system-ui, sans-serif; }
.cal-date { flex: 0 0 3.4rem; font-weight: 700; color: var(--accent); font-size: .9rem; text-align: right; }
.cal-body { flex: 1; }
.cal-body a { text-decoration: none; color: var(--ink); font-weight: 600; }
.cal-body a:hover { color: var(--accent); }
.cal-body .cal-meta { color: var(--muted); font-size: .85rem; }
.cal-undated { margin-top: 2.5rem; }
.icslink { font-family: -apple-system, system-ui, sans-serif; font-size: .85rem;
           color: var(--muted); margin-top: 2rem; }

footer { margin-top: 4rem; padding-top: 1.4rem; border-top: 1px solid var(--line);
         font-size: .85rem; color: var(--muted); line-height: 1.7;
         font-family: -apple-system, system-ui, sans-serif; }
.empty { text-align: center; padding: 4rem 1rem; color: var(--faint);
         background: var(--card); border: 1px dashed var(--line); border-radius: 7px; }
@media (max-width: 620px) {
  .brand h1 { font-size: 1.35rem; }
  .fiche-head h2 { font-size: 1.45rem; }
  .enbref dl { grid-template-columns: 1fr; }
}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _strip_internal(d):
    """Retire récursivement tout champ préfixé '_' (bias profil interne, méta privée)."""
    if isinstance(d, dict):
        return {k: _strip_internal(v) for k, v in d.items() if not str(k).startswith("_")}
    if isinstance(d, list):
        return [_strip_internal(v) for v in d]
    return d


def _get_any(d: dict, *keys, default=None):
    for k in keys:
        v = d.get(k) if isinstance(d, dict) else None
        if v not in (None, "", []):
            return v
    return default


def _esc(s) -> str:
    return html.escape(str(s)) if s is not None else ""


def load_bareme() -> list[dict]:
    if not CRITERES_PATH.exists():
        return []
    data = _load_yaml(CRITERES_PATH)
    out = []
    for fam in (data.get("bareme") or {}).get("familles", []):
        for c in fam.get("criteres", []):
            out.append({"id": c["id"], "label": c["label"], "poids": c.get("poids", 1)})
    return out


def fiche_fields(f: dict) -> dict:
    """Normalise les accès (tolérant aux noms FR/ES/EN renvoyés par Claude)."""
    opp = f.get("opportunite") or {}
    lieu = opp.get("lieu") or {}
    cand = f.get("candidature") or f.get("candidatura") or f.get("application") or {}
    elig = f.get("eligibilite") or f.get("elegibilidad") or {}
    return {
        "uid": f.get("uid", ""),
        "type": f.get("type", "unknown"),
        "nom": _get_any(opp, "nom", "name", default="Sans titre"),
        "nom_fr": opp.get("nom_fr"),
        "affichage": opp.get("affichage_titre") or _get_any(opp, "nom", "name", default="Sans titre"),
        "organisme": _get_any(opp, "organisme", "organizer", default=""),
        "ville": _get_any(lieu, "ville", "ciudad", "city"),
        "pays": _get_any(lieu, "pays", "pais", "país", "country"),
        "territoire": _get_any(lieu, "territoire", "territorio"),
        "date_limite": _get_any(cand, "date_limite", "deadline", "fecha_limite"),
        "url_candidature": _get_any(cand, "url_candidature", "url_candidatura"),
        "source_url": f.get("source_url", "#"),
        "score": f.get("score"),
        "status": f.get("status", "indetermine"),
        "disciplines": _get_any(elig, "disciplines", "disciplinas", default=[]) or [],
        "eligibilite": elig,
        "candidature": cand,
        "analyse": f.get("analyse") or {},
        "a_savoir": f.get("a_savoir") or [],
        "criteres_programme": f.get("criteres_programme") or [],
        "conditions": (f.get("conditions_residence") or f.get("conditions_bourse")
                       or f.get("conditions_prix") or f.get("conditions_exposition") or {}),
        "raw": f,
    }


def load_all(base: Path) -> list[dict]:
    out = []
    for t in TYPES:
        d = base / t
        if d.exists():
            for p in sorted(d.glob("*.yml")):
                try:
                    out.append(_strip_internal(_load_yaml(p)))
                except Exception as e:
                    print(f"  ⚠ skip {p}: {e}")
    return out


def org_slug_for(nom: str) -> str:
    """Trouve le slug du fichier organisme correspondant à un nom canonique."""
    if not nom:
        return ""
    for p in ORGANISMES_DIR.glob("*.yml"):
        try:
            d = _load_yaml(p)
        except Exception:
            continue
        if (d.get("nom_canonique") or "").strip().lower() == nom.strip().lower():
            return p.stem
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Fragments HTML
# ─────────────────────────────────────────────────────────────────────────────
def page_shell(title: str, body: str, active: str = "") -> str:
    def na(key):
        return ' class="active"' if key == active else ""
    return f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>{_esc(title)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<meta name="description" content="Veille internationale des résidences, bourses, prix et appels à exposition ouverts aux plasticien·nes.">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:type" content="website">
<link rel="alternate" type="application/rss+xml" title="Toutes opportunités" href="/feed/all.xml">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header class="masthead">
  <a class="brand" href="/">
    <span class="logo-mark">R</span>
    <span>
      <h1>Résidence</h1>
      <div class="baseline">la veille des opportunités pour artistes plasticien·nes</div>
    </span>
  </a>
  <nav class="topnav">
    <a href="/"{na('catalogue')}>Catalogue</a>
    <a href="/calendrier.html"{na('calendrier')}>Calendrier</a>
    <a href="/organismes.html"{na('organismes')}>Organismes</a>
    <a href="/archive.html"{na('archive')}>Archive</a>
    <a href="/feed/all.xml">RSS</a>
    <a href="/suggerer.html"{na('suggerer')}>Suggérer une source</a>
    <a href="/a-propos.html"{na('apropos')}>À propos</a>
  </nav>
</header>
{body}
<footer>
  <p>Mise à jour automatique — sources FR / EN / ES, interface FR.
     Flux : <a href="/feed/residences.xml">résidences</a> ·
     <a href="/feed/bourses.xml">bourses</a> ·
     <a href="/feed/prix.xml">prix</a> ·
     <a href="/feed/expositions.xml">expositions</a> ·
     <a href="/data.json">données (JSON)</a></p>
  <p>Vérifiez toujours les informations sur le site de l'organisme avant de candidater.
     Code : <a href="https://github.com/CedricMabilotte/residence-veille">github.com/CedricMabilotte/residence-veille</a></p>
</footer>
</div>
</body>
</html>'''


def deadline_html(date_limite) -> str:
    if date_limite:
        return f'<span class="deadline">Échéance {_esc(date_limite)}</span>'
    return '<span class="deadline">échéance à confirmer</span>'


def render_card(ff: dict) -> str:
    """Carte d'opportunité dans le catalogue (lien vers la fiche-item)."""
    t = ff["type"]
    discipline = ", ".join(ff["disciplines"][:3])
    lieu = ", ".join(v for v in [ff["ville"], ff["pays"]] if v)
    score = ff["score"]
    score_html = f'<span class="score-pill">{score}/10</span>' if isinstance(score, (int, float)) else ""
    org_slug = org_slug_for(ff["organisme"])
    org_html = (
        f'<a href="/organisme/{_esc(org_slug)}/">{_esc(ff["organisme"])}</a>'
        if org_slug else _esc(ff["organisme"])
    )
    search_blob = " ".join(str(x) for x in [
        ff["affichage"], ff["organisme"], lieu, discipline,
        (ff["analyse"] or {}).get("synthese", ""),
    ]).lower()
    return f'''<li class="card {_esc(ff['status'])}" data-type="{_esc(t)}"
    data-pays="{_esc((ff['pays'] or '').lower())}"
    data-disc="{_esc(discipline.lower())}"
    data-deadline="{_esc(ff['date_limite'] or '')}"
    data-search="{_esc(search_blob)}">
  <div class="row1">
    <span class="tag {_esc(t)}">{_esc(TYPE_LABEL_FR.get(t, t))}</span>
    {deadline_html(ff['date_limite'])}
    {score_html}
  </div>
  <h3><a href="/o/{_esc(ff['uid'])}.html">{_esc(ff['affichage'])}</a></h3>
  <div class="meta">{org_html}{' — ' if ff['organisme'] and lieu else ''}{_esc(lieu)}
    {(' · ' + _esc(discipline)) if discipline else ''}</div>
</li>'''


def render_fiche_item(ff: dict) -> str:
    """Page HTML complète d'une opportunité — structure orientée analyse."""
    t = ff["type"]
    lieu = ", ".join(v for v in [ff["ville"], ff["pays"]] if v)
    org_slug = org_slug_for(ff["organisme"])
    analyse = ff["analyse"] or {}

    # ── 1. Analyse du programme ──
    synthese = analyse.get("synthese")
    pour_qui = analyse.get("pour_qui")
    if synthese:
        analyse_html = f'<div class="prose"><p>{_esc(synthese)}</p>'
        if pour_qui:
            analyse_html += f'<p><strong>Pour qui :</strong> {_esc(pour_qui)}</p>'
        analyse_html += '</div>'
    else:
        analyse_html = '<p class="prose">Analyse non disponible — voir la source originale.</p>'

    # ── 2. Critères recherchés (barème) ──
    bareme = {c["id"]: c["label"] for c in load_bareme()}
    crit_rows = ""
    for c in ff["criteres_programme"]:
        cid = c.get("id", "")
        label = bareme.get(cid, cid)
        rempli = (c.get("rempli") or "inconnu").lower()
        just = c.get("justification") or ""
        cls = {"oui": "crit-oui", "non": "crit-non",
               "partiel": "crit-partiel"}.get(rempli, "crit-inconnu")
        mark = {"oui": "Oui", "non": "Non", "partiel": "Partiel"}.get(rempli, "Non précisé")
        crit_rows += (f'<tr><td>{_esc(label)}</td>'
                      f'<td class="{cls}">{mark}</td>'
                      f'<td>{_esc(just)}</td></tr>')
    if crit_rows:
        criteres_html = (f'<table class="crit"><tr><th>Critère</th><th>Programme</th>'
                         f'<th>Justification</th></tr>{crit_rows}</table>')
    else:
        criteres_html = '<p class="prose">Critères non encore évalués pour cette fiche.</p>'

    # ── 3. Éligibilité (tableau critère/valeur) ──
    elig = ff["eligibilite"]
    elig_map = [
        ("Disciplines", ", ".join(ff["disciplines"]) if ff["disciplines"] else None),
        ("Niveau de carrière", _get_any(elig, "niveau_carriere", "nivel_carrera")),
        ("Âge maximum", elig.get("age_max")),
        ("Nationalité", _get_any(elig, "nationalite", "nacionalite", "nacionalidad")),
        ("Résidence administrative", _get_any(elig, "residence_administrative")),
    ]
    elig_rows = "".join(
        f'<tr><td>{_esc(k)}</td><td>{_esc(v)}</td></tr>'
        for k, v in elig_map if v not in (None, "", [])
    )
    elig_html = (f'<table class="crit">{elig_rows}</table>' if elig_rows
                 else '<p class="prose">Critères d\'éligibilité non précisés.</p>')

    # ── 4. À savoir ──
    asavoir = ff["a_savoir"]
    asavoir_html = ""
    if asavoir:
        items = "".join(f"<li>{_esc(x)}</li>" for x in asavoir)
        asavoir_html = f'<div class="asavoir"><strong>À savoir</strong><ul>{items}</ul></div>'

    # ── 5. Infos pratiques ──
    cand = ff["candidature"]
    pratique = [
        ("Date limite", ff["date_limite"]),
        ("Langue du dossier", ", ".join(_get_any(cand, "langue_dossier", "lingua_dossier", default=[]) or [])),
        ("Pièces demandées", ", ".join(_get_any(cand, "pieces_demandees", default=[]) or [])),
    ]
    prat_rows = "".join(
        f'<tr><td>{_esc(k)}</td><td>{_esc(v)}</td></tr>'
        for k, v in pratique if v not in (None, "", [])
    )
    prat_html = f'<table class="crit">{prat_rows}</table>' if prat_rows else ""
    apply_url = ff["url_candidature"] or ff["source_url"]

    # ── 6. Liens transverses ──
    org_link = (f'<a href="/organisme/{_esc(org_slug)}/">{_esc(ff["organisme"])}</a>'
                if org_slug else _esc(ff["organisme"]))
    lieu_link = (f'<a href="/?pays={_esc((ff["pays"] or "").lower())}">{_esc(lieu)}</a>'
                 if ff["pays"] else _esc(lieu))

    score = ff["score"]
    score_html = (f'<span class="score-pill">{score}/10</span>'
                  if isinstance(score, (int, float)) else "")

    body = f'''
<a class="backlink" href="/">← Catalogue</a>
<div class="fiche-head">
  <div class="row1">
    <span class="tag {_esc(t)}">{_esc(TYPE_LABEL_FR.get(t, t))}</span>
    {deadline_html(ff['date_limite'])}
    {score_html}
  </div>
  <h2>{_esc(ff['affichage'])}</h2>
  <div class="sub">{org_link}{' — ' if ff['organisme'] and lieu else ''}{lieu_link}</div>
</div>

<div class="enbref">
  <dl>
    <dt>Type</dt><dd>{_esc(TYPE_LABEL_FR.get(t, t))}</dd>
    <dt>Organisme</dt><dd>{org_link}</dd>
    <dt>Lieu</dt><dd>{lieu_link or '—'}</dd>
    <dt>Date limite</dt><dd>{_esc(ff['date_limite']) or 'à confirmer'}</dd>
  </dl>
</div>

<h2 class="sec">Analyse du programme</h2>
{analyse_html}
{asavoir_html}

<h2 class="sec">Critères recherchés</h2>
{criteres_html}

<h2 class="sec">Éligibilité</h2>
{elig_html}

<h2 class="sec">Infos pratiques</h2>
{prat_html}
<p style="margin-top:1rem"><a class="cta" href="{_esc(apply_url)}" target="_blank" rel="noopener">Voir l'appel &amp; candidater →</a></p>

<h2 class="sec">Source</h2>
<p class="prose"><a href="{_esc(ff['source_url'])}" target="_blank" rel="noopener">{_esc(ff['source_url'])}</a></p>
'''
    return page_shell(f"{ff['affichage']} — Résidence", body, active="catalogue")


def render_catalogue(fiches: list[dict]) -> str:
    ffs = [fiche_fields(f) for f in fiches]

    def sort_key(ff):
        try:
            return (0, _dt.date.fromisoformat(ff["date_limite"][:10]))
        except Exception:
            return (1, _dt.date.max)
    ffs.sort(key=sort_key)

    pays = sorted({ff["pays"] for ff in ffs if ff["pays"]})
    cards = "\n".join(render_card(ff) for ff in ffs) or '<div class="empty">Aucune opportunité ouverte pour le moment.</div>'
    pays_opts = "".join(f'<option value="{_esc(p.lower())}">{_esc(p)}</option>' for p in pays)
    n = len(ffs)

    body = f'''
<p style="font-size:1.05rem;color:var(--muted);font-style:italic;margin:1.2rem 0">
  {n} opportunité{'s' if n != 1 else ''} ouverte{'s' if n != 1 else ''} — résidences, bourses, prix et appels à exposition,
  recensées en français, anglais et espagnol.</p>

<div class="toolbar">
  <input type="search" id="q" placeholder="Rechercher (titre, organisme, lieu, analyse…)">
  <select id="f-type">
    <option value="">Tous les types</option>
    <option value="residence">Résidences</option>
    <option value="bourse">Bourses</option>
    <option value="prix">Prix</option>
    <option value="exposition">Expositions</option>
  </select>
  <select id="f-pays"><option value="">Tous les pays</option>{pays_opts}</select>
  <input type="search" id="f-disc" placeholder="Discipline…" style="max-width:11em">
  <select id="f-deadline">
    <option value="">Toute échéance</option>
    <option value="30">Dans 30 jours</option>
    <option value="90">Dans 90 jours</option>
  </select>
  <span class="count" id="count"></span>
</div>

<ul class="cards" id="cards">
{cards}
</ul>

<script>
(function() {{
  var cards = Array.prototype.slice.call(document.querySelectorAll('.card'));
  var q = document.getElementById('q'), fT = document.getElementById('f-type'),
      fP = document.getElementById('f-pays'), fD = document.getElementById('f-disc'),
      fDl = document.getElementById('f-deadline'), count = document.getElementById('count');

  // Pré-remplir depuis l'URL (?pays=, ?type=)
  var params = new URLSearchParams(location.search);
  if (params.get('pays')) fP.value = params.get('pays');
  if (params.get('type')) fT.value = params.get('type');

  function daysTo(d) {{
    if (!d) return Infinity;
    var t = new Date(d) - new Date();
    return t / 86400000;
  }}
  function apply() {{
    var qq = (q.value||'').toLowerCase().trim();
    var t = fT.value, p = fP.value, dd = (fD.value||'').toLowerCase().trim(), dl = fDl.value;
    var vis = 0;
    cards.forEach(function(c) {{
      var okQ = !qq || (c.dataset.search||'').indexOf(qq) > -1;
      var okT = !t || c.dataset.type === t;
      var okP = !p || c.dataset.pays === p;
      var okD = !dd || (c.dataset.disc||'').indexOf(dd) > -1;
      var okDl = !dl || daysTo(c.dataset.deadline) <= parseInt(dl);
      var show = okQ && okT && okP && okD && okDl;
      c.style.display = show ? '' : 'none';
      if (show) vis++;
    }});
    count.textContent = vis + ' / ' + cards.length;
  }}
  [q, fT, fP, fD, fDl].forEach(function(el) {{ el.addEventListener('input', apply); }});
  apply();
}})();
</script>
'''
    return page_shell("Résidence — catalogue des opportunités", body, active="catalogue")


def render_archive(fiches: list[dict]) -> str:
    ffs = [fiche_fields(f) for f in fiches]
    cards = "\n".join(render_card(ff) for ff in ffs) or '<div class="empty">Aucune opportunité archivée.</div>'
    body = f'''
<a class="backlink" href="/">← Catalogue</a>
<h2 class="sec">Archive — opportunités expirées</h2>
<p style="color:var(--muted);font-style:italic">Conservées pour mémoire, suivi des cycles annuels et préparation des candidatures futures.</p>
<ul class="cards">{cards}</ul>
'''
    return page_shell("Archive — Résidence", body, active="archive")


_MOIS_FR = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
            "août", "septembre", "octobre", "novembre", "décembre"]


def render_calendar(fiches: list[dict]) -> str:
    """Page calendrier HTML : opportunités groupées par mois d'échéance, cliquables."""
    ffs = [fiche_fields(f) for f in fiches]
    dated, undated = [], []
    for ff in ffs:
        d = None
        if ff["date_limite"]:
            try:
                d = _dt.date.fromisoformat(ff["date_limite"][:10])
            except Exception:
                d = None
        (dated if d else undated).append((d, ff))
    dated.sort(key=lambda x: x[0])

    # Regroupement par mois
    from itertools import groupby
    months_html = ""
    for (yr, mo), grp in groupby(dated, key=lambda x: (x[0].year, x[0].month)):
        rows = ""
        for d, ff in grp:
            lieu = ", ".join(v for v in [ff["ville"], ff["pays"]] if v)
            rows += f'''<li class="cal-item">
  <span class="cal-date">{d.day:02d}</span>
  <span class="cal-body">
    <a href="/o/{_esc(ff['uid'])}.html">{_esc(ff['affichage'])}</a>
    <div class="cal-meta"><span class="tag {_esc(ff['type'])}">{_esc(TYPE_LABEL_FR.get(ff['type'], ff['type']))}</span>
      &nbsp;{_esc(ff['organisme'])}{' — ' if ff['organisme'] and lieu else ''}{_esc(lieu)}</div>
  </span>
</li>'''
        months_html += (f'<div class="cal-month"><h3>{_MOIS_FR[mo]} {yr}</h3>'
                        f'<ul class="cal-list">{rows}</ul></div>')

    undated_html = ""
    if undated:
        rows = ""
        for _, ff in undated:
            lieu = ", ".join(v for v in [ff["ville"], ff["pays"]] if v)
            rows += f'''<li class="cal-item">
  <span class="cal-date">—</span>
  <span class="cal-body">
    <a href="/o/{_esc(ff['uid'])}.html">{_esc(ff['affichage'])}</a>
    <div class="cal-meta"><span class="tag {_esc(ff['type'])}">{_esc(TYPE_LABEL_FR.get(ff['type'], ff['type']))}</span>
      &nbsp;{_esc(ff['organisme'])}{' — ' if ff['organisme'] and lieu else ''}{_esc(lieu)}</div>
  </span>
</li>'''
        undated_html = (f'<div class="cal-month cal-undated"><h3>Échéance à confirmer</h3>'
                        f'<ul class="cal-list">{rows}</ul></div>')

    inner = (months_html + undated_html) or '<div class="empty">Aucune opportunité au calendrier.</div>'
    body = f'''
<a class="backlink" href="/">← Catalogue</a>
<h2 class="sec">Calendrier des échéances</h2>
<p style="color:var(--muted);font-style:italic">Les dates limites de candidature, mois par mois. Chaque entrée mène à sa fiche détaillée.</p>
{inner}
<p class="icslink">↓ <a href="/calendar.ics">Télécharger le calendrier au format .ics</a> (à importer dans votre agenda)</p>
'''
    return page_shell("Calendrier — Résidence", body, active="calendrier")


def render_annuaire(orgs: list[dict], by_org: dict) -> str:
    items = ""
    for org in sorted(orgs, key=lambda o: (o.get("nom_canonique") or "").lower()):
        slug = org.get("uid", "")
        nom = org.get("nom_canonique", "Organisme")
        pays = org.get("pays") or ""
        n = len(by_org.get(nom, []))
        type_org = org.get("type_organisme") or ""
        items += f'''<li class="org-card">
  <a href="/organisme/{_esc(slug)}/"><span class="org-name">{_esc(nom)}</span></a>
  <div class="org-meta">{_esc(pays)}{' · ' if pays and type_org else ''}{_esc(type_org)}
    {' · ' if (pays or type_org) else ''}{n} opportunité{'s' if n != 1 else ''}</div>
</li>'''
    grid = f'<ul class="org-grid">{items}</ul>' if items else '<div class="empty">Aucun organisme répertorié.</div>'
    body = f'''
<a class="backlink" href="/">← Catalogue</a>
<h2 class="sec">Annuaire des organismes</h2>
<p style="color:var(--muted);font-style:italic">Les structures qui portent les opportunités recensées. Une carte géographique est prévue dans une prochaine version.</p>
{grid}
'''
    return page_shell("Organismes — Résidence", body, active="organismes")


def render_organisme(org: dict, related: list[dict]) -> str:
    nom = org.get("nom_canonique", "Organisme")
    pays = org.get("pays") or ""
    desc = org.get("description_courte") or ""
    url = org.get("url_canonique") or ""
    adresse = org.get("adresse") or ""
    ville = org.get("ville") or ""
    type_org = (org.get("type_organisme") or "").replace("_", " ")
    acronymes = org.get("acronymes") or []
    disciplines = org.get("disciplines_proposees") or []
    ffs = [fiche_fields(f) for f in related]
    cards = "\n".join(render_card(ff) for ff in ffs) or '<div class="empty">Aucune opportunité enregistrée.</div>'

    # Carte d'identité de l'organisme
    ident_rows = []
    if type_org:
        ident_rows.append(("Type", type_org))
    if acronymes:
        ident_rows.append(("Sigle", ", ".join(acronymes)))
    loc = ", ".join(v for v in [adresse, ville, pays] if v)
    if loc:
        ident_rows.append(("Adresse", loc))
    if url:
        ident_rows.append(("Site web", f'<a href="{_esc(url)}" target="_blank" rel="noopener">{_esc(url)}</a>'))
    if disciplines:
        ident_rows.append(("Disciplines accueillies", ", ".join(disciplines)))
    n_opp = len(ffs)
    ident_rows.append(("Opportunités recensées", str(n_opp)))
    ident_html = ""
    if ident_rows:
        dl = "".join(f"<dt>{_esc(k)}</dt><dd>{v if k in ('Site web',) else _esc(v)}</dd>"
                     for k, v in ident_rows)
        ident_html = f'<div class="enbref"><dl>{dl}</dl></div>'

    # Historique des éditions (track record)
    track = org.get("track_record") or {}
    track_html = ""
    if track:
        rows = ""
        for tid, info in track.items():
            eds = ", ".join(info.get("editions") or [])
            rows += f'<tr><td>{_esc(TYPE_LABEL_FR.get(tid, tid))}</td><td>{_esc(eds)}</td></tr>'
        track_html = (f'<h2 class="sec">Historique des éditions</h2>'
                      f'<table class="crit"><tr><th>Type</th><th>Éditions repérées</th></tr>{rows}</table>')

    # Signaux internes (cycles + partenaires) — affichés, marqués indicatifs
    signaux_html = ""
    cycles_bits = []
    for tid, info in track.items():
        fen = info.get("fenetre_annuelle")
        if fen:
            cycles_bits.append(f"{TYPE_LABEL_FR.get(tid, tid)} : {fen}")
    partenaires = org.get("partenaires_mentionnes") or []
    if cycles_bits or partenaires:
        parts = ""
        if cycles_bits:
            parts += "<p><strong>Fenêtres de candidature estimées :</strong> " + " ; ".join(_esc(c) for c in cycles_bits) + "</p>"
        if partenaires:
            noms = ", ".join(_esc(p.get("nom_brut", p.get("organisme_uid", ""))) for p in partenaires[:10])
            parts += f"<p><strong>Partenaires repérés :</strong> {noms}</p>"
        signaux_html = (f'<h2 class="sec">Repères</h2>'
                        f'<div class="asavoir">{parts}'
                        f'<p style="color:var(--faint)">Estimations indicatives, dérivées des éditions passées — à vérifier.</p></div>')

    body = f'''
<a class="backlink" href="/organismes.html">← Annuaire</a>
<div class="fiche-head">
  <h2>{_esc(nom)}</h2>
  <div class="sub">{_esc(", ".join(v for v in [ville, pays] if v))}
    {f' · <a href="{_esc(url)}" target="_blank" rel="noopener">site officiel</a>' if url else ''}</div>
</div>
{f'<p class="prose">{_esc(desc)}</p>' if desc else ''}
{ident_html}

<h2 class="sec">Opportunités</h2>
<ul class="cards">{cards}</ul>
{track_html}
{signaux_html}
'''
    return page_shell(f"{nom} — Résidence", body, active="organismes")


def render_about() -> str:
    body = '''
<a class="backlink" href="/">← Catalogue</a>
<h2 class="sec">À propos</h2>
<div class="prose">
<p><strong>Résidence</strong> agrège, classe et publie quatre types d'opportunités ouvertes
   aux artistes plasticien·nes : <em>résidences, bourses, prix et appels à exposition</em>.
   Les sources sont parcourues en français, anglais et espagnol ; l'interface est en français.</p>
<p>Plusieurs fois par semaine, un script parcourt une liste de sources institutionnelles.
   Pour chaque appel détecté, une fiche structurée est extraite automatiquement : type,
   organisme, lieu, date limite, conditions, éligibilité, et une analyse synthétique.</p>
<p>Chaque fiche est lue contre un barème de critères matériels (rétribution, hébergement,
   atelier, prise en charge des frais) qui éclaire le programme proposé.</p>
<p><strong>Limites.</strong> Les fiches sont extraites par un modèle de langage : certaines
   informations peuvent être incomplètes ou erronées. Vérifiez toujours sur le site de
   l'organisme avant de candidater — un lien direct figure sur chaque fiche.</p>
<p>Code source : <a href="https://github.com/CedricMabilotte/residence-veille">CedricMabilotte/residence-veille</a>.</p>
</div>
'''
    return page_shell("À propos — Résidence", body, active="apropos")


def render_suggest() -> str:
    action = (f"https://formspree.io/f/{FORMSPREE_ID}"
              if FORMSPREE_ID != "VOTRE_ID_FORMSPREE" else "")
    note = "" if action else (
        '<p style="color:var(--accent)"><strong>Formulaire à activer :</strong> '
        'créer un endpoint sur formspree.io et renseigner l\'ID dans generate_site.py. '
        f'En attendant, écrire à <a href="mailto:{CONTACT_MAIL}?subject=Suggestion%20de%20source">'
        f'{CONTACT_MAIL}</a>.</p>'
    )
    form_attrs = f'action="{action}" method="POST"' if action else 'onsubmit="return false"'
    body = f'''
<a class="backlink" href="/">← Catalogue</a>
<h2 class="sec">Suggérer une source</h2>
<div class="prose">
<p>Vous connaissez un site qui publie des appels à résidences, bourses, prix ou
   expositions pour plasticien·nes ? Proposez-le — il sera instruit automatiquement
   au prochain passage de la veille.</p>
</div>
{note}
<form class="suggest" {form_attrs}>
  <label for="url">URL de la source *</label>
  <input type="url" id="url" name="url" placeholder="https://…" required>
  <label for="type">Type d'opportunités</label>
  <select id="type" name="type">
    <option value="">Indifférent / plusieurs</option>
    <option>Résidences</option><option>Bourses</option>
    <option>Prix</option><option>Expositions</option>
  </select>
  <label for="note">Remarque (facultatif)</label>
  <textarea id="note" name="note" rows="3" placeholder="Pays, discipline, langue…"></textarea>
  <p style="margin-top:1rem"><button class="cta" type="submit">Envoyer la suggestion</button></p>
</form>
'''
    return page_shell("Suggérer une source — Résidence", body, active="suggerer")


# ─────────────────────────────────────────────────────────────────────────────
# RSS / ICS
# ─────────────────────────────────────────────────────────────────────────────
def render_rss(fiches: list[dict], title: str) -> str:
    items = ""
    for f in fiches[:50]:
        ff = fiche_fields(f)
        desc = f"{TYPE_LABEL_FR.get(ff['type'], '')} — {ff['organisme']} — échéance : {ff['date_limite'] or 'à confirmer'}"
        items += (f"<item><title>{xml_escape(ff['affichage'])}</title>"
                  f"<link>https://residence.actitude.org/o/{xml_escape(ff['uid'])}.html</link>"
                  f"<guid isPermaLink='false'>{xml_escape(ff['uid'])}</guid>"
                  f"<description>{xml_escape(desc)}</description></item>\n")
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
            f'<title>{xml_escape(title)}</title>'
            f'<link>https://residence.actitude.org/</link>'
            f'<description>{xml_escape(title)}</description><language>fr</language>\n'
            f'{items}</channel></rss>')


def render_ics(fiches: list[dict]) -> str:
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ev = ""
    for f in fiches:
        ff = fiche_fields(f)
        if not ff["date_limite"]:
            continue
        try:
            d = _dt.date.fromisoformat(ff["date_limite"][:10])
        except Exception:
            continue
        ev += (f"BEGIN:VEVENT\nUID:{ff['uid']}@residence.actitude.org\nDTSTAMP:{now}\n"
               f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}\n"
               f"DTEND;VALUE=DATE:{(d + _dt.timedelta(days=1)).strftime('%Y%m%d')}\n"
               f"SUMMARY:[{TYPE_LABEL_FR.get(ff['type'], '')}] {ff['affichage'][:180]}\n"
               f"URL:https://residence.actitude.org/o/{ff['uid']}.html\nEND:VEVENT\n")
    return f"BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Residence//actitude.org//FR\n{ev}END:VCALENDAR\n"


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    for sub in ("", "o", "feed", "organisme"):
        (SITE_DIR / sub).mkdir(parents=True, exist_ok=True)

    ouvertes = load_all(APPELS_DIR)
    archivees = load_all(ARCHIVE_DIR)

    # Index par organisme
    from collections import defaultdict
    by_org: dict[str, list[dict]] = defaultdict(list)
    for f in ouvertes + archivees:
        nom = (f.get("opportunite") or {}).get("organisme") or ""
        if nom:
            by_org[nom].append(f)

    # Pages principales
    (SITE_DIR / "index.html").write_text(render_catalogue(ouvertes), encoding="utf-8")
    (SITE_DIR / "calendrier.html").write_text(render_calendar(ouvertes), encoding="utf-8")
    (SITE_DIR / "archive.html").write_text(render_archive(archivees), encoding="utf-8")
    (SITE_DIR / "a-propos.html").write_text(render_about(), encoding="utf-8")
    (SITE_DIR / "suggerer.html").write_text(render_suggest(), encoding="utf-8")

    # Fiches-items
    for f in ouvertes + archivees:
        ff = fiche_fields(f)
        if ff["uid"]:
            (SITE_DIR / "o" / f"{ff['uid']}.html").write_text(
                render_fiche_item(ff), encoding="utf-8")

    # Annuaire + fiches organismes
    orgs = []
    if ORGANISMES_DIR.exists():
        for p in sorted(ORGANISMES_DIR.glob("*.yml")):
            try:
                orgs.append(_load_yaml(p))
            except Exception:
                continue
    (SITE_DIR / "organismes.html").write_text(render_annuaire(orgs, by_org), encoding="utf-8")
    for org in orgs:
        slug = org.get("uid", "")
        if not slug:
            continue
        od = SITE_DIR / "organisme" / slug
        od.mkdir(parents=True, exist_ok=True)
        related = by_org.get(org.get("nom_canonique", ""), [])
        od.joinpath("index.html").write_text(
            render_organisme(org, [_strip_internal(r) for r in related]), encoding="utf-8")

    # RSS
    (SITE_DIR / "feed" / "all.xml").write_text(
        render_rss(ouvertes, "Résidence — toutes opportunités"), encoding="utf-8")
    for t in TYPES:
        sub = [f for f in ouvertes if f.get("type") == t]
        (SITE_DIR / "feed" / f"{RSS_FILE[t]}.xml").write_text(
            render_rss(sub, f"Résidence — {RSS_FILE[t]}"), encoding="utf-8")

    # ICS
    (SITE_DIR / "calendar.ics").write_text(render_ics(ouvertes), encoding="utf-8")

    # data.json
    (SITE_DIR / "data.json").write_text(json.dumps({
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "n_ouvertes": len(ouvertes), "n_archive": len(archivees),
        "opportunites": ouvertes,
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    # robots / sitemap / favicon / CNAME
    (SITE_DIR / "robots.txt").write_text(
        "User-agent: *\nAllow: /\nSitemap: https://residence.actitude.org/sitemap.xml\n",
        encoding="utf-8")
    urls = ["", "calendrier.html", "organismes.html", "archive.html", "a-propos.html", "suggerer.html"]
    urls += [f"o/{fiche_fields(f)['uid']}.html" for f in ouvertes if fiche_fields(f)["uid"]]
    urls += [f"organisme/{o.get('uid')}/" for o in orgs if o.get("uid")]
    sm = "".join(f"<url><loc>https://residence.actitude.org/{u}</loc></url>\n" for u in urls)
    (SITE_DIR / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{sm}</urlset>\n',
        encoding="utf-8")
    (SITE_DIR / "favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<rect width="64" height="64" rx="12" fill="#bc4c3a"/>'
        '<text x="32" y="46" font-family="Georgia,serif" font-size="40" font-weight="bold" '
        'text-anchor="middle" fill="#f4f1e8">R</text></svg>', encoding="utf-8")
    (SITE_DIR / "CNAME").write_text("residence.actitude.org\n", encoding="utf-8")

    print(f"✓ Site généré : {len(ouvertes)} ouvertes, {len(archivees)} archivées, "
          f"{len(orgs)} organismes, {len(ouvertes)+len(archivees)} fiches-items")


if __name__ == "__main__":
    main()

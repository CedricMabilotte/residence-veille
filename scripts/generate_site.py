#!/usr/bin/env python3
"""
generate_site.py — Génère le site public à partir des fiches YAML.

Sorties dans site/ :
  - index.html       : home avec liste des opportunités ouvertes (filtres FR JS)
  - archive.html     : opportunités expirées (consultables)
  - calendar.ics     : fichier ICS global avec toutes les ouvertes datées
  - feed/all.xml     : flux RSS global
  - feed/{type}.xml  : flux RSS par type
  - organisme/{slug}/index.html : page par organisme
  - CNAME            : residence.actitude.org

Auteur : Residence Bot — généré à chaque run.
"""

from __future__ import annotations

import datetime as _dt
import html
import json
import re
import shutil
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

import yaml

ROOT = Path(__file__).resolve().parent.parent
APPELS_DIR = ROOT / "appels"
ARCHIVE_DIR = ROOT / "archive"
ORGANISMES_DIR = ROOT / "organismes"
SITE_DIR = ROOT / "site"

TYPES = ["residence", "bourse", "prix", "exposition"]
TYPE_LABEL_FR = {
    "residence": "Résidence",
    "bourse": "Bourse",
    "prix": "Prix",
    "exposition": "Exposition",
}
TYPE_EMOJI = {
    "residence": "Re",
    "bourse": "Bo",
    "prix": "Pr",
    "exposition": "Ex",
}

CSS = """
:root {
  --text: #1a1a1a; --muted: #666; --bg: #f7f6f1; --card: #ffffff;
  --border: #e0ddd6; --accent: #bc4c3a; --accent-dark: #8f3829;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  color: var(--text); background: var(--bg); line-height: 1.55;
}
.wrap { max-width: 1080px; margin: 0 auto; padding: 2.5rem 1.2rem 4rem; }
.header { margin-bottom: 2rem; }
h1 { font-size: 2rem; margin: 0 0 .3rem; letter-spacing: -0.02em; }
h2 { font-size: 1.15rem; margin: 2.2rem 0 .8rem; padding-bottom: .4rem; border-bottom: 1px solid var(--border); }
.tagline { color: var(--muted); margin: 0 0 1.5rem; font-size: 1.05rem; }
nav { display: flex; gap: 1.2rem; margin-bottom: 2rem; padding-bottom: 1rem; border-bottom: 1px solid var(--border); font-size: .92rem; flex-wrap: wrap; }
nav a { color: var(--accent); text-decoration: none; }
nav a:hover { color: var(--accent-dark); text-decoration: underline; }
.filters {
  background: var(--card); border: 1px solid var(--border); border-radius: 8px;
  padding: 1rem 1.2rem; margin-bottom: 1.8rem;
  display: flex; gap: 1.2rem; flex-wrap: wrap; align-items: center;
}
.filters label { font-size: .85rem; color: var(--muted); display: flex; align-items: center; gap: .4rem; }
.filters select, .filters input {
  padding: .35rem .55rem; border: 1px solid var(--border); border-radius: 4px;
  font-size: .9rem; background: white; color: var(--text);
}
.filters #f-count { margin-left: auto; color: var(--muted); font-size: .85rem; font-variant-numeric: tabular-nums; }
ul.opps { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: .7rem; }
li.opp {
  background: var(--card); border: 1px solid var(--border); border-radius: 8px;
  padding: 1rem 1.2rem; transition: border-color .15s, box-shadow .15s;
}
li.opp:hover { border-color: var(--accent); box-shadow: 0 2px 8px rgba(188,76,58,0.08); }
li.opp .badges { display: flex; gap: .6rem; align-items: center; flex-wrap: wrap; margin-bottom: .4rem; }
li.opp .type-tag {
  display: inline-block; background: var(--accent); color: white;
  font-size: .72rem; padding: .2rem .55rem; border-radius: 3px;
  text-transform: uppercase; letter-spacing: .06em; font-weight: 600;
}
li.opp h3 { margin: .15rem 0 .3rem; font-size: 1.08rem; font-weight: 600; line-height: 1.35; }
li.opp h3 a { color: var(--text); text-decoration: none; }
li.opp h3 a:hover { color: var(--accent); }
li.opp .meta { color: var(--muted); font-size: .87rem; }
.deadline { color: var(--accent); font-weight: 600; font-size: .9rem; font-variant-numeric: tabular-nums; }
li.opp.indetermine .deadline { color: var(--muted); font-weight: normal; font-style: italic; }
.summary { color: #555; font-size: .9rem; margin: .5rem 0 0; }
footer {
  margin-top: 4rem; padding-top: 1.5rem; border-top: 1px solid var(--border);
  font-size: .85rem; color: var(--muted); line-height: 1.7;
}
footer a { color: var(--muted); }
footer a:hover { color: var(--accent); }
.empty { text-align: center; padding: 4rem 1rem; color: var(--muted); background: var(--card); border: 1px dashed var(--border); border-radius: 8px; }
@media (max-width: 600px) {
  .wrap { padding: 1.5rem .8rem 3rem; }
  h1 { font-size: 1.6rem; }
  .filters { flex-direction: column; align-items: stretch; gap: .7rem; }
  .filters #f-count { margin-left: 0; text-align: right; }
}
"""


def _load_fiche(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _strip_internal(d: dict) -> dict:
    """Retire récursivement tous les champs commençant par _ (bias interne, méta privée)."""
    if isinstance(d, dict):
        return {k: _strip_internal(v) for k, v in d.items() if not k.startswith("_")}
    if isinstance(d, list):
        return [_strip_internal(v) for v in d]
    return d


def all_fiches(include_archive: bool = False) -> list[dict]:
    fiches = []
    bases = [APPELS_DIR]
    if include_archive:
        bases.append(ARCHIVE_DIR)
    for base in bases:
        for type_id in TYPES:
            d = base / type_id
            if not d.exists():
                continue
            for path in sorted(d.glob("*.yml")):
                try:
                    fiches.append(_strip_internal(_load_fiche(path)))
                except Exception as e:
                    print(f"  ⚠ skip {path}: {e}")
    return fiches


def _get_any(d: dict, *keys, default=None):
    """Prend la première clé non-vide trouvée parmi keys."""
    for k in keys:
        v = d.get(k)
        if v not in (None, "", []):
            return v
    return default


def render_opp_li(f: dict) -> str:
    type_id = f.get("type", "unknown")
    opp = f.get("opportunite") or {}
    nom = _get_any(opp, "nom", "name", default="Sans titre")
    nom_fr = opp.get("nom_fr")
    # Préférer nom (souvent plus complet) à l'affichage bilingue quand nom_fr est trompeur
    if nom_fr and len(nom_fr) >= 0.5 * len(nom or ""):
        affichage = opp.get("affichage_titre") or nom
    else:
        affichage = nom
    organisme = _get_any(opp, "organisme", "organizer", default="")
    lieu = opp.get("lieu") or {}
    ville = _get_any(lieu, "ville", "ciudad", "city", "town")
    pays = _get_any(lieu, "pays", "pais", "país", "country")
    lieu_str = ", ".join(v for v in [ville, pays] if v)
    cand = f.get("candidature") or f.get("candidatura") or f.get("application") or {}
    date_lim = _get_any(cand, "date_limite", "deadline", "fecha_limite")
    url = f.get("source_url") or _get_any(cand, "url_candidature", "url_candidatura", "application_url") or "#"
    status = f.get("status", "indetermine")
    elig = f.get("eligibilite") or f.get("elegibilidad") or f.get("eligibility") or {}
    discipline_list = _get_any(elig, "disciplines", "disciplinas", default=[]) or []
    discipline = ", ".join(discipline_list[:3]) if discipline_list else ""

    deadline_html = (
        f'<span class="deadline">📅 {html.escape(date_lim)}</span>'
        if date_lim else
        '<span class="deadline">date à confirmer</span>'
    )

    return f'''<li class="opp {html.escape(status)}" data-type="{html.escape(type_id)}"
       data-pays="{html.escape((pays or "").lower())}"
       data-disc="{html.escape(discipline.lower())}">
  <div class="badges">
    <span class="type-tag">{html.escape(TYPE_LABEL_FR.get(type_id, type_id))}</span>
    {deadline_html}
  </div>
  <h3><a href="{html.escape(url)}" target="_blank" rel="noopener">{html.escape(affichage)}</a></h3>
  <div class="meta">
    {html.escape(organisme)}{' — ' if organisme and lieu_str else ''}{html.escape(lieu_str)}
    {' · ' + html.escape(discipline) if discipline else ''}
  </div>
</li>'''


def render_index(fiches: list[dict]) -> str:
    # Trie : date_limite croissante, puis indéterminées
    def sort_key(f):
        dl = (f.get("candidature") or {}).get("date_limite")
        try:
            return (0, _dt.date.fromisoformat(dl[:10]))
        except Exception:
            return (1, _dt.date.max)

    fiches_sorted = sorted(fiches, key=sort_key)
    pays_set = sorted({
        ((f.get("opportunite") or {}).get("lieu") or {}).get("pays") or ""
        for f in fiches_sorted if ((f.get("opportunite") or {}).get("lieu") or {}).get("pays")
    })
    items_html = "\n".join(render_opp_li(f) for f in fiches_sorted) or '<div class="empty">Aucune opportunité ouverte pour le moment.</div>'

    pays_options = '\n'.join(f'<option value="{html.escape(p.lower())}">{html.escape(p)}</option>' for p in pays_set)

    n_total = len(fiches_sorted)
    return f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Résidence — opportunités arts plastiques</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<meta name="description" content="Veille internationale des résidences, bourses, prix et appels à exposition ouverts aux plasticien·nes. Mise à jour automatique. Sources FR/EN/ES.">
<meta property="og:title" content="Résidence — opportunités arts plastiques">
<meta property="og:description" content="Veille internationale des résidences, bourses, prix et appels à exposition ouverts aux plasticien·nes.">
<meta property="og:type" content="website">
<meta property="og:url" content="https://residence.actitude.org/">
<link rel="alternate" type="application/rss+xml" title="Toutes opportunités" href="/feed/all.xml">
<link rel="alternate" type="application/rss+xml" title="Résidences" href="/feed/residences.xml">
<link rel="alternate" type="application/rss+xml" title="Bourses" href="/feed/bourses.xml">
<link rel="alternate" type="application/rss+xml" title="Prix" href="/feed/prix.xml">
<link rel="alternate" type="application/rss+xml" title="Expositions" href="/feed/expositions.xml">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">

<div class="header">
  <h1>Résidence</h1>
  <p class="tagline">Opportunités arts plastiques — résidences, bourses, prix, appels à exposition. <strong>{n_total}</strong> ouverte{'s' if n_total > 1 else ''} aujourd'hui.</p>
</div>

<nav>
  <a href="/">Ouvertes</a>
  <a href="/archive.html">Archive</a>
  <a href="/calendar.ics">Calendrier (.ics)</a>
  <a href="/feed/all.xml">RSS</a>
  <a href="/a-propos.html">À propos</a>
</nav>

<div class="filters">
  <label>Type
    <select id="f-type">
      <option value="">tous</option>
      <option value="residence">Résidence</option>
      <option value="bourse">Bourse</option>
      <option value="prix">Prix</option>
      <option value="exposition">Exposition</option>
    </select>
  </label>
  <label>Pays
    <select id="f-pays">
      <option value="">tous</option>
      {pays_options}
    </select>
  </label>
  <label>Discipline
    <input type="search" id="f-disc" placeholder="ex. textile, photo…" style="width: 12em">
  </label>
  <span id="f-count"></span>
</div>

<ul class="opps">
{items_html}
</ul>

<footer>
  <p>Mise à jour automatique — sources FR/EN/ES, interface FR. Voir aussi :
     <a href="/feed/residences.xml">RSS résidences</a> ·
     <a href="/feed/bourses.xml">bourses</a> ·
     <a href="/feed/prix.xml">prix</a> ·
     <a href="/feed/expositions.xml">expositions</a>.</p>
  <p>Code source : <a href="https://github.com/CedricMabilotte/residence-veille">github.com/CedricMabilotte/residence-veille</a></p>
</footer>

</div>

<script>
(function() {{
  const opps = document.querySelectorAll('li.opp');
  const fType = document.getElementById('f-type');
  const fPays = document.getElementById('f-pays');
  const fDisc = document.getElementById('f-disc');
  const fCount = document.getElementById('f-count');

  function apply() {{
    const t = fType.value, p = fPays.value, d = (fDisc.value || '').toLowerCase().trim();
    let visible = 0;
    opps.forEach(li => {{
      const okT = !t || li.dataset.type === t;
      const okP = !p || li.dataset.pays === p;
      const okD = !d || (li.dataset.disc || '').includes(d);
      const show = okT && okP && okD;
      li.style.display = show ? '' : 'none';
      if (show) visible++;
    }});
    fCount.textContent = visible + ' / ' + opps.length;
  }}
  [fType, fPays, fDisc].forEach(el => el.addEventListener('input', apply));
  apply();
}})();
</script>

</body>
</html>'''


def render_archive(fiches: list[dict]) -> str:
    items_html = "\n".join(render_opp_li(f) for f in fiches) or '<div class="empty">Aucune opportunité archivée pour le moment.</div>'
    return f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Archive — Résidence</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<div class="header">
  <h1>Archive</h1>
  <p class="tagline">Opportunités expirées — gardées pour mémoire, track record et préparation des candidatures futures.</p>
</div>
<nav><a href="/">← Retour aux opportunités ouvertes</a></nav>
<ul class="opps">{items_html}</ul>
</div>
</body>
</html>'''


def render_rss(fiches: list[dict], title: str) -> str:
    items = []
    for f in fiches[:50]:
        nom = (f.get("opportunite") or {}).get("affichage_titre") \
            or (f.get("opportunite") or {}).get("nom") or "Sans titre"
        url = f.get("source_url") or "#"
        cand = f.get("candidature") or {}
        date_lim = cand.get("date_limite") or "à confirmer"
        organisme = (f.get("opportunite") or {}).get("organisme") or ""
        desc = f"{TYPE_LABEL_FR.get(f.get('type'), '')} — {organisme} — date limite : {date_lim}"
        items.append(f'''  <item>
    <title>{xml_escape(nom)}</title>
    <link>{xml_escape(url)}</link>
    <guid isPermaLink="false">{xml_escape(f.get('uid', url))}</guid>
    <description>{xml_escape(desc)}</description>
  </item>''')
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>{xml_escape(title)}</title>
<link>https://residence.actitude.org/</link>
<description>{xml_escape(title)}</description>
<language>fr</language>
{chr(10).join(items)}
</channel>
</rss>'''


def render_ics(fiches: list[dict]) -> str:
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    events = []
    for f in fiches:
        cand = f.get("candidature") or {}
        date_lim = cand.get("date_limite")
        if not date_lim:
            continue
        try:
            d = _dt.date.fromisoformat(date_lim[:10])
        except Exception:
            continue
        dstr = d.strftime("%Y%m%d")
        end = (d + _dt.timedelta(days=1)).strftime("%Y%m%d")
        nom = (f.get("opportunite") or {}).get("affichage_titre") \
            or (f.get("opportunite") or {}).get("nom") or "Sans titre"
        url = f.get("source_url") or ""
        organisme = (f.get("opportunite") or {}).get("organisme") or ""
        uid = f.get("uid", "unknown") + "@residence.actitude.org"
        summary = f"[{TYPE_LABEL_FR.get(f.get('type'), '')}] {nom}"
        desc = f"{organisme}\\n\\nDétails : {url}"
        events.append(f"""BEGIN:VEVENT
UID:{uid}
DTSTAMP:{now}
DTSTART;VALUE=DATE:{dstr}
DTEND;VALUE=DATE:{end}
SUMMARY:{summary[:200]}
DESCRIPTION:{desc[:400]}
URL:{url}
END:VEVENT""")
    return ("BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Residence//actitude.org//FR\n"
            + "\n".join(events) + "\nEND:VCALENDAR\n")


def render_organisme_page(org: dict, fiches_de_lui: list[dict]) -> str:
    nom = org.get("nom_canonique", "Organisme")
    pays = org.get("pays") or ""
    desc = org.get("description_courte") or ""
    url = org.get("url_canonique") or ""
    items_html = "\n".join(render_opp_li(f) for f in fiches_de_lui) or '<div class="empty">Aucune opportunité enregistrée pour cet organisme.</div>'
    track = org.get("track_record") or {}
    track_html = ""
    if track:
        rows = []
        for type_id, info in track.items():
            editions = ", ".join(info.get("editions") or [])
            fenetre = info.get("fenetre_annuelle") or ""
            rows.append(f"<li>{html.escape(TYPE_LABEL_FR.get(type_id, type_id))} : éditions {html.escape(editions)} {('— ' + html.escape(fenetre)) if fenetre else ''}</li>")
        track_html = f"<h2>Historique</h2><ul>{''.join(rows)}</ul>"
    return f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>{html.escape(nom)} — Résidence</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<nav><a href="/">← Toutes les opportunités</a></nav>
<div class="header">
  <h1>{html.escape(nom)}</h1>
  <p class="tagline">{html.escape(pays) if pays else ''}{' — ' + html.escape(desc) if desc else ''}
   {f' · <a href="{html.escape(url)}" target="_blank" rel="noopener">Site officiel</a>' if url else ''}
  </p>
</div>
<h2>Opportunités</h2>
<ul class="opps">{items_html}</ul>
{track_html}
</div>
</body>
</html>'''


def main():
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "feed").mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "organisme").mkdir(parents=True, exist_ok=True)

    fiches_ouvertes = all_fiches(include_archive=False)
    fiches_archive_only = []
    for type_id in TYPES:
        d = ARCHIVE_DIR / type_id
        if not d.exists():
            continue
        for path in sorted(d.glob("*.yml")):
            try:
                fiches_archive_only.append(_strip_internal(_load_fiche(path)))
            except Exception:
                continue

    # Pages principales
    (SITE_DIR / "index.html").write_text(render_index(fiches_ouvertes), encoding="utf-8")
    (SITE_DIR / "archive.html").write_text(render_archive(fiches_archive_only), encoding="utf-8")

    # Calendar global
    (SITE_DIR / "calendar.ics").write_text(render_ics(fiches_ouvertes), encoding="utf-8")

    # Flux RSS : un par type + un global
    (SITE_DIR / "feed" / "all.xml").write_text(
        render_rss(fiches_ouvertes, "Résidence — toutes opportunités"), encoding="utf-8"
    )
    # Nommage : residences.xml, bourses.xml, prix.xml (sans s), expositions.xml
    RSS_FILENAMES = {"residence": "residences", "bourse": "bourses", "prix": "prix", "exposition": "expositions"}
    for type_id in TYPES:
        sub = [f for f in fiches_ouvertes if f.get("type") == type_id]
        filename = RSS_FILENAMES.get(type_id, type_id + "s") + ".xml"
        (SITE_DIR / "feed" / filename).write_text(
            render_rss(sub, f"Résidence — {filename.replace('.xml','')}"), encoding="utf-8"
        )

    # Pages organismes
    if ORGANISMES_DIR.exists():
        # Indexe les fiches par organisme_uid via le mapping nom → fiches
        from collections import defaultdict
        by_org_name: dict[str, list[dict]] = defaultdict(list)
        for f in fiches_ouvertes + fiches_archive_only:
            org_nom = (f.get("opportunite") or {}).get("organisme") or ""
            if org_nom:
                by_org_name[org_nom].append(f)
        for path in sorted(ORGANISMES_DIR.glob("*.yml")):
            try:
                org = _load_fiche(path)
            except Exception:
                continue
            slug = path.stem  # uid de l'organisme
            org_dir = SITE_DIR / "organisme" / slug
            org_dir.mkdir(parents=True, exist_ok=True)
            related = by_org_name.get(org.get("nom_canonique", ""), [])
            org_dir.joinpath("index.html").write_text(
                render_organisme_page(org, related), encoding="utf-8"
            )

    # Page À propos
    about_html = f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>À propos — Résidence</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<nav><a href="/">← Retour à l'accueil</a></nav>
<div class="header">
  <h1>À propos</h1>
  <p class="tagline">Une veille internationale automatisée pour artistes plasticien·nes.</p>
</div>

<h2>Quoi</h2>
<p>Ce site agrège, classe et publie quatre types d'opportunités ouvertes aux plasticien·nes :
   <strong>résidences</strong>, <strong>bourses</strong>, <strong>prix</strong>, et <strong>appels à exposition</strong>.
   Les sources sont scrapées en français, anglais et espagnol ; l'interface est en français.</p>

<h2>Comment</h2>
<p>Plusieurs fois par semaine, un script parcourt une liste de sources institutionnelles
   (CNAP, Institut français, e-flux, Res Artis, TransArtists, MATADERO Madrid, Hangar
   Barcelona, etc.). Pour chaque appel détecté, une fiche structurée est extraite
   automatiquement (Claude Haiku) : type, organisme, lieu, date limite, conditions,
   éligibilité, partenaires.</p>

<h2>Pourquoi</h2>
<p>Pour qu'un·e artiste puisse repérer en quelques secondes les opportunités qui le
   ou la concernent, trier par discipline ou pays, et s'abonner via RSS ou calendrier
   ICS aux nouveautés.</p>

<h2>Limites</h2>
<p>Les fiches sont extraites par un modèle de langage. Certaines informations peuvent
   être incomplètes ou erronées : <strong>toujours vérifier sur le site source de l'organisme</strong>
   avant de candidater. Un lien direct est fourni sur chaque fiche.</p>

<h2>Code source</h2>
<p>Le projet est publié sur GitHub :
   <a href="https://github.com/CedricMabilotte/residence-veille">CedricMabilotte/residence-veille</a>.
   Pour signaler une source manquante ou une fiche erronée, ouvrir une <em>issue</em>.</p>

<h2>Sources principales</h2>
<ul>
  <li>Agrégateurs : TransArtists, Res Artis, On-the-Move, e-flux</li>
  <li>Institutions FR : CNAP, Institut français, Cité internationale des arts</li>
  <li>Lieux : Pollen (Monflanquin), Salon de Montrouge</li>
  <li>Hispanophones : MATADERO Madrid, Hangar Barcelona</li>
</ul>
<p><a href="/feed/all.xml">Tous les flux RSS</a> · <a href="/calendar.ics">Calendrier ICS</a> · <a href="/data.json">Export JSON</a></p>

<footer>
  <p>Mise à jour automatique — sources FR/EN/ES, interface FR.</p>
</footer>
</div>
</body>
</html>'''
    (SITE_DIR / "a-propos.html").write_text(about_html, encoding="utf-8")

    # Export JSON pour usage tiers (intégrations)
    json_payload = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "n_ouvertes": len(fiches_ouvertes),
        "n_archive": len(fiches_archive_only),
        "opportunites": fiches_ouvertes,  # déjà strippés des champs _internes
    }
    (SITE_DIR / "data.json").write_text(
        json.dumps(json_payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    # CNAME (residence.actitude.org)
    (SITE_DIR / "CNAME").write_text("residence.actitude.org\n", encoding="utf-8")

    # robots.txt + sitemap.xml
    (SITE_DIR / "robots.txt").write_text(
        "User-agent: *\nAllow: /\nSitemap: https://residence.actitude.org/sitemap.xml\n",
        encoding="utf-8",
    )
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    urls = [
        ("https://residence.actitude.org/", "daily", "1.0"),
        ("https://residence.actitude.org/archive.html", "weekly", "0.5"),
        ("https://residence.actitude.org/feed/all.xml", "daily", "0.8"),
    ]
    if ORGANISMES_DIR.exists():
        for path in sorted(ORGANISMES_DIR.glob("*.yml")):
            slug = path.stem
            urls.append((f"https://residence.actitude.org/organisme/{slug}/", "weekly", "0.6"))
    sm_items = "\n".join(
        f"  <url><loc>{u}</loc><changefreq>{cf}</changefreq><priority>{p}</priority></url>"
        for u, cf, p in urls
    )
    (SITE_DIR / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{sm_items}\n</urlset>\n',
        encoding="utf-8",
    )

    # Favicon SVG (sobre)
    favicon = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="12" fill="#bc4c3a"/><text x="32" y="46" font-family="serif" font-size="42" font-weight="bold" text-anchor="middle" fill="white">R</text></svg>'''
    (SITE_DIR / "favicon.svg").write_text(favicon, encoding="utf-8")

    # Bilan
    print(f"✓ Site généré dans {SITE_DIR.relative_to(ROOT)}")
    print(f"  - {len(fiches_ouvertes)} opportunité(s) ouverte(s)")
    print(f"  - {len(fiches_archive_only)} archivée(s)")
    if ORGANISMES_DIR.exists():
        print(f"  - {len(list(ORGANISMES_DIR.glob('*.yml')))} page(s) organisme")


if __name__ == "__main__":
    main()

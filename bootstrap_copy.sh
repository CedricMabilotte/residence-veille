#!/usr/bin/env bash
# bootstrap_copy.sh — Copie les modules réutilisés depuis le projet BIBLIO.
#
# À lancer UNE FOIS, après le bootstrap initial. Copie depuis :
#   ~/Documents/Claude/Projects/biblio/
# vers :
#   ~/Documents/Claude/Projects/Residences\ artistiques/
#
# Les modules retirés du fork ne sont volontairement pas copiés :
#   pdf_processor, bibliography_extractor, synopsis_enricher,
#   parsers/{archive_org,hal,opds}.py, export_bibtex, fulltext_index,
#   new_project, share_sources, discovery_{bibliography,openalex,
#   semantic_scholar,footnotes,promote}.py
#
# Usage : bash bootstrap_copy.sh

set -euo pipefail

SRC="$HOME/Documents/Claude/Projects/biblio"
DST="$HOME/Documents/Claude/Projects/Residences artistiques"

if [ ! -d "$SRC" ]; then
  echo "❌ Source introuvable : $SRC"
  exit 1
fi
if [ ! -d "$DST" ]; then
  echo "❌ Destination introuvable : $DST"
  exit 1
fi

echo "→ Copie depuis :  $SRC"
echo "→ Vers         :  $DST"
echo ""

mkdir -p "$DST/scripts/parsers"

# ─── Parsers conservés ──────────────────────────────────────────────────────
echo "  ↳ parsers/__init__.py + html_static + deep_html + rss"
cp -v "$SRC/scripts/parsers/__init__.py"      "$DST/scripts/parsers/"
cp -v "$SRC/scripts/parsers/html_static.py"   "$DST/scripts/parsers/"
cp -v "$SRC/scripts/parsers/deep_html.py"     "$DST/scripts/parsers/"
cp -v "$SRC/scripts/parsers/rss.py"           "$DST/scripts/parsers/"

# Playwright différé mais conservé
cp -v "$SRC/scripts/parsers/playwright_parser.py" "$DST/scripts/parsers/" 2>/dev/null || true

# ─── Modules utilitaires conservés ──────────────────────────────────────────
echo ""
echo "  ↳ scripts utilitaires"
cp -v "$SRC/scripts/probe_source.py"        "$DST/scripts/"
cp -v "$SRC/scripts/source_health.py"       "$DST/scripts/"
cp -v "$SRC/scripts/throttle.py"            "$DST/scripts/"
cp -v "$SRC/scripts/dedup.py"               "$DST/scripts/"
cp -v "$SRC/scripts/templating_helpers.py"  "$DST/scripts/"

# ─── Désactivés au démarrage mais code en place ─────────────────────────────
echo ""
echo "  ↳ scripts désactivés au démarrage (newsletter, webhooks)"
cp -v "$SRC/scripts/newsletter.py"          "$DST/scripts/"
cp -v "$SRC/scripts/webhooks.py"            "$DST/scripts/"
cp -v "$SRC/scripts/review_issues.py"       "$DST/scripts/"

# ─── Discovery réutilisés ───────────────────────────────────────────────────
echo ""
echo "  ↳ discovery modules conservés (external_links, mastodon, llm_suggest, blind_spots)"
cp -v "$SRC/scripts/discovery_external_links.py"  "$DST/scripts/"
cp -v "$SRC/scripts/discovery_mastodon.py"        "$DST/scripts/"
cp -v "$SRC/scripts/discovery_llm_suggest.py"     "$DST/scripts/"
cp -v "$SRC/scripts/discovery_blind_spots.py"     "$DST/scripts/"

# ─── Adapter parsers/__init__.py : retirer opds/hal/archive_org du dispatcher ─
echo ""
echo "  ↳ Adaptation parsers/__init__.py — retrait des dispatchers obsolètes"
python3 - <<'PYEOF'
from pathlib import Path
p = Path.home() / "Documents/Claude/Projects/Residences artistiques/scripts/parsers/__init__.py"
content = p.read_text(encoding="utf-8")
# Retire les imports et entrées dispatch des parsers obsolètes
for obsolete in ("archive_org", "hal", "opds"):
    content = content.replace(f"from . import {obsolete}", f"# REMOVED: from . import {obsolete}")
    content = content.replace(f"'{obsolete}'", f"# '{obsolete}'")
    content = content.replace(f'"{obsolete}"', f'# "{obsolete}"')
p.write_text(content, encoding="utf-8")
print(f"  ✓ {p.name} adapté")
PYEOF

# ─── Adapter discovery_mastodon.py : hashtags arts plastiques ──────────────
echo ""
echo "  ↳ Adaptation discovery_mastodon.py — hashtags art"
python3 - <<'PYEOF'
from pathlib import Path
p = Path.home() / "Documents/Claude/Projects/Residences artistiques/scripts/discovery_mastodon.py"
content = p.read_text(encoding="utf-8")
old_hashtags = """DEFAULT_HASHTAGS = [
    "communs", "paysannerie", "ZAD", "tierraylibertad",
    "agroecologie", "souveraineteAlimentaire",
]"""
new_hashtags = """DEFAULT_HASHTAGS = [
    "opencall", "appelacandidature", "residenceartiste", "artistresidency",
    "convocatoria", "appelaprojets", "appelaartistes", "aircall",
    "residencia", "residencyopen",
]"""
if old_hashtags in content:
    content = content.replace(old_hashtags, new_hashtags)
    p.write_text(content, encoding="utf-8")
    print(f"  ✓ {p.name} hashtags adaptés")
else:
    print(f"  ⚠ {p.name} : hashtags BIBLIO non trouvés (déjà adapté ?)")
PYEOF

echo ""
echo "✓ Bootstrap copy terminé."
echo ""
echo "Étapes suivantes :"
echo "  1. Vérifier que watch.py démarre :  python scripts/watch.py"
echo "  2. Décommenter les imports en haut de scripts/watch.py (parsers, throttle, dedup, discovery_external_links)"
echo "  3. Lancer un probe sur les sources de config/sources.yml : python scripts/probe_source.py <url>"
echo "  4. Premier run dry : DRY_RUN=true python scripts/watch.py"

"""
templating_helpers.py — Utilitaires pour le scaffolding d'agents de veille.

Petites fonctions pures réutilisables :
  - substitute_placeholders : remplace les {{TOKEN}} dans un template texte
  - slug_to_title           : convertit un slug url-safe en titre lisible
  - generate_simple_logo_svg : produit un SVG minimaliste (initiale + couleur)
  - pick_palette             : retourne une palette terre cuite/parchemin
                               dérivée d'une seed (le slug du projet)
"""

from __future__ import annotations

import hashlib
import re


# ─────────────────────────────────────────────────────────────────────────────
# Substitution de placeholders
# ─────────────────────────────────────────────────────────────────────────────
def substitute_placeholders(text: str, mapping: dict[str, str]) -> str:
    """
    Remplace {{TOKEN}} par mapping['TOKEN'] dans `text`.

    Les tokens non trouvés dans mapping sont laissés tels quels (pour
    permettre des passes successives). Aucune interpolation Jinja-style,
    on reste explicite et déterministe.
    """
    def _replace(match: re.Match) -> str:
        key = match.group(1).strip()
        return mapping.get(key, match.group(0))

    return re.sub(r"\{\{\s*([A-Z0-9_]+)\s*\}\}", _replace, text)


# ─────────────────────────────────────────────────────────────────────────────
# Slug → titre lisible
# ─────────────────────────────────────────────────────────────────────────────
# Table d'accents pour quelques mots fréquents (extensible).
# On n'essaie PAS de deviner les accents : on capitalise simplement les
# parties séparées par des tirets, l'utilisateur affinera via --display.
_ACCENT_HINTS = {
    "feminismes": "Féminismes",
    "ecologies": "Écologies",
    "ecologie": "Écologie",
    "decoloniaux": "Décoloniaux",
    "decoloniale": "Décoloniale",
    "decolonial": "Décolonial",
    "antiraciste": "Antiraciste",
    "anticarceral": "Anticarcéral",
    "decroissance": "Décroissance",
    "energie": "Énergie",
    "education": "Éducation",
    "egalite": "Égalité",
    "etat": "État",
}


def slug_to_title(slug: str) -> str:
    """
    'feminismes-decoloniaux' → 'Féminismes décoloniaux'.
    'communs-terres' → 'Communs terres'.

    Heuristique simple : split sur '-' ou '_', mappe quelques mots à accents
    fréquents, met la première lettre du résultat en majuscule.
    """
    parts = re.split(r"[-_]+", slug.strip())
    out = []
    for i, p in enumerate(parts):
        low = p.lower()
        if low in _ACCENT_HINTS:
            word = _ACCENT_HINTS[low]
            # Première lettre minuscule sauf si c'est le premier mot
            if i > 0:
                word = word[0].lower() + word[1:]
            out.append(word)
        else:
            if i == 0:
                out.append(p[:1].upper() + p[1:].lower())
            else:
                out.append(p.lower())
    return " ".join(out)


# ─────────────────────────────────────────────────────────────────────────────
# Palette dérivée du slug (déterministe)
# ─────────────────────────────────────────────────────────────────────────────
# Palette de base : terre cuite / parchemin / olive / ocre — référence BIBLIO.
# On retourne un dict de couleurs pour la couverture / le logo / le manifest.
_BIBLIO_PALETTES = [
    {"primary": "#a44a2c", "secondary": "#5a7048", "accent": "#a88930", "bg": "#f7f2e7"},  # terre cuite / olive
    {"primary": "#6b4f3a", "secondary": "#8a6d4b", "accent": "#c79f5f", "bg": "#f5ecdc"},  # noisette / sable
    {"primary": "#7a3b3b", "secondary": "#3d5a4a", "accent": "#b08d3c", "bg": "#f6efe2"},  # grenat / sapin
    {"primary": "#3f5a3c", "secondary": "#7d5938", "accent": "#c9a14a", "bg": "#f4ecdb"},  # mousse / bois
    {"primary": "#8c3a2d", "secondary": "#4a5e3a", "accent": "#a88930", "bg": "#f7f2e7"},  # tomette / champ
    {"primary": "#5d4037", "secondary": "#789262", "accent": "#d4a857", "bg": "#f6f0e1"},  # café / prairie
]


def pick_palette(seed: str) -> dict[str, str]:
    """Choisit une palette stable à partir du slug (hash sha1 → index)."""
    h = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    idx = int(h[:6], 16) % len(_BIBLIO_PALETTES)
    return _BIBLIO_PALETTES[idx]


# ─────────────────────────────────────────────────────────────────────────────
# Logo SVG minimaliste (initiale + couleur)
# ─────────────────────────────────────────────────────────────────────────────
def generate_simple_logo_svg(
    initial: str,
    color_hex: str,
    secondary_hex: str = "#5a7048",
) -> str:
    """
    SVG carré 64x64 : livre stylisé deux pages + initiale du projet centrée.
    Cohérent visuellement avec le logo BIBLIO d'origine.

    Args:
        initial: une lettre (la première du projet).
        color_hex: couleur principale (ex: '#a44a2c').
        secondary_hex: couleur secondaire (ex: '#5a7048').
    """
    letter = (initial or "?")[:1].upper()
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" '
        'fill="none" aria-hidden="true">\n'
        f'  <path d="M8 14c0-1.1.9-2 2-2h18c2.2 0 4 1.8 4 4v36c0-2.2-1.8-4-4-4H10c-1.1 0-2-.9-2-2V14z" fill="{color_hex}" opacity="0.92"/>\n'
        f'  <path d="M56 14c0-1.1-.9-2-2-2H36c-2.2 0-4 1.8-4 4v36c0-2.2 1.8-4 4-4h18c1.1 0 2-.9 2-2V14z" fill="{secondary_hex}" opacity="0.92"/>\n'
        '  <path d="M32 16v36" stroke="#231f1c" stroke-width="1.4" stroke-linecap="round"/>\n'
        f'  <text x="32" y="42" text-anchor="middle" font-family="Georgia, EB Garamond, serif" font-size="22" font-weight="600" fill="#f7f2e7">{letter}</text>\n'
        '</svg>\n'
    )


def generate_simple_favicon_svg(
    color_hex: str,
    secondary_hex: str = "#5a7048",
    bg_hex: str = "#f7f2e7",
) -> str:
    """Favicon 32x32 sur fond parchemin, deux pages colorées."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="none">\n'
        f'  <rect width="32" height="32" rx="4" fill="{bg_hex}"/>\n'
        '  <path d="M16 6v20" stroke="#231f1c" stroke-width="1"/>\n'
        f'  <path d="M5 9c0-.6.4-1 1-1h8c1.1 0 2 .9 2 2v16c0-1.1-.9-2-2-2H6c-.6 0-1-.4-1-1V9z" fill="{color_hex}"/>\n'
        f'  <path d="M27 9c0-.6-.4-1-1-1h-8c-1.1 0-2 .9-2 2v16c0-1.1.9-2 2-2h8c.6 0 1-.4 1-1V9z" fill="{secondary_hex}"/>\n'
        '</svg>\n'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Petite démo / self-test (exécutable en standalone)
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Self-test rapide
    assert substitute_placeholders("Hello {{NAME}}", {"NAME": "world"}) == "Hello world"
    assert substitute_placeholders("Hello {{NAME}}", {}) == "Hello {{NAME}}"
    assert slug_to_title("feminismes-decoloniaux") == "Féminismes décoloniaux"
    assert slug_to_title("communs-terres") == "Communs terres"
    p = pick_palette("communs-terres-paysannerie")
    assert p["primary"].startswith("#")
    svg = generate_simple_logo_svg("F", p["primary"], p["secondary"])
    assert "<svg" in svg and "F</text>" in svg
    print("templating_helpers.py — self-test OK")
    print("palette pour 'communs-terres-paysannerie' :", p)

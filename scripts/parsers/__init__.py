"""
Registre des parsers pour la veille des opportunités arts plastiques.

Pour ajouter un nouveau type de source :
1. Créer un module dans scripts/parsers/<nom>.py exposant find_documents(source: dict) -> list[dict]
2. L'enregistrer dans la map PARSERS ci-dessous
3. Dans config/sources.yml, ajouter `type: <nom>` à la source

L'API contract pour tout parser :
    find_documents(source: dict) -> list[dict]
    où source = {url, label, type, [autres options]}
    et chaque doc retourné = {url, filename, extension, link_text, context,
                              page_title, source_url}

Note (fork « Résidence ») : on a retiré les parsers `opds`, `archive_org`,
`hal` (sans objet pour les opportunités datées) et ajouté `jsonld_event`
(extraction Schema.org/Event embarqué dans le HTML).
"""

from . import html_static, deep_html, playwright_parser, rss, jsonld_event

PARSERS = {
    "html":         html_static.find_documents,
    "deep_html":    deep_html.find_documents,
    "playwright":   playwright_parser.find_documents,
    "rss":          rss.find_documents,
    "jsonld_event": jsonld_event.find_documents,
}


def dispatch(source: dict) -> list[dict]:
    """Aiguille vers le parser correspondant au type de la source.

    Si type non spécifié → fallback sur 'html' (rétrocompatibilité).
    Si type inconnu → liste vide + warning.
    """
    parser_type = source.get("type", "html")
    parser_fn = PARSERS.get(parser_type)
    if parser_fn is None:
        print(f"  ⚠  Parser inconnu : '{parser_type}' "
              f"(types valides : {', '.join(PARSERS)})")
        return []
    return parser_fn(source)

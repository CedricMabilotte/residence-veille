# Catalogue de sources pour la veille des opportunités arts plastiques

> Document de référence (équivalent du CATALOGUE-SOURCES de BIBLIO, adapté).
> Dernière mise à jour : 2026-05-19 (bootstrap).

## Méthodologie de probe

Avant d'ajouter une URL à `config/sources.yml`, valider :

```bash
UA="Mozilla/5.0 (compatible; ResidenceBot/1.0)"
URL="https://example.com/opportunities"
# Page d'index : liste-t-elle des opportunités datées en HTML statique ?
curl -sL -A "$UA" --max-time 20 "$URL" \
  | grep -oiE '(deadline|date.limite|application.deadline|fecha.l[ií]mite)' \
  | wc -l
```

Indicateurs favorables :
- Présence de mots-clés `deadline / date limite / fecha límite` dans le HTML.
- Présence d'une balise `<script type="application/ld+json">` avec `@type=Event` ou `Grant`.
- Listing paginé avec URLs propres (`?page=N`).

Indicateurs défavorables (= sourcing complexe, à différer) :
- JS-rendering pur (React/Vue) sans SSR.
- Login / paywall.
- Pas d'index public, uniquement newsletter privée.

## Sources de démarrage (V0)

Voir `config/sources.yml` (12 sources pour le premier run).

## Sources à instruire en priorité (V1)

| URL | Catégorie | Pays | Langue | Type estimé |
|---|---|---|---|---|
| https://www.transartists.org/en/air | Agrégateur | NL/Int. | EN | deep_html ✓ V0 |
| https://resartis.org/listings/ | Agrégateur | Int. | EN | deep_html ✓ V0 |
| https://on-the-move.org/funding/ | Agrégateur | Int. | EN/FR/ES | deep_html ✓ V0 |
| https://www.e-flux.com/announcements/ | Agrégateur | US/Int. | EN | deep_html ✓ V0 |
| https://www.cnap.fr/appels-projets | Institutionnel | FR | FR | deep_html ✓ V0 |
| https://www.institutfrancais.com/fr/programmes | Institutionnel | FR | FR | deep_html ✓ V0 |
| https://salondemontrouge.com/candidater/ | Prix / sélection | FR | FR | html ✓ V0 |
| https://www.citedesartsparis.net/fr/residences | Lieu / résidence | FR | FR | deep_html ✓ V0 |
| https://www.pollen-monflanquin.com/residences/ | Lieu / résidence | FR | FR | html ✓ V0 |
| https://hangar.org/es/convocatorias/ | Lieu / résidence | ES | ES | deep_html ✓ V0 |
| https://www.mataderomadrid.org/convocatorias | Lieu / résidence | ES | ES | deep_html ✓ V0 |
| https://www.curatorspace.com/opportunities | Agrégateur | UK | EN | à probe |
| https://www.callforentry.org/ | Agrégateur | US | EN | à probe |
| https://www.ensad-limoges.fr/ | École d'art | FR | FR | à probe |
| https://www.lefresnoy.net/fr | École d'art | FR | FR | à probe |
| https://www.villa-arson.org/ | École d'art | FR | FR | à probe |
| https://documentsdartistes.org/ (réseaux régionaux) | Réseau | FR | FR | à probe |
| https://www.fondation-camargo.org/ | Lieu / résidence | FR | FR/EN | à probe |
| https://www.molysabata.com/ | Lieu / résidence rural | FR | FR | à probe |
| https://prix-marcel-duchamp.com/ | Prix | FR | FR/EN | à probe |
| https://convocatorias.com/ | Agrégateur | LatAm | ES | à probe |
| https://www.bancaintesasanpaolo.com/aaa/ | Bourse / fondation | IT | IT/EN | à probe |

## Sources hors-périmètre (rejets francs)

- Vanity galleries (pay-to-show).
- Plateformes NFT / metavers.
- Open calls fermés (sur invitation uniquement).
- Concours strictement musicaux / dansés / théâtraux / cinématographiques (sans volet plastique).

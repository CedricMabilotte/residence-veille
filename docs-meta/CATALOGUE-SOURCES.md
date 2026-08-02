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

## Petits réseaux — annuaires et DRAC régionales (ajout 2026-08-02)

Vérifiées accessibles via recherche web en session (pas encore probées avec
`probe_source.py`, qui a un accès réseau direct plus fiable).

### Annuaires à crawler (`discovery_institutional_directories.py`, `discovery/annuaires.yml`)

| URL | Rôle | Rendement attendu |
|---|---|---|
| https://www.cnap.fr/annuaire/ | Annuaire CNAP des lieux (centres d'art, FRAC, écoles, assos) | Élevé — gisement direct d'organismes |
| https://andea.fr/en/andea/general-assembly/ | Membres ANdEA (44 écoles supérieures d'art) | Élevé — angle mort écoles non couvertes |
| https://www.ufisc.org/l-union/membres/ | Réseaux membres UFISC (lieux intermédiaires) | Incertain — plusieurs réseaux centrés musiques actuelles, filtrer disciplinaire |

### DRAC régionales "aide individuelle à la création" arts plastiques (à ajouter comme sources directes, pas comme annuaires)

| Région | URL |
|---|---|
| Auvergne-Rhône-Alpes | https://www.culture.gouv.fr/Regions/Drac-Auvergne-Rhone-Alpes/Demarches-aides/Demande-de-subvention/Aides-arts-plastiques |
| Occitanie | https://culture.gouv.fr/Regions/Drac-Occitanie/Aides-et-demarches/Subventions/Aides-Arts-plastiques |
| Île-de-France | https://www.culture.gouv.fr/Regions/Drac-Ile-de-France/Aides-et-demarches/Arts-plastiques |
| Hauts-de-France | https://www.culture.gouv.fr/Regions/Drac-Hauts-de-France/Aides-et-demarches/Arts-plastiques |
| Normandie | https://www.culture.gouv.fr/regions/drac-normandie/aides-et-demarches/aides-et-demarches-pour-la-creation-artistique-et-le-developpement-des-publics/aides-concernant-le-secteur-des-arts-plastiques2 |
| Bretagne | https://www.culture.gouv.fr/Regions/Drac-Bretagne/Aides-et-demarches/Arts-plastiques-cinema-livre-et-lecture-spectacle-vivant/Arts-visuels |
| Grand Est | https://www.culture.gouv.fr/regions/drac-grand-est/services/creation/arts-visuels |
| PACA | https://www.culture.gouv.fr/regions/Drac-Provence-Alpes-Cote-d-Azur/aides-demarches/aides-financieres/aides-aux-artistes-plasticiens |

Régions non trouvées en session (à rechercher individuellement, ne pas deviner
l'URL — les schémas varient trop d'une région à l'autre, cf. les 8 ci-dessus
qui n'ont que 2 patterns communs sur 8) : Bourgogne-Franche-Comté,
Centre-Val-de-Loire, Pays de la Loire, Corse, DAC outre-mer.

## Sources hors-périmètre (rejets francs)

- Vanity galleries (pay-to-show).
- Plateformes NFT / metavers.
- Open calls fermés (sur invitation uniquement).
- Concours strictement musicaux / dansés / théâtraux / cinématographiques (sans volet plastique).

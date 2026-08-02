# Instruction de démarrage — Fork de BIBLIO pour les opportunités arts plastiques

> Document de cadrage pour démarrer un fork du projet **BIBLIO** (`biblio`) appliqué à la veille des **opportunités pour plasticien·nes** : **résidences, bourses, prix et appels à exposition**, calibré (en interne) sur le profil de **Lucile Leloup** ([lucileloup.actitude.org](https://lucileloup.actitude.org/fr)).
>
> Date : 2026-05-19 — révisé après arbitrages utilisateur
> Auteur du brief : Ced
> Sous-domaine cible : **`residence.actitude.org`**

---

## 1. Pourquoi ce fork

BIBLIO veille sur des **ouvrages PDF** autour des communs fonciers et des paysanneries. L'architecture (scrape → score Claude → catalogue → site public `biblio.actitude.org`) est solide et réutilisable. On la déporte vers un autre **objet de veille** : les **opportunités professionnelles ouvertes aux plasticien·nes** — résidences, bourses, prix, appels à exposition.

Trois différences structurantes par rapport à BIBLIO conditionnent l'instruction de démarrage :

1. **Ce qu'on cherche n'est pas un fichier mais une opportunité datée.** Chaque appel a une date limite de candidature. Un appel expiré n'a plus aucune valeur. La temporalité est centrale, alors qu'un PDF reste utile dix ans.
2. **Le score ne suffit pas — il faut une fiche structurée.** Un livre = un score de pertinence. Une opportunité = un faisceau de critères (type, lieu, durée, dotation, conditions, discipline, public visé, critères d'éligibilité). On extrait, on ne se contente pas de noter.
3. **Le PDF est optionnel.** Beaucoup d'appels sont en HTML pur, ou s'accompagnent d'un dossier de candidature PDF qu'on peut archiver à part. Le pipeline doit accepter "pas de PDF" comme cas normal.

À cela s'ajoute une quatrième différence introduite par l'arbitrage **multi-catégories** : **on agrège quatre types d'opportunités** (résidences, bourses, prix, expositions) dans une **même base** — chaque type a ses spécificités à modéliser (voir §5 et §6).

---

## 2. Cadrage retenu (après arbitrages)

| Dimension | Choix |
|---|---|
| **Audience** | Outil public, calibré (en interne, invisible côté public) sur le profil de **Lucile Leloup** |
| **Catégories agrégées** | **Résidences + bourses + prix + appels à exposition** (4 types dans la même base, filtrables) |
| **Livrable** | Fiches structurées + calendrier des dates limites + site public + archivage PDF si dispo + extraction des critères d'éligibilité |
| **Discipline** | **Strictement arts plastiques** (exclure musique, danse, cinéma, écriture pure — accepter transdisciplinaire avec volet plastique) |
| **Géographie** | **International** (FR, Europe, Amérique du Nord, Amérique latine, Afrique, Asie, Océanie) |
| **Langues sources** | **FR, EN, ES** (scraping multilingue) |
| **Langue interface** | **FR uniquement** côté public — les contenus FR sont publiés tels quels ; EN/ES extraits sont résumés en FR par le pipeline |
| **Sous-domaine** | **`residence.actitude.org`** (au singulier) |
| **Newsletter** | **Différée** — l'infrastructure `newsletter.py` reste en place, désactivée |
| **Bias Leloup** | **Invisible côté public** — actif uniquement dans le scoreur Claude (concepts.yml) |
| **Cross-pollination BIBLIO** | **Cloisonné** — pas d'échange via `share_sources.py` |

### Calibrage sur le profil de Lucile Leloup (interne)

Sa pratique oriente **le scoring uniquement** (rien sur le site public ne mentionne ce profil). Le biais reste doux : on accepte large mais on note plus haut les opportunités qui résonnent avec :

- **disciplines** : installation, textile, feutre, dessin, écriture & poésie contemporaine, performance ;
- **territoire** : rural ou paysan, paysage, matériaux locaux (laine, bois, chanvre, lin) ;
- **valeurs** : dynamiques collectives, artisanat, lien art / agriculture paysanne / mémoires rurales ;
- **conditions** : atelier + hébergement + rémunération, durée >= 2 semaines (pour résidences) ; dotation décente (pour bourses/prix) ; lieux d'exposition reconnus dans le réseau art contemporain (pour expositions).

Le site reste utile à tout·e plasticien·ne francophone.

---

## 3. Adaptation de l'architecture BIBLIO

### Ce qui change

| Composant BIBLIO | Adaptation Résidences |
|---|---|
| `config/sources.yml` (sites de PDF) | `config/sources.yml` (sites d'appels à résidences) — voir §4 |
| `config/concepts.yml` (ontologie communs/terres) | `config/concepts.yml` (ontologie résidences arts plastiques) — voir §5 |
| Scoring sur titre + contexte | Scoring + **extraction structurée** (lieu, dates, conditions, éligibilité) |
| `docs/` (PDFs téléchargés) | `appels/` (fiches JSON/YAML par résidence) + `pdfs/` (dossiers de candidature optionnels) |
| `synopsis/catalog.json` | `catalog/residences.json` avec champs structurés |
| `interface/index.html` (fiches synopsis) | `interface/index.html` **+ tri par date limite + filtre par discipline/géographie** |
| `bulles/` (publications éditoriales) | `alertes/` (deadlines J-30, J-14, J-7) |
| Discovery (OpenAlex, Semantic Scholar, Mastodon) | Discovery (mailing lists artistes, RSS DRAC, agrégateurs : Resartis, Transartists, On-the-Move, Documents d'artistes) |

### Ce qui reste identique

- L'ossature Python + GitHub Actions + scoring Claude Haiku via OAuth
- Le pattern `parsers/` (html, deep_html, rss) — on **réutilise tel quel** html, deep_html, rss
- La logique `dedup.py` (déduplication URL)
- Le pipeline `webhooks.py` (Discord/Slack/Mastodon) — utile pour pousser les nouveaux appels
- L'export `share_sources.py` (cross-pollination entre forks)
- Le déploiement vers un repo public + GitHub Pages

### Ce qu'on retire ou désactive d'abord

- `pdf_processor.py` (validation MIME / extraction texte) — **retiré du chemin obligatoire**, branché en option si un appel est accompagné d'un PDF de dossier
- `synopsis_enricher.py` (couverture PNG page 1) — **retiré**, remplacé par capture HTML de la page d'appel
- `bibliography_extractor.py` (références dans le PDF) — **retiré**
- Parsers `opds`, `hal`, `archive_org` — **retirés** (sans objet pour les résidences)
- `fulltext_index.py` — **différé** (utile si on indexe le texte des appels)

### Ce qu'on ajoute

- `parsers/jsonld_event.py` : extraction Schema.org/Event présent sur beaucoup de sites d'appels institutionnels
- `extract_residency.py` : appel Claude (Haiku) qui prend la page d'un appel et retourne un JSON structuré (voir §6)
- `deadline_tracker.py` : moteur de tri / archivage des appels expirés, calcul d'alertes J-30 / J-14 / J-7
- `interface/calendar.html` : vue calendrier ICS exportable

---

## 4. Sources à instruire (premier cercle, 4 catégories)

Validation à faire en `probe_source.py` (déjà existant). Sources organisées par catégorie d'opportunité — beaucoup couvrent plusieurs types simultanément (un agrégateur listera à la fois résidences, bourses, prix, expositions).

### A. Agrégateurs internationaux multi-types (à privilégier)

- **TransArtists** (NL, EN) — `https://www.transartists.org/en/air`
- **Res Artis** (EN) — `https://resartis.org/listings/`
- **On-the-Move** (EN, FR, ES) — `https://on-the-move.org/funding/`
- **Curator Space** (EN) — `https://www.curatorspace.com/opportunities`
- **Rhizome / Art Opportunities Monthly** (EN)
- **DutchCulture / TransArtists open calls** (NL/EN)
- **CallforEntry / CaFÉ** (EN, US — expositions + prix)
- **e-flux open calls** (EN — résidences + bourses + appels expo internationaux)

### B. Institutionnels FR / francophones (résidences + bourses + prix)

- **CNAP** — résidences, **prix CNAP**, allocations de recherche
- **DRAC** (régions FR) — appels à projets, aides individuelles à la création
- **Institut français** — résidences internationales, **Villa Albertine, Villa Médicis, Casa de Velázquez**
- **FRAC** régionaux — résidences associées, expositions
- **Documents d'Artistes** réseaux régionaux (PACA, Bretagne, Auvergne-Rhône-Alpes…)
- **Réseau Diagonal** (photographie / art contemporain)
- **Astre, Devenir.art, ADAGP** (newsletters)
- **ADAGP — bourses et prix** (action culturelle)
- **Fondation des Artistes** (Paris) — bourses
- **Centre national d'art et de culture Pompidou** — bourses recherche & résidences

### C. Prix et concours (catégorie nouvelle)

- **Prix Marcel Duchamp** (ADIAF)
- **Prix AICA France**
- **Salon de Montrouge** — sélection annuelle artistes émergents
- **Prix Drawing Now** (foire dessin contemporain)
- **Prix Aware** (femmes artistes)
- **Prix Fondation Pernod Ricard**
- **Prix Fondation d'entreprise Ricard**
- **Prix Marcel Bleustein-Blanchet pour la Vocation**
- **Prix Société Générale de la Photographie**
- **Prix HSBC pour la Photographie**
- **Hyères — Festival photo & mode** (prix photo)
- **Prix Niépce / Nadar**
- **Prix Mario Merz** (international)

### D. Appels à exposition (catégorie nouvelle)

- **Salon de Montrouge** (appel à candidature annuel)
- **Biennale de Lyon, Manifesta, Documenta** (appels à projets curatoriaux)
- **JeunesArtistes.fr** — appels expositions FR
- **Biennale internationale de Mulhouse** (Mulhouse 0xx)
- **Foires off** (Drawing Now off, Asia Now off, etc.)
- **Centres d'art labellisés** — appels à projets exposition (page "Appels" sur les sites)
- **Centres d'art municipaux & associatifs** — programmation par appel
- **Réseau Tram (Île-de-France)** — appels associés à ses lieux
- **Réseau d.c.a. (association des centres d'art contemporain)**

### E. Lieux et fondations (résidences au cas par cas)

- **Fondation Camargo** (Cassis)
- **Triangle France — Astérides** (Marseille)
- **Cité internationale des arts** (Paris)
- **Pollen** (Monflanquin) — territoire rural
- **Domaine de Boisbuchet** — design / matériaux
- **Moly-Sabata** — résidence rurale
- **Casa Wabi / Fountainhead / MASS MoCA Studios / Banff Centre** (international)

### F. Sources hispanophones (multi-types)

- **Hangar Barcelona** (ES) — résidences, expositions
- **MATADERO Madrid** — résidences, prix, expositions
- **Plataforma de Arte Contemporáneo PAC** — appels (ES)
- **Convocatorias.com** (LatAm) — agrégateur multi-types
- **Iberescena / Ibermuseos** (filtrer arts visuels)
- **Premio Velázquez de las Artes** (ES)
- **Generaciones — Fundación Montemadrid** (jeunes artistes, ES)

**Note** : un même site liste souvent **plusieurs types** simultanément. Le pipeline `detect_type.py` classera chaque item individuellement. Les flux RSS d'institutions (CNAP, DRAC) mélangent typiquement résidences + bourses + prix.

---

## 5. Ontologie (proposition `concepts.yml`)

```yaml
project:
  name: "opportunites-arts-plastiques"
  display_name: "Résidence — opportunités arts plastiques"
  tagline: "Veille internationale des résidences, bourses, prix et appels à exposition ouverts aux plasticien·nes."
  description: >
    Agrégation et tri des opportunités ouvertes aux plasticien·nes dans le monde :
    résidences, bourses, prix et appels à exposition. Extraction structurée
    des conditions, des critères d'éligibilité et des dates limites.
    Interface en français, sources multilingues (FR, EN, ES).
  languages_sources: [fr, en, es]
  language_interface: fr

ontology:
  # ─── 4 types d'opportunités, agrégés dans une même base ─────────────────
  opportunity_types:

    - id: "residence"
      label_fr: "Résidence"
      definition: >
        Dispositif d'accueil temporaire d'un·e artiste dans un lieu qui met
        à disposition un espace de travail, parfois un hébergement et une
        rémunération, en vue d'une production, d'une recherche ou d'une
        restitution.
      required_signals:
        - dispositif d'accueil physique sur place
        - durée définie (jours / semaines / mois)
        - date limite de candidature future
        - candidature ouverte (pas d'invitation uniquement)
      equivalents:
        fr: ["résidence d'artiste", "résidence de création", "résidence de recherche"]
        en: ["artist residency", "artist-in-residence", "AIR", "residency program"]
        es: ["residencia artística", "residencia de artistas"]

    - id: "bourse"
      label_fr: "Bourse"
      definition: >
        Soutien financier accordé à un·e artiste pour développer un projet,
        une recherche, une production ou une formation, sans nécessairement
        impliquer une présence physique dans un lieu.
      required_signals:
        - dotation monétaire
        - candidature ouverte
        - date limite future
      equivalents:
        fr: ["bourse", "aide à la création", "aide à la recherche", "soutien à la production", "aide individuelle"]
        en: ["grant", "fellowship", "stipend", "production grant", "research grant"]
        es: ["beca", "ayuda económica", "subvención"]

    - id: "prix"
      label_fr: "Prix"
      definition: >
        Distinction attribuée à un·e artiste à l'issue d'un processus de
        sélection (jury, vote), comprenant généralement une dotation
        monétaire, une exposition, ou une publication.
      required_signals:
        - processus de sélection compétitif
        - dotation (monétaire, exposition, édition, achat)
        - candidature ouverte (≠ prix sur nomination uniquement)
        - date limite future
      equivalents:
        fr: ["prix", "concours", "lauréat·e", "récompense"]
        en: ["prize", "award", "competition", "open competition"]
        es: ["premio", "concurso", "certamen"]

    - id: "exposition"
      label_fr: "Appel à exposition"
      definition: >
        Appel à candidatures pour participer à une exposition collective ou
        personnelle dans un lieu d'art, festival, biennale, salon ou espace
        alternatif. Inclut les appels à projets curatoriaux portés par des
        artistes.
      required_signals:
        - exposition publique programmée
        - sélection par dossier ou jury
        - date limite future
      equivalents:
        fr: ["appel à candidature exposition", "appel à projets exposition", "open call exposition", "appel à artistes"]
        en: ["open call exhibition", "call for artists", "call for proposals", "submissions"]
        es: ["convocatoria de exposición", "convocatoria artistas"]

  # ─── Champs à extraire (varient selon le type) ─────────────────────────
  to_extract_all_types:
    - type (residence | bourse | prix | exposition)
    - nom de l'opportunité
    - organisme porteur
    - lieu (ville, pays, territoire)
    - date limite de candidature
    - url de candidature
    - langue(s) du dossier
    - frais d'inscription (montant, devise)
    - pièces demandées
    - critères d'éligibilité (nationalité, âge, niveau de carrière, discipline)
    - dotation / conditions matérielles (voir ci-dessous selon type)

  to_extract_by_type:
    residence:
      - durée (semaines, dates)
      - hébergement (oui / non / partiel)
      - atelier (m², équipements)
      - per diem / rémunération (montant, devise, périodicité)
      - voyage pris en charge (oui / non / plafond)
      - restitution attendue (exposition, édition, conférence)
    bourse:
      - montant (devise)
      - finalité (production, recherche, formation, mobilité)
      - calendrier d'usage des fonds
      - obligations de rendu
    prix:
      - dotation (montant, exposition, achat, édition)
      - composition du jury (si publiée)
      - nombre de lauréat·es prévu
      - éditions précédentes (track record)
    exposition:
      - lieu(x) d'exposition
      - dates d'exposition
      - format (collective, personnelle, festival, biennale)
      - prise en charge production / transport / per diem
      - vernissage / restitution

  # ─── Disciplines (commun aux 4 types) ──────────────────────────────────
  disciplines_acceptees:
    - installation
    - sculpture
    - textile / feutre / fibres
    - dessin
    - peinture
    - photographie
    - vidéo / film d'artiste
    - performance
    - édition / livre d'artiste
    - écriture (uniquement si volet plastique)
    - art sonore (uniquement si volet plastique)
    - art et écologie / land art
    - art textile / craft contemporain
    - art et agriculture / art paysan
    - pratiques transdisciplinaires (si volet plastique explicite)

  disciplines_exclues:
    - musique pure (composition, interprétation classique)
    - danse pure
    - théâtre, dramaturgie
    - cinéma narratif / fiction longue
    - écriture littéraire / romanesque pure
    - journalisme
    - recherche académique sans production plastique

  # ─── Bias profil Leloup (INTERNE, jamais affiché côté public) ──────────
  affinites_profil_interne:
    description: >
      Bonus de scoring (+1) appliqué silencieusement quand l'opportunité
      résonne avec la pratique calibrée. AUCUN affichage côté site public —
      le profil reste invisible aux usagers.
    signaux:
      - territoire rural / paysan
      - matériaux locaux / sourcés (laine, bois, chanvre, lin)
      - lien artisanat / art contemporain
      - dimension collective ou participative
      - mémoire / patrimoine immatériel
      - écriture / poésie comme outil
      - durée longue (≥ 4 semaines) pour résidences

  # ─── Anti-concepts (rejets francs) ─────────────────────────────────────
  anti_concepts:
    - opportunité sur invitation uniquement (pas d'open call)
    - opportunité réservée aux disciplines strictement non-plastiques
    - formations payantes déguisées (artiste paye > il reçoit)
    - vente d'espace atelier déguisée en résidence
    - workshops / masterclass < 1 semaine
    - "résidences" / "prix" NFT / metavers / blockchain
    - prix / appels avec fee > 100 € sans dotation proportionnée
    - appels prédateurs (vanity galleries, pay-to-show abusif)
    - opportunités destinées à des mineurs (< 18 ans)

editorial:
  voice: "factuel + utile, sobre"
  language_public: fr
  audience: >
    Artistes plasticien·nes francophones qui cherchent un flux fiable
    d'opportunités internationales triées par date limite.
  tone_examples:
    - "Résidence — 8 semaines au Limousin, hébergement et atelier compris, per diem 600€/semaine. Date limite : 15 juillet."
    - "Bourse — aide à la production 5000€, ouvert aux plasticien·nes émergent·es, dossier en français. Date limite : 30 juin."
    - "Prix — dotation 10 000€ + exposition au lauréat, jury international. Date limite : 1er octobre."
    - "Appel à exposition — biennale internationale photographie + installation, prise en charge transport, vernissage automne 2027. Date limite : 12 août."

scoring:
  threshold: 6
  strict_mode: true

  rules:
    - "Si la date limite est passée → score 0 (exclu)."
    - "Si l'opportunité ne correspond à aucun des 4 types → score 0."
    - "Si la discipline acceptée est exclusivement non-plastique → score 0."
    - "Si payant pour l'artiste et dotation < frais (résidence loyer > rétribution, prix fee > dotation) → score 1."
    - "Si open call international, conditions correctes, ouvert aux plasticien·nes → score 7+."
    - "Si bonus profil interne (ruralité, textile, collectif…) → +1 silencieux."
    - "Critères d'éligibilité absents → score max 5 (instruire manuellement)."
    - "Source non FR/EN/ES → résumer en FR avant extraction."
```

---

## 6. Schéma de fiche (sortie type, 4 variantes)

Le pipeline produit une fiche par opportunité, dans `appels/{type}/{slug}-{uid}.yml`. Un **bloc commun** + un **bloc spécifique au type**.

### Bloc commun (toujours présent)

```yaml
uid: "8a3f2c11"
type: "residence"               # residence | bourse | prix | exposition
source_url: "https://example.org/opportunities/foo-2026"
fetched_at: "2026-05-19T14:32:00Z"
score: 8
status: "ouverte"               # ouverte | bientot-fermee | expiree | sur-invitation

opportunite:
  nom: "Résidence Foo"
  organisme: "Fondation Foo"
  lieu:
    ville: "Cassis"
    pays: "France"
    territoire: "littoral méditerranéen"

candidature:
  date_limite: "2026-07-15"
  # candidature_continue (ajouté 2026-08-02, leçon L3) : true si l'opportunité
  # n'a délibérément PAS de date limite fixe — candidature au fil de l'eau,
  # généralement une résidence autofinancée (ex. O Castro Art Village). Distinct
  # d'une simple absence de date_limite par lacune d'extraction : deadline_tracker.py
  # calcule le statut "ouverte-continue" uniquement si ce champ est explicitement
  # true, sinon une fiche sans date_limite reste "indetermine" (donnée à corriger).
  # Champ optionnel, absent ou false par défaut.
  candidature_continue: false
  langue_dossier: ["fr", "en"]
  langue_source: "en"           # langue de la page d'appel (pour résumé FR si != fr)
  frais_inscription: { montant: 0, devise: "EUR" }
  pieces_demandees:
    - "dossier artistique (20 visuels)"
    - "note d'intention (3 pages)"
    - "CV"
  url_candidature: "https://example.org/apply"
  pdf_appel: "pdfs/8a3f2c11-appel.pdf"   # optionnel

eligibilite:
  disciplines: ["installation", "sculpture", "textile", "performance"]
  niveau_carriere: "émergent·e ou confirmé·e"
  age_max: null
  nationalite: "sans restriction"
  residence_administrative: "sans restriction"

# ─── Bonus interne, JAMAIS affiché sur le site public ───
_interne_affinite:
  match: true
  signaux: ["ruralité", "textile", "collectif"]
  bonus_score: 1

_meta:
  extracted_by: "claude-haiku-4-5"
  extracted_confidence: 0.92
  resume_fr: "Court résumé FR généré si la source n'est pas en français."
```

### Bloc spécifique — `type: residence`

```yaml
conditions_residence:
  duree: { semaines: 8, dates: "septembre - octobre 2026" }
  hebergement: true
  atelier: "50 m² avec lumière naturelle"
  remuneration: { montant: 600, devise: "EUR", periodicite: "semaine" }
  voyage: { pris_en_charge: true, plafond: 800, devise: "EUR" }
  restitution: "exposition collective"
```

### Bloc spécifique — `type: bourse`

```yaml
conditions_bourse:
  montant: { montant: 5000, devise: "EUR" }
  finalite: "production"         # production | recherche | formation | mobilite
  calendrier_usage: "12 mois à compter de l'attribution"
  obligations_rendu: ["rapport final", "mention du soutien dans les supports"]
```

### Bloc spécifique — `type: prix`

```yaml
conditions_prix:
  dotation:
    montant: { montant: 10000, devise: "EUR" }
    exposition: true
    achat_oeuvre: false
    edition_catalogue: true
  jury_public: ["nom1", "nom2"]
  nb_laureats: 1
  editions_precedentes: ["2024", "2025"]   # track record
```

### Bloc spécifique — `type: exposition`

```yaml
conditions_exposition:
  lieux: ["Centre d'art Foo, Paris"]
  dates_exposition: "novembre 2026 - février 2027"
  format: "collective"            # collective | personnelle | festival | biennale
  prise_en_charge:
    production: true
    transport: { pris_en_charge: true, plafond: 500, devise: "EUR" }
    per_diem: false
    hebergement_vernissage: true
```

Le moteur **`extract_opportunity.py`** appelle Claude Haiku avec un prompt qui **détecte le type d'abord**, puis demande le schéma adapté. Confidence < 0.7 → fiche mise en quarantaine manuelle.

### 6.bis Dédup inter-sources — schéma complété

Quand la même opportunité est détectée sur plusieurs sources (ex. un prix CNAP listé aussi sur e-flux), on **fusionne en une seule fiche** avec :

```yaml
candidature:
  url_canonique: "https://www.cnap.fr/prix-foo-2026"          # site de l'organisme porteur
  urls_secondaires:
    - { source: "e-flux", url: "https://www.e-flux.com/announcements/123/prix-foo-2026/" }
    - { source: "TransArtists", url: "https://www.transartists.org/calls/prix-foo-2026" }
  url_candidature: "https://www.cnap.fr/prix-foo-2026/candidater"
```

**Règle de canonicité** (`dedup.py` à adapter) :

1. URL pointant vers le **domaine de l'organisme porteur** identifié dans `opportunite.organisme` → canonique.
2. À défaut, URL ne contenant **aucun querystring de tracking** (`?utm_*`, `?ref=*`).
3. À défaut, URL la **plus ancienne dans `fetched_at`** (priorité historique).
4. Les autres sources sont conservées dans `urls_secondaires` (utile pour la fraîcheur — si une source meurt, on a un fallback).

**Clé de dédup** : `(opportunite.organisme normalisé) + (opportunite.nom normalisé) + (candidature.date_limite)`. Une similarité ≥ 0.85 sur les deux premiers champs + date limite identique → même fiche.

### 6.ter Titre bilingue

```yaml
opportunite:
  nom: "Open Call for Visual Artists 2027"          # titre original
  nom_fr: "Appel à plasticien·nes 2027"             # traduction Haiku, si source != fr
  affichage_titre: "Open Call for Visual Artists 2027 [Appel à plasticien·nes 2027]"
```

L'interface utilise `affichage_titre` pour les listes et la home. La recherche full-text indexe `nom` + `nom_fr` + `_meta.resume_fr`.

---

## 7. Pipeline final

```
config/sources.yml          ← URLs agrégateurs + institutionnels + lieux + prix + appels expo
   ↓ scripts/watch.py
   ↓   ├── scrape (parsers html / deep_html / rss / jsonld_event)
   ↓   ├── detect_type.py       → residence | bourse | prix | exposition
   ↓   ├── extract_opportunity.py → fiche YAML structurée (schéma par type)
   ↓   ├── score Claude (concepts.yml + bias profil interne)
   ↓   ├── deadline_tracker.py  → tri ouverte / bientôt / expirée
   ↓   ├── (si source EN/ES) → resume_fr.py via Claude Haiku
   ↓   └── (optionnel) download PDF dossier de candidature
   ↓
appels/{type}/{slug}.yml + pdfs/ + alertes/
   ↓ génère interface/ (en FR uniquement)
   ↓   ├── index.html         (home — opportunités ouvertes, filtres riches)
   ↓   ├── archive.html       (opportunités expirées, consultables)
   ↓   ├── calendar.html      (vue calendrier global avec filtres)
   ↓   ├── calendar.ics       (fichier ICS unique, contient toutes les ouvertes)
   ↓   ├── feed/all.xml       (flux RSS global)
   ↓   ├── feed/residences.xml
   ↓   ├── feed/bourses.xml
   ↓   ├── feed/prix.xml
   ↓   ├── feed/expositions.xml
   ↓   └── alertes/           (J-30 / J-14 / J-7)
   ↓
GitHub Actions → publication → residence.actitude.org
   ↓
(webhooks.py désactivé tant que newsletter différée — infra en place)
```

Note : pas d'échange `share_sources.py` avec BIBLIO (cloisonnement décidé).

---

## 8. Plan de démarrage en 5 étapes

| Étape | Quoi | Estimation |
|---|---|---|
| **1. Bootstrap** | Cloner `biblio` dans `Residences artistiques`. Retirer `pdf_processor.py` (chemin obligatoire), `synopsis_enricher.py`, `bibliography_extractor.py`, parsers `opds`/`hal`/`archive_org`. Garder `parsers/html.py`, `deep_html.py`, `rss.py`. Désactiver `webhooks.py` (mais garder le code). Vider `docs/`, `synopsis/`, `bulles/`, `discovery/`, `share_sources.py`. | 1 séance |
| **2. Ontologie** | Écrire `config/concepts.yml` (proposition §5 — **4 types : residence / bourse / prix / exposition**). Calibrer le bias profil interne (silencieux côté public). | 1 séance |
| **3. Sources** | Probe les sources prioritaires (§4) avec `probe_source.py`. Étendre la liste vers **prix et appels à exposition** (CNAP prix, Marcel Duchamp, AICA, Salon de Montrouge, biennales, etc.). Garder celles ≥ 5 items/run. Remplir `config/sources.yml`. | 2 séances |
| **4. Extraction** | Écrire `detect_type.py` (classifier les 4 types) + `extract_opportunity.py` (Claude Haiku → JSON schéma §6 selon le type). Écrire `resume_fr.py` pour traduire/résumer EN/ES en FR. Tester sur 20 opportunités manuelles couvrant les 4 types. Itérer jusqu'à 90 % de bon remplissage. | 3 séances |
| **5. Interface FR + déploiement** | Adapter `interface/index.html` (FR uniquement, tri date limite, filtres par type / discipline / pays). Ajouter `calendar.html`. Workflow GH Actions + repo public `residence-actitude-org`. CNAME `residence.actitude.org`. | 2 séances |

À chaque étape : commiter, faire tourner un run en `dry_run: true`, vérifier la sortie.

---

## 9. Premiers garde-fous

- **Fraîcheur** : `deadline_tracker.py` doit faire tourner un cron quotidien — un appel expiré ne doit pas rester sur la home plus de 24 h.
- **Classification fiable** : les sites mélangent les 4 catégories. `detect_type.py` doit pouvoir trancher avec une **confidence** ≥ 0.7 — sinon quarantaine manuelle. Un item peut être hybride (résidence + exposition à la sortie) : on choisit le type **primaire** (ce que reçoit l'artiste, pas ce qu'il rend).
- **Anti-faux-positif « candidature ouverte »** *(ajouté 2026-08-01, suite à L1)* : les mots-clés de domaine (`TYPE_KEYWORDS`) ne suffisent pas à distinguer un vrai appel d'une page d'annuaire/bilan — "résidence" apparaît autant dans "nos résidents 2024" que dans "candidatez à notre résidence". `detect_type.py` calcule désormais un signal indépendant (`open_call_signal()` : verbe d'appel type "candidatez/apply now", marqueur d'échéance, date future, moins les marqueurs rétrospectifs comme "a eu lieu"/"alumni"/"vernissage", avec gestion des négations du type "n'est pas un appel à candidature") et **plafonne la confidence** en conséquence (`_apply_open_call_guardrail`), quel que soit le score de mots-clés de domaine. Un signal faible + marqueurs rétrospectifs ⇒ confidence plafonnée à 0.2 ; un signal ambigu ⇒ plafonnée à 0.65 — les deux paliers restent sous le seuil `scoring.auto_promote.min_confidence` de `concepts.yml` (0.70 en V0 exploratoire, cible 0.85 une fois calibré), donc bloquants quel que soit celui des deux en vigueur. Seul un signal fort (≥ 0.5) n'est pas plafonné. Testé sur les fiches quarantainées en session (Cité internationale des arts, Rurart).
- **Faux négatifs PDF** : beaucoup d'appels sont en PDF uniquement (pas en HTML). Prévoir un fallback PDF → texte → Claude pour ces cas (réutiliser un bout de `pdf_processor` de BIBLIO, branché en option et non sur le chemin obligatoire).
- **Loyer déguisé / pay-to-play** : red flag absolu (résidences-arnaques, vanity galleries). Anti-concept à expliciter dans `concepts.yml` — vérifier ratio dotation / fee.
- **Privacy / mineurs** : certains appels jeunes-artistes ont des conditions d'âge minimal. Ne pas amplifier d'appels destinés à des mineurs (< 18 ans) sans vérification.
- **Profil interne ne fuite pas** : le champ `_interne_affinite` n'est **jamais** publié sur le site. Le générateur HTML doit ignorer tous les champs préfixés `_`. À tester explicitement avant déploiement.
- **Résumé FR fidèle** : pour les sources EN/ES, `resume_fr.py` doit citer littéralement les chiffres (montant, dates, m²) sans paraphraser — diviser entre "résumé éditorial FR" et "données structurées brutes".

---

## 10. Arbitrages validés (sortis des questions ouvertes)

| Question | Décision |
|---|---|
| **1. Nom et sous-domaine** | `residence.actitude.org` (singulier, cohérent avec `biblio.actitude.org` et `lucileloup.actitude.org`). Repo public : `residence-actitude-org`. |
| **2. Langue de l'interface** | **FR uniquement**. Les sources EN/ES sont scrapées, mais résumées en FR par `resume_fr.py`. Les données brutes (montants, dates) sont citées telles quelles. |
| **3. Newsletter** | **Différée**. L'infra `newsletter.py` reste en place mais désactivée dans le workflow. À réactiver plus tard (V2). |
| **4. Profil Leloup** | **Implicite et invisible** côté public. Actif uniquement dans `concepts.yml` (bonus de scoring silencieux). Le champ `_interne_affinite` n'est jamais publié. |
| **5. Cross-pollination BIBLIO** | **Cloisonné**. Pas d'échange via `share_sources.py`. Les deux projets vivent leur vie. La logique reste copiable depuis BIBLIO mais aucun lien runtime. |
| **6. Catégories agrégées** *(ajout utilisateur)* | **4 types** : résidence, bourse, prix, exposition — agrégés dans la même base, classifiés par `detect_type.py`, schémas spécialisés par type (§6), filtrables côté interface. |

---

## 11. Arbitrages d'implémentation (validés)

| Sujet | Décision |
|---|---|
| **Dédup inter-types** | **Une seule fiche par opportunité, plusieurs liens.** L'URL canonique = celle de l'organisme porteur. Les liens des agrégateurs (e-flux, TransArtists, etc.) sont ajoutés dans `candidature.urls_secondaires` (voir §6.bis). |
| **Calendrier ICS** | **Un fichier global** `residence.actitude.org/calendar.ics` avec **filtres riches** côté interface (par type, discipline, pays, fourchette de deadline, gratuité). Le fichier ICS contient toutes les fiches ouvertes ; les filtres opèrent côté HTML/JS sur la même base. |
| **Flux RSS** | **Un flux par type** : `/feed/residences.xml`, `/feed/bourses.xml`, `/feed/prix.xml`, `/feed/expositions.xml`. Plus un flux global `/feed/all.xml`. Utile même sans newsletter — les utilisateurs s'abonnent à ce qui les intéresse. |
| **Archivage des expirées** | **Conservées en archive consultable.** Section `/archive/` séparée de la home (qui ne montre que les ouvertes). Les fiches expirées gardent leur valeur documentaire (track record d'un prix, conditions d'éditions précédentes, repérage des cycles annuels). Aucune suppression. |
| **Titres bilingues** | **Original + traduction FR entre crochets.** Exemple : `"Open Call for Visual Artists 2027 [Appel à plasticien·nes 2027]"`. La traduction FR est générée par `resume_fr.py` (Claude Haiku). Le champ `nom` du YAML contient le titre original ; `nom_fr` la traduction. L'interface affiche l'un ou l'autre selon le contexte (titre = original + crochets ; recherche full-text = les deux). |

---

## 12. Mécanismes de découverte de sources

L'objectif est de faire **vivre** le `config/sources.yml` au-delà de la liste initiale du §4. BIBLIO a démontré qu'un système de découverte est viable mais souffre d'un goulot d'étranglement (1 096 candidats accumulés pour 234 fiches validées). On garde ce qui marche, on retire ce qui est sans objet, on invente ce qui manque, et on **passe en auto-promotion** pour éviter le goulot.

### 12.1 Briques BIBLIO réutilisées telles quelles

| Mécanisme | Rôle | Fréquence |
|---|---|---|
| `discovery_external_links.py` | Capture passive des `<a href>` vers domaines tiers pendant le scrape | À chaque run |
| `discovery_mastodon.py` | Hashtags / comptes Mastodon — adaptés au domaine art | Hebdo |
| `discovery_llm_suggest.py` | Claude Haiku suggère N nouvelles sources à partir du catalog + ontologie | Mensuel |
| `discovery_blind_spots.py` | Auto-diagnostic statistique (langues, pays, types, disciplines manquantes) + Claude | Mensuel |
| Issues GitHub `nouvelle-source` | Cross-pollination communautaire (un·e artiste propose une source) | À la demande |

**Hashtags Mastodon retenus** : `#opencall #appelacandidature #residenceartiste #artistresidency #convocatoria #appelaprojets #appelaartistes #aircall #residencia #residencyopen`.

**Comptes à suivre** (à instruire) : `@cnap@mastodon.social`, comptes des FRAC, e-flux, comptes d'artistes-veilleurs reconnus du milieu.

### 12.2 Briques BIBLIO retirées

- `discovery_footnotes.py` (pas de NBP dans les appels HTML — **mais on en garde une variante en §12.5/G**, pour les logos partenaires)
- `discovery_bibliography.py` (pas de bibliographies)
- `discovery_openalex.py` / `discovery_semantic_scholar.py` (académique)
- `discovery_promote.py` (DOI → Unpaywall sans objet)

### 12.3 Mécanismes nouveaux retenus (validés utilisateur)

**A. Cycles annuels** — `discovery_cycles.py`

À chaque fiche qui expire, le moteur regarde si l'opportunité comporte un millésime (`Prix Foo 2026`, `Résidence 2025-2026`). Si oui :
- enregistrer une **prédiction** dans `discovery/cycles.yml` : `{organisme, type, prochaine_edition_estimee, fenetre_surveillance, url_a_surveiller}` ;
- activer un crawl ciblé sur l'URL d'organisme à `prochaine_edition_estimee - 60 jours` jusqu'à `+ 60 jours` ;
- si la prédiction se confirme (nouvelle fiche détectée dans la fenêtre) → renforcer le score de fiabilité du cycle ; sinon → relâcher.

Stockage : `discovery/cycles.yml` indexé par organisme + type d'opportunité.

**B. Graphe de partenariats** — `discovery_partnerships.py`

Pendant l'extraction Claude (§6), un champ supplémentaire est demandé : `partenaires[]` (organismes mentionnés dans la page d'appel — financeurs, lieux associés, soutiens). Ces noms d'organismes sont ajoutés à un graphe `discovery/organismes-graph.yml` avec leurs occurrences. Un organisme cité ≥ 3 fois dans des fiches connues mais sans fiche organisme propre → candidat à instruire en priorité.

**C. Crawl des pages "Réseau / Liens / Partenaires"** — `discovery_network_pages.py`

Heuristique : pour chaque domaine d'organisme connu, tester l'existence de pages dont l'URL contient `/reseau`, `/liens`, `/partenaires`, `/partners`, `/network`, `/links`, `/about/partners`, `/colaboradores`. Si trouvée, deep-crawl 1 niveau pour extraire les domaines mentionnés. Source typique : pages "Réseau" du Tram, d.c.a., Documents d'Artistes.

**D. Pages d'actualités d'écoles d'art** — sources curées dans `config/sources.yml`

Pas un mécanisme à part, mais une **catégorie de sources** à ajouter en dur : pages "Actualités" / "Opportunités" / "Vie après l'école" des écoles d'art (Ensad, Ensba, Ensad Limoges, Le Fresnoy, Villa Arson, ESBA Nantes, EESI Poitiers-Angoulême, Beaux-Arts régionaux). Ces pages sont des **agrégateurs naturels** d'appels pour diplômé·es.

**E. Newsletters CAAP / USOPAV / syndicats**

Deux options techniques :
- **Web-first** : crawler les sites publics où ces organisations archivent les appels (CAAP, USOPAV, Profession Plasticien·ne, La Buse).
- **Email-fallback** : créer une adresse dédiée `residence@actitude.org`, s'abonner aux newsletters, puis pipeline IMAP → extract Claude. **Différé V2** (complique l'opérationnel, infra mail à monter).

Démarrage : Web-first uniquement.

**F. Tags Instagram** — `discovery_instagram.py` (V2, expérimental)

Pas d'API publique fiable. Deux pistes :
- scraping via Playwright sur les pages publiques `#opencall` etc. — fragile et à la frontière éthique ;
- agréger des comptes-veille tiers (`@residencyhopper`, etc.) qui republient les opportunités.

**Démarrage : reporté en V2**, mais on garde une issue ouverte. Risque de bannissement IP + dette éthique non triviale.

**G. Logos / mentions partenaires dans les PDFs d'appels** — `discovery_pdf_partners.py`

Variante de `footnotes` adaptée. Quand un PDF d'appel est téléchargé :
- extraction OCR/texte du bas de page (zone logos) ;
- repérage des noms d'organismes (heuristique `MAJUSCULES`, `Fondation`, `Foundation`, `Ministerio`, `DRAC` etc.) ;
- alimente le même graphe `discovery/organismes-graph.yml` que (B).

**H. Pages "Lauréat·es éditions précédentes"** — `discovery_editions_archive.py`

Quand on tombe sur une URL de type `/laureats/2024` ou `/winners/2024` ou `/laureados/2024` :
- capture du **pattern d'URL** dans `discovery/url-patterns.yml` ;
- prédiction : `/laureats/2025`, `/laureats/2023`, etc. à tester ;
- alimentation rétroactive de l'archive avec les éditions passées.

**Intérêt double** : nourrit `archive.html` et permet de prédire où chercher l'édition à venir (couplé avec A).

### 12.4 Mécanismes expérimentaux retenus

**I. Crawl saisonnier** — paramètre `seasonal_intensity` dans `sources.yml`

Sur chaque source, un champ optionnel `peak_months: [9, 10, 11]`. Hors de ces mois, le `min_interval_days` est multiplié par 2. Pendant le pic, multiplié par 0.5. Économie de bande passante en creux estival.

**J. Track record d'un organisme**

Indicateur dérivé du graphe organismes (voir §13). Une opportunité dont l'organisme a un track record ≥ 3 éditions précédentes obtient un **bonus de scoring** (+1). Un organisme sans aucun historique repérable mais qui annonce une "première édition" obtient un **malus de fiabilité** (-1) → bascule en quarantaine manuelle.

**K. Détection conflits de typage inter-sources** — **résolu via fiche organisme (§13)**

Quand deux sources classent la même opportunité différemment (résidence vs. exposition), on ne tranche pas en aveugle. La **fiche organisme** §13 indique le type principal des opportunités habituelles de l'organisme. À défaut, on garde les deux types dans `types_secondaires[]` et on signale en quarantaine.

**L. Veille "nouveaux entrants"**

Métrique mensuelle issue de `discovery_blind_spots.py` : organismes apparaissant pour la première fois dans le graphe (B/G/H). Section dédiée du rapport mensuel : "Nouveaux organismes repérés ce mois".

### 12.5 Stratégie de promotion : **auto-promotion par Claude**

Arbitrage utilisateur : pas de review humaine systématique (qui crée le goulot BIBLIO). Règle :

1. Une URL candidate est promue automatiquement en source si **Claude Haiku** lui attribue :
   - `type` détecté avec `confidence ≥ 0.85` ;
   - `date_limite` extraite et **future** (sinon archive directe) ;
   - `discipline` compatible (plastique ou transdisciplinaire avec volet plastique) ;
   - **pas** d'anti-concept (loyer déguisé, NFT, fee abusif).
2. Si l'URL est sur un **domaine déjà connu et validé** → auto-promotion sans condition de confidence supplémentaire.
3. Si l'URL est sur un **nouveau domaine** → auto-promotion avec `_meta.confidence_status: "auto-new-domain"` (loggué pour audit).
4. Toute promotion est tracée dans `discovery/promote-log.jsonl` (un événement par ligne, auditable).
5. Une revue manuelle reste possible via `discovery/review.md` pour les cas litigieux, mais ce n'est plus le chemin par défaut.

Garde-fou : un cron quotidien `discovery_audit.py` rejoue les 20 dernières promotions et alerte si Claude reclassifie autrement (drift de modèle).

---

## 13. Fiche organisme — la brique de dédup et de cycle

Idée structurante issue de l'échange : **chaque organisme porteur a une fiche propre** qui rassemble un index des opportunités liées. Cette fiche organisme est ce qui permet la dédup inter-types (§11/K), la prédiction des cycles annuels (§12.3/A), le track record (§12.4/J), et la veille "nouveaux entrants" (§12.4/L).

### 13.1 Schéma `organismes/{slug}.yml`

```yaml
uid: "cnap-fr"
nom_canonique: "Centre national des arts plastiques (CNAP)"
acronymes: ["CNAP"]
pays: "France"
type_organisme: "institution_publique"   # institution_publique | fondation | centre_art | ecole | reseau | autre
url_canonique: "https://www.cnap.fr"
urls_secondaires:
  - "https://cnap.fr"

# ─── Profil de l'organisme ────────────────────────────────
description_courte: "Établissement public sous tutelle du Ministère de la Culture, soutient la création contemporaine en arts plastiques."
disciplines_proposees: ["installation", "sculpture", "photographie", "performance", "édition"]
types_opportunites_habituels: ["bourse", "prix", "residence"]

# ─── Index des opportunités liées (dédup inter-types) ─────
opportunites_liees:
  - { uid: "8a3f2c11", type: "prix",       nom: "Prix CNAP 2026" }
  - { uid: "b7d4e201", type: "bourse",     nom: "Soutien recherche 2026" }
  - { uid: "f1c9a3e8", type: "residence",  nom: "Résidence Saint-Cloud 2026" }

# ─── Track record et cycles ───────────────────────────────
track_record:
  prix:
    editions: ["2022", "2023", "2024", "2025", "2026"]
    fiabilite_cycle: 0.95
    fenetre_annuelle: "ouverture mars - clôture juin"
  bourse:
    editions: ["2024", "2025", "2026"]
    fiabilite_cycle: 0.9
    fenetre_annuelle: "ouverture continue"

# ─── Graphe partenariats ──────────────────────────────────
partenaires_mentionnes:
  - { organisme_uid: "drac-idf", occurrences: 5 }
  - { organisme_uid: "institut-francais", occurrences: 3 }

# ─── Veille ───────────────────────────────────────────────
pages_surveillees:
  - { url: "https://www.cnap.fr/appels", role: "agregateur_appels" }
  - { url: "https://www.cnap.fr/laureats", role: "archive_laureats" }
  - { url: "https://www.cnap.fr/rss", role: "rss" }

# ─── Méta ─────────────────────────────────────────────────
_meta:
  first_seen: "2026-05-20"
  last_updated: "2026-05-20"
  status: "actif"          # actif | dormant | obsolete
  nouveaux_entrants: false # true si organisme apparu < 90 jours
```

### 13.2 Trois usages directs

**Dédup inter-types** : quand deux fiches arrivent avec le même `organisme.uid`, on consulte la fiche organisme. Si le `nom` des opportunités est suffisamment proche (similarité ≥ 0.85), on tient compte du `types_opportunites_habituels` pour trancher le type. Sinon, on les garde toutes les deux dans `opportunites_liees[]`.

**Prédiction de cycle** : la `fenetre_annuelle` du `track_record` informe `discovery_cycles.py` : on sait quand activer la surveillance ciblée.

**Track record / scoring** : `len(track_record[type].editions) >= 3` → bonus de scoring +1 sur les nouvelles fiches du même organisme/type.

### 13.3 Création et mise à jour

- **Création** : à la première fiche détectée pour un organisme, on crée la fiche organisme avec les infos minimales extraites.
- **Mise à jour** : à chaque nouvelle fiche du même organisme, on enrichit (`opportunites_liees[]`, `partenaires_mentionnes[]`, `track_record`).
- **Enrichissement Claude mensuel** : `enrich_organismes.py` (cron mensuel) fait passer Claude sur les fiches organismes incomplètes pour deviner `description_courte`, `type_organisme`, `disciplines_proposees`.

### 13.4 Côté interface

L'interface publique gagne une page par organisme : `residence.actitude.org/organisme/{slug}/`. Cette page liste :
- les opportunités **ouvertes** de l'organisme ;
- les éditions **passées** archivées (utile pour préparer une candidature, comprendre les critères implicites du jury) ;
- un mini-historique factuel ("4 éditions du prix entre 2022 et 2026").

Pas de scoring affiché, pas de jugement éditorial — la fiche organisme reste un objet documentaire neutre.

---

## Sources

- [Lucile Leloup — Biographie](https://lucileloup.actitude.org/fr/biographie)
- [Lucile Leloup — Ensad Limoges](https://www.ensad-limoges.fr/diplomes/lucile-leloup/)
- BIBLIO — `biblio` (repo local, `README.md`, `config/concepts.yml`, `config/sources.yml`, `.github/workflows/watch.yml`, `DEPLOIEMENT.md`)

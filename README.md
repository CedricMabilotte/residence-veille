# Résidence — veille des opportunités arts plastiques

Veille automatisée des **résidences, bourses, prix et appels à exposition**
ouverts aux plasticien·nes dans le monde. Scrape multilingue (FR/EN/ES),
extraction structurée par Claude, calendrier des dates limites,
flux RSS par type, publication automatique sur **residence.actitude.org**.

Fork de [BIBLIO](https://github.com/CedricMabilotte/biblio-actitude-org)
(veille communs fonciers & paysanneries) appliqué à un autre domaine.

## Structure

```
config/
├── concepts.yml        ← ontologie 4 types + disciplines + scoring
└── sources.yml         ← URLs surveillées + parsers + intervalles

scripts/
├── watch.py            ← orchestration
├── detect_type.py      ← classifier (residence|bourse|prix|exposition)
├── extract_opportunity.py  ← Claude → fiche YAML structurée
├── resume_fr.py        ← traduction EN/ES → résumé FR
├── score_opportunity.py    ← scoring + bias profil interne
├── deadline_tracker.py ← tri ouvertes / bientôt / expirées
├── organisme_manager.py    ← fiches organismes (dédup, cycles, track record)
├── dedup.py            ← dédup inter-sources
├── parsers/            ← html_static, deep_html, rss, jsonld_event
└── discovery_*.py      ← 9 mécanismes de découverte (voir §12 de l'instruction)

appels/                 ← fiches YAML, une par type
├── residence/
├── bourse/
├── prix/
└── exposition/

organismes/             ← fiches organismes (CNAP, FRAC, fondations…)
archive/                ← opportunités expirées (consultables)
discovery/              ← candidats nouvelles sources
interface/              ← HTML généré (FR uniquement)
site/                   ← snapshot du site public à publier
```

## Démarrage rapide (à compléter une fois le bootstrap fini)

1. Lancer `bash bootstrap_copy.sh` pour copier les modules réutilisés depuis BIBLIO
2. Éditer `config/sources.yml` (sources de démarrage déjà incluses)
3. GitHub → Settings → Secrets → ajouter `CLAUDE_CODE_OAUTH_TOKEN`
4. GitHub → Actions → "Veille opportunités" → Run workflow

## Documentation

- **`INSTRUCTION-DEMARRAGE.md`** : cadrage complet (13 sections), décisions
  validées, schémas de données, mécanismes de découverte, fiche organisme.

## Sous-domaine cible

`residence.actitude.org` (en attente DNS + GitHub Pages).

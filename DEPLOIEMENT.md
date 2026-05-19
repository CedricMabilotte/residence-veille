# Déploiement de residence.actitude.org

Documentation parallèle de `Agent recup web github/DEPLOIEMENT-BIBLIO.md`, adaptée au fork.

## Repos

- **Repo privé** (code + veille) : `residence-veille` (à créer)
- **Repo public** (site Pages) : `residence-actitude-org` (à créer)
- **URL cible** : `https://residence.actitude.org` (en attente DNS)
- **URL temporaire** (active dès création GH Pages) : `https://cedricmabilotte.github.io/residence-actitude-org/`

## Étape DNS — registrar actitude.org

Ajouter un enregistrement CNAME :

| Type  | Nom        | Cible                          | TTL  |
|-------|------------|--------------------------------|------|
| CNAME | `residence`| `cedricmabilotte.github.io.`   | 3600 |

⚠ La cible n'est PAS `cedricmabilotte.github.io/residence-actitude-org` — c'est juste `cedricmabilotte.github.io.` (point final inclus si supporté par le registrar).

## Secrets GitHub à configurer (dans `residence-veille`)

| Secret                       | Rôle                                          |
|------------------------------|-----------------------------------------------|
| `CLAUDE_CODE_OAUTH_TOKEN`    | Auth Claude Code CLI (subscription)           |
| `RESIDENCE_PUBLISH_TOKEN`    | PAT GitHub avec scope `repo` pour pousser vers `residence-actitude-org` |

Webhooks (Discord/Slack/Mastodon) : à ajouter plus tard quand la newsletter sera activée.

## Pipeline de publication automatique

À chaque exécution du workflow "Veille opportunités" sur le repo privé :

```
residence-veille (privé)
   ↓ scripts/watch.py + deadline_tracker + discoveries
   ↓
appels/ + organismes/ + archive/ + interface/ + site/
   ↓ rsync vers
residence-actitude-org (public)
   ↓ GitHub Pages auto-deploy
   ↓
https://residence.actitude.org
```

## Initialisation des repos (à faire une fois)

```bash
# 1. Init local
cd "$HOME/Documents/Claude/Projects/Residences artistiques"
git init -b main
git add .
git commit -m "bootstrap: fork BIBLIO appliqué aux opportunités arts plastiques"

# 2. Créer repo privé sur GitHub via gh CLI
gh repo create CedricMabilotte/residence-veille --private --source=. --push

# 3. Créer repo public vide pour le site
gh repo create CedricMabilotte/residence-actitude-org --public

# 4. Configurer GitHub Pages sur le repo public
gh api -X POST /repos/CedricMabilotte/residence-actitude-org/pages \
  -f source[branch]=main -f source[path]=/
```

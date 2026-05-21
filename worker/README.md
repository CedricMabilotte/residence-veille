# Worker « Suggérer une source »

Petit relais Cloudflare Worker qui transforme une soumission du formulaire public
en **issue GitHub** taguée `nouvelle-source`, traitée ensuite automatiquement par
`scripts/review_issues.py`.

Le navigateur du visiteur ne voit jamais le token GitHub : il reste côté Worker,
dans une variable secrète. Aucun compte GitHub n'est requis du visiteur.

```
Formulaire (residence.actitude.org/suggerer.html)
   │  POST JSON {url, type, note}
   ▼
Cloudflare Worker  ──(API GitHub, token secret)──►  issue « nouvelle-source »
   ▼
review_issues.py (à chaque run de la veille) ──► discovery/candidates.yml
```

---

## Mise en place (≈ 15 min, une seule fois)

### 1. Créer le token GitHub (fine-grained PAT)

Sur <https://github.com/settings/tokens?type=beta> → **Generate new token**.

- **Resource owner** : CedricMabilotte
- **Repository access** : *Only select repositories* → `residence-veille`
- **Permissions** → *Repository permissions* → **Issues : Read and write**
- **Expiration** : 1 an (à renouveler ensuite)

Copier le token généré (`github_pat_…`). Il ne sera plus affiché ensuite.

### 2. Créer le Worker

Sur <https://dash.cloudflare.com> (créer un compte gratuit si besoin) :

1. **Workers & Pages** → **Create** → **Create Worker**.
2. Nom : `residence-suggest` → **Deploy** (déploie un Worker vide).
3. **Edit code** → coller intégralement le contenu de `suggest-worker.js` → **Deploy**.

### 3. Renseigner le token comme secret

Dans le Worker → **Settings** → **Variables and Secrets** → **Add** :

- Type : **Secret**
- Nom : `GITHUB_TOKEN`  *(exactement ce nom)*
- Valeur : le token de l'étape 1

→ **Deploy** pour appliquer.

### 4. Récupérer l'URL du Worker

Dans l'onglet du Worker, l'URL est de la forme :

```
https://residence-suggest.<votre-sous-domaine>.workers.dev
```

La reporter dans `scripts/generate_site.py`, ligne ~38 :

```python
WORKER_URL = "https://residence-suggest.xxx.workers.dev"
```

Tant que la valeur reste `VOTRE_URL_WORKER`, la page « Suggérer » affiche le
repli e-mail au lieu du formulaire actif.

### 5. Créer le label GitHub

L'API GitHub refuse une issue dont le label n'existe pas. Créer le label une fois :

<https://github.com/CedricMabilotte/residence-veille/labels> → **New label** :

- Nom : `nouvelle-source`  *(exactement ce nom)*

---

## Vérifications

- Le secret côté Worker s'appelle bien `GITHUB_TOKEN`.
- Le constante `REPO` en haut de `suggest-worker.js` correspond au repo de veille.
- `ALLOWED_ORIGIN` vaut `https://residence.actitude.org` (origine autorisée à
  poster — protège contre les soumissions depuis d'autres sites).
- Le token utilisé par le workflow pour `review_issues.py`
  (`secrets.RESIDENCE_PUBLISH_TOKEN`) doit aussi disposer du droit
  **Issues : Read and write** sur `residence-veille`, sinon le triage ne pourra
  ni lister ni commenter les issues.

## Test rapide

Une fois tout en place, soumettre une URL via la page « Suggérer ». Une issue
`Nouvelle source : …` doit apparaître sous le label `nouvelle-source`. Au prochain
run de la veille, `review_issues.py` la probe et commente le résultat.

## Coût

Plan gratuit Cloudflare Workers : 100 000 requêtes/jour — très largement suffisant.

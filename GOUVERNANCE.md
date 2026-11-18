## Instructions — Résidences artistiques

### Statut : projet standalone

Fork de biblio-actitude-org (biblio).
Autonome techniquement (GitHub Actions, Python, GitHub Pages).
Dépend de para uniquement pour le DNS du sous-domaine.

foyer_para   : — (standalone)
agent_porteur: @neo (déploiement DNS uniquement)
statut       : standalone

---

### Connexions à para

**DNS residence.actitude.org** — géré par @neo via Gandi.
Toute modification DNS : consulter resources/shared/acces-connecteurs.md
puis déposer dans agents/neo/inbox/.

**Profil cible : Lucile Leloup** — site lucileloup.fr maintenu par @neo.
Fiche mémoire : ~/.claude/projects/-home-ced-Documents-Ced-Cabinet-Activities-agents/memory/project_lucileloup.md

**Actitude.org** — ce projet est satellite d'actitude.org.
Si une décision éditoriale impacte la ligne d'actitude.org :
  → la poser dans projects/actitude/context/open-questions.md

---

### Credentials (via @neo)

Aucun secret dans ce repo. Credentials dans ~/.claude/credentials/.
Accès : suivre le protocole resources/shared/acces-connecteurs.md.

Secrets GitHub Actions du dépôt `residence-veille` (corrigé le 2026-11-18 ;
l'ancienne mention `ANTHROPIC_API_KEY` ne correspondait pas au workflow) :

- `CLAUDE_CODE_OAUTH_TOKEN` — auth Claude Code CLI sur la **souscription
  personnelle de Ced**. La veille partage donc sa limite hebdomadaire d'usage :
  c'est la raison de la cadence hebdomadaire (lundi 6h UTC) et du budget de
  60 min par run. Si la limite est atteinte, `claude_guard.py` passe le run en
  mode dégradé (aucune fiche promue) et le signale dans le rapport.
- `RESIDENCE_PUBLISH_TOKEN` — PAT GitHub (scope `repo`) pour pousser le site
  vers `residence-actitude-org`. Jamais renouvelé depuis mai 2026 : rotation à
  demander à @neo.

Cadence : hebdomadaire. Un run complet re-traite uniquement les items absents de
`discovery/seen_items.json` (index versionné) ; `discovery/throttle_state.json`
(versionné) espace les sources selon `min_interval_days`.

---

### Repos

Veille (privé) : github.com/CedricMabilotte/residence-veille
Site (public)  : github.com/CedricMabilotte/residence-actitude-org
Para           : github.com/CedricMabilotte/freechi-agents
Lucile         : github.com/CedricMabilotte/lucileloup-org

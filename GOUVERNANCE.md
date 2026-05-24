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

GitHub Actions Secret ANTHROPIC_API_KEY : demander rotation à @neo.

---

### Repos

Veille (privé) : github.com/CedricMabilotte/residence-veille
Site (public)  : github.com/CedricMabilotte/residence-actitude-org
Para           : github.com/CedricMabilotte/freechi-agents
Lucile         : github.com/CedricMabilotte/lucileloup-org

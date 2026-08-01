# Panne d'automatisation — diagnostic, correctifs, recommandations (2026-08-01)

## Constat

Le site n'avait pas été rafraîchi depuis le 22 mai 2026 (2,5 mois). Preuve
récoltée via l'API GitHub (`gh api repos/CedricMabilotte/residence-veille/actions/runs`) :
**les ~25 runs historiques du workflow « Veille opportunités » sont TOUS
`event: workflow_dispatch`, aucun `event: schedule`.**

## Cause racine

Le fichier `.github/workflows/watch.yml` ne déclarait, avant cette session,
**aucun déclencheur `schedule`** — uniquement `workflow_dispatch` (bouton
« Run workflow » cliqué à la main). Le pipeline n'a donc jamais tourné tout
seul : quelqu'un a lancé ~25 runs manuels entre le 19 et le 22 mai (phase de
mise au point), puis plus personne n'a cliqué le bouton. Ce n'est ni un bug
de script, ni un token expiré, ni un problème réseau — le déclencheur
attendu n'existait simplement pas. La documentation du projet (commentaire
dans `deadline_tracker.py` : « Exécution : cron quotidien dans le workflow
GH Actions ») décrivait une intention jamais implémentée.

## Facteurs aggravants identifiés (sans lien de causalité direct, mais qui
auraient prolongé la panne même une fois un cron ajouté)

1. **Aucune alerte d'échec.** Rien ne signale à Cédric qu'un run a échoué ou
   ne s'est pas déclenché. Le seul moyen de le savoir était de vérifier
   manuellement l'onglet Actions ou l'ancienneté du site — ce qui n'a pas été
   fait pendant 2,5 mois.
2. **Un échec de la « Veille principale » bloquait tout le reste.** L'étape
   `scripts/watch.py` n'avait pas de tolérance de panne : si elle échoue
   (token expiré, source down, quota Claude), toutes les étapes suivantes —
   y compris `deadline_tracker.py` et `generate_site.py`, qui ne dépendent
   pourtant pas du scraping — étaient sautées. Résultat : même le simple
   archivage des appels expirés (qui ne nécessite aucun appel réseau ni
   Claude) s'arrêtait avec le reste.
3. **Deux secrets configurés une seule fois, jamais vérifiés depuis** :
   `CLAUDE_CODE_OAUTH_TOKEN` et `RESIDENCE_PUBLISH_TOKEN`, tous deux datés du
   19 mai 2026 dans les paramètres du dépôt. Aucun moyen de vérifier leur
   date d'expiration depuis l'extérieur (GitHub ne l'affiche pas) — si
   `RESIDENCE_PUBLISH_TOKEN` est un PAT à expiration (30/60/90 jours), il
   pourrait déjà être proche de l'expiration ou l'avoir dépassée sans que
   personne ne le sache avant le prochain run.
4. **Incohérence de nommage dans la documentation.** `GOUVERNANCE.md`
   mentionne un secret `ANTHROPIC_API_KEY` à faire tourner par @neo, alors
   que le workflow utilise en réalité `CLAUDE_CODE_OAUTH_TOKEN`. Soit ce nom a
   changé sans mise à jour de la doc, soit c'est un doublon oublié — à
   clarifier pour ne pas rotationner le mauvais secret le jour où c'est
   nécessaire.
5. **`do_discovery_weekly` déclaré mais jamais utilisé.** L'input existe
   dans `workflow_dispatch` mais aucune étape ne le lit (seul
   `do_discovery_monthly` est branché). Ligne morte, sans impact fonctionnel,
   mais source de confusion pour quiconque relit le fichier.

## Correctifs appliqués cette session (dans `.github/workflows/watch.yml`)

1. **Ajout d'un déclencheur `schedule`** : cron quotidien à 6h UTC.
2. **Étape « Résoudre les paramètres »** ajoutée en tête de job : calcule les
   valeurs par défaut (seuil 6, pas de dry-run, discovery hebdo le lundi,
   mensuelle le 1er du mois) quand le run vient du cron, et reprend les
   valeurs saisies quand il vient d'un déclenchement manuel. Toutes les
   étapes suivantes lisent désormais `steps.params.outputs.*` au lieu de
   `github.event.inputs.*` (qui n'existe pas hors `workflow_dispatch`).
3. **`continue-on-error: true`** sur l'étape « Veille principale » : un échec
   du scraping n'empêche plus `deadline_tracker.py` / `generate_site.py` /
   commit / publication de tourner sur les données déjà connues.
4. **Notification d'échec** : nouvelle étape en fin de job qui ouvre (ou
   commente, pour éviter le spam) une issue GitHub si le job échoue ou si la
   veille principale échoue — en utilisant le `GITHUB_TOKEN` automatique,
   sans secret supplémentaire à gérer.

## Recommandations restant à trancher par Cédric

1. **Vérifier/renouveler `RESIDENCE_PUBLISH_TOKEN`** et si possible le
   configurer sans date d'expiration (ou avec un rappel calendrier), pour
   éviter une nouvelle panne silencieuse liée à un token expiré.
2. **Clarifier `GOUVERNANCE.md`** : le secret réellement utilisé est
   `CLAUDE_CODE_OAUTH_TOKEN`, pas `ANTHROPIC_API_KEY`. Corriger la doc ou
   ajouter le secret manquant si les deux sont réellement nécessaires
   ailleurs.
3. **Décider d'un canal d'alerte plus visible qu'une issue GitHub** si
   souhaité — Discord/Slack/mail (l'infra `webhooks.py` existe déjà mais est
   désactivée par choix éditorial, cf. §12.3/E de `INSTRUCTION-DEMARRAGE.md`
   sur la newsletter différée). L'issue GitHub est un filet minimal, pas une
   solution définitive.
4. **Vérifier après le premier run planifié** (dans les 24h) que le cron
   s'est bien déclenché — GitHub désactive automatiquement un workflow
   planifié après 60 jours d'inactivité du dépôt ; comme ce dépôt reçoit
   maintenant potentiellement ses propres commits quotidiens, ce risque
   devrait rester théorique, sauf si le job échoue en boucle avant même
   d'atteindre l'étape de commit.
5. **Nettoyer `do_discovery_weekly`** : soit le brancher sur une vraie étape
   hebdomadaire distincte de la discovery quotidienne Mastodon/network_pages,
   soit le retirer de la déclaration d'inputs pour ne pas laisser une option
   qui ne fait rien.

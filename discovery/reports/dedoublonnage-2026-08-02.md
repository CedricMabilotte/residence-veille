# Dédoublonnage — 2026-08-02

## Contexte

Premier run automatisé GH Actions réussi après le fix du cron (commit `f065033`,
2026-08-02 09:56) : 15 nouvelles opportunités qualifiées ajoutées, dont 11 pour
la Cité internationale des arts. Deux de ces fiches font doublon avec des fiches
créées manuellement la veille (2026-08-01), la même opportunité réelle ayant été
capturée via deux URLs légèrement différentes de la Cité (page `/en/` vs page FR).

## Doublons identifiés et résolus

1. **République dominicaine x Cité internationale des arts** —
   `c781ae19` (manuelle, confidence 0.8) vs `c16312c6` (bot, confidence 0.95).
   La fiche bot conserve `c16312c6` : pièces demandées détaillées (formats/pages
   précis), restitution documentée (compte rendu + open studios), niveau de
   carrière et nationalité explicités. `c781ae19` déplacée en quarantaine.

2. **Timor-Leste x Cité internationale des arts** —
   `fc738c65` (manuelle, confidence 0.8) vs `eb0a78fc` (bot, confidence 0.95).
   Même arbitrage : la fiche bot est retenue (restitution précisée, pièces
   demandées détaillées). `fc738c65` déplacée en quarantaine.

Les deux fiches manuelles ont été déplacées vers `discovery/quarantine/residence/`
(pas de suppression). La fiche organisme `cite-internationale-des-arts-...-054e95ce.yml`
a été corrigée : `opportunites_liees` ne référence plus que les uid du bot
(`c16312c6`, `eb0a78fc`), les deux uid manuels en ont été retirés.

## Point ouvert — pas corrigé ici

Une 3e fiche du même run, `appels/residence/225583d7.yml` (« Bridges »), est un
appel réel et ouvert mais réservé aux **critiques d'art membres AICA** — pas aux
artistes plasticien·nes praticien·nes, hors mission du site. Elle a passé le
filtre discipline de `scripts/score_opportunity.py::hard_filters()` uniquement
parce que ce filtre accepte toute discipline dont le libellé contient la
sous-chaîne `"art"` (cf. liste de mots-clés ligne ~80-82, qui inclut `"art"` tout
court). `"critique d'art"` matche trivialement. C'est un trou potentiel dans le
filtre discipline, à signaler pour une session ultérieure — **non corrigé ici** :
la fiche Bridges elle-même reste en l'état, ce n'est pas un faux positif au sens
du garde-fou anti-faux-positif (l'appel est réel et ouvert), juste une discipline
limite pour la mission du site.

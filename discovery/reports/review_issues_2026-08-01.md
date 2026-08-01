# Triage issues — 2026-08-01 (session manuelle Claude, hors GH Actions)

## Constat de départ

Dernier run automatisé : 2026-05-22. `deadline_tracker.py` relancé le 2026-08-01 :
85 fiches, seulement **1 « ouverte »**, 13 archivées comme expirées, **71 « indéterminée »**
(date limite absente). Sur ces 71, un examen manuel révèle que ce n'est pas seulement
un problème de date manquante : **32 fiches ne sont pas des appels à candidature du
tout**. Mises en quarantaine (`discovery/quarantine/`), pas supprimées.

## Quarantaine (32 fiches) — faux positifs de classification

### A. `citeinternationaledesarts.fr/programme-de-residence/*` — 25 fiches

Chaque page décrit un **partenariat institutionnel existant** (« Visarte Suisse x Cité
internationale des arts », « CALQ x Cité internationale des arts », etc.) : l'atelier est
alloué par l'institution partenaire qui nomme son résident, l'artiste ne candidate pas
directement à la Cité. C'est l'anti-concept explicite de `concepts.yml` : *« opportunité
sur invitation uniquement (pas d'open call) »* → devrait scorer 0, a été promu à 7-8.
Le crawl `deep_html` a traité l'annuaire des partenaires comme un annuaire d'appels.

Fiches : 0bcafeab, 1e42f10a, 1e993b36, 250c2109, 332456f4, 37ce57ed, 3d215270, 526c28e8,
56022bf8, 58c7b0db, 5bc54b72, 700f3dbf, 75d83cb5, 98392c7c, a5f1e203, bd896490, d1830d66,
d700f12b, ddb8fb07, e2d037ef, fdd214b6 (residence).

### B. `casadevelazquez.org/residents-et-alumni/*` — 2 fiches (6e7966fe, aa3e9d31, b21c7eb2, fb9a1992 → 4 en tout)

Pages biographiques d'anciens résident·es (alumni), pas des appels. Même logique que A :
navigation d'annuaire prise pour une liste d'opportunités.

### C. `rurart.org/exposition-*` — 4 fiches

Pages décrivant des **expositions déjà programmées ou passées** d'un artiste nommé
(ex. « Médecine Castor — Suzanne Husky », dates 12/03–14/06/2026, déjà close à la
date du contrôle). Ce sont des comptes-rendus, pas des appels à candidature pour une
exposition future. Fiches : 27167a71, 4894b873, 6c232e5c, 8e002b81.

### D. `salondemontrouge.com/actualit*` — 3 fiches

Pages d'actualité / interviews d'artistes sélectionné·es les années précédentes, pas
la page d'appel à candidature elle-même (qui existe mais n'a pas été identifiée par le
crawl). Fiches : 9badead2, b8f7cc68, cb46598a.

## Leçon (à reporter dans lecons-Residences-artistiques.md)

`detect_type.py` / `extract_opportunity.py` doivent vérifier le **signal minimal
« candidature ouverte »** (verbe à l'impératif adressé au candidat, présence d'un
formulaire ou d'une adresse de dépôt, date limite ou fenêtre de dépôt) avant de
promouvoir — pas seulement la présence de mots-clés du domaine (résidence, exposition).
Une page qui *raconte* une résidence/exposition passée n'est pas une page qui *ouvre*
une candidature. Contrôle proposé : rejeter si la page ne contient aucun verbe
d'action à la 2e personne du type « candidatez », « déposez », « soumettez », « apply »,
« postule » et aucune date dans le futur.

## Nouvelles fiches ajoutées cette session

Voir `reports/run_2026-08-01_manuel.json` pour le détail (recherche manuelle Claude,
sources prioritaires §4 de INSTRUCTION-DEMARRAGE.md).

# Feuille de route

Objectif : un logiciel unique, utilisable par tous et d'abord par les linguistes
qui documentent des langues, qui réunit la majorité des fonctions de FLEx, de
WeSay, de PrimerPrep et de Bloom, lit les ressources Paratext, et produit
dictionnaires imprimés et applications Android. Principe constant : des règles
explicites déclarées par le linguiste, des propositions automatiques toujours
justifiées et jamais appliquées sans décision humaine.

## Phase 0 — Fondations ✅ (version 0.2)

- [x] Paquet Python découpé en modules (texte, base, projet, lexique, alignement, USFM, exports, interface)
- [x] Projets multi-langues : un projet = une langue = un fichier `.lexique`, réglages dans le fichier
- [x] Schéma SQLite versionné, migrations transactionnelles, copie de sécurité avant mise à jour
- [x] Conversion des bases v0.1 sans perte (relations non reliées conservées en note)
- [x] Modèle de lexique entrée → sens → exemples, propriétés libres, relations
- [x] Découpage en mots à règles déclarées (caractères de mot, longueur minimale, mots vides)
- [x] Propositions justifiées par les phrases sources ; contradictions à résoudre
- [x] Interface PySide6 (Qt) : tableau de bord, lexique, validation, corpus, exports, réglages
- [x] Sauvegardes automatiques ; tests automatiques (cœur et interface)

## Phase 1 — Lexique complet (inspiré de FLEx) — prochaine étape

- [ ] Domaines sémantiques officiels SIL (liste DDP4, environ 1 800 domaines, recherche arborescente)
- [ ] Formes : forme de citation, variantes, allomorphes, formes complexes et composants
- [ ] Catégories hiérarchiques et traits grammaticaux propres à la langue (classes nominales, tons…)
- [ ] Index inverse (langue d'analyse → langue documentée)
- [ ] Prononciation (API), enregistrements audio et images liés aux entrées
- [ ] Homographes numérotés, statut de l'entrée, édition en masse, filtres
- [ ] Import LIFT complet (reprendre un lexique FLEx ou WeSay)
- [ ] Systèmes d'écriture : polices, claviers, ordre de tri propre à la langue

## Phase 2 — Textes et analyse (inspiré de FLEx)

- [ ] Inventaire des formes de mots avec fréquences
- [ ] Concordance (mot dans son contexte)
- [ ] Interlinéaire : segmentation, glose mot à mot et morphème par morphème
- [ ] Analyseur morphologique à règles déclarées (affixes, clitiques) relié au lexique

## Phase 3 — Paratext

- [ ] Lecture d'un dossier de projet Paratext (Settings.xml, livres SFM, noms des livres)
- [ ] Lexique et glossaire interlinéaire de Paratext
- [ ] Rendus des termes bibliques
- [ ] Lecture seule : le projet Paratext n'est jamais modifié

## Phase 4 — Syllabaires (inspiré de PrimerPrep)

- [ ] Inventaire des graphèmes (multigraphes déclarés : ng, ŋg, nj…) et des tons
- [ ] Fréquences dans le corpus
- [ ] Ordre d'enseignement proposé et justifié, modifiable
- [ ] Mots et phrases utilisables à chaque leçon ; export

## Phase 5 — Publication

- [ ] Dictionnaire imprimé : PDF et Word sur deux colonnes, mots-guides, index inverse
- [ ] Application Android : données et configuration pour Dictionary App Builder (SIL)
- [ ] Listes de mots et livrets pour Bloom
- [ ] Export Webonary

## Phase 6 — Collecte communautaire (inspiré de WeSay)

- [ ] Mode simplifié pour les locuteurs
- [ ] Collecte guidée par domaine sémantique
- [ ] Enregistrement audio direct
- [ ] Échange de données entre plusieurs postes

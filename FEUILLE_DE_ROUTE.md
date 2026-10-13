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

## Phase 1 — Lexique complet (inspiré de FLEx) ✅ (version 0.3)

- [x] Domaines sémantiques officiels SIL (1 792 domaines, français et anglais, questions d'élicitation),
      copiés depuis l'installation de FLEx ou un fichier SemDom.xml / LocalizedLists ; page Domaines
- [x] Forme de citation, prononciation (API), type morphologique (noms FLEx), statut de l'entrée
- [x] Variantes (libre, dialectale, orthographique, irrégulière) et allomorphes avec environnement
- [x] Formes complexes (composé, dérivé, redoublement, expression…) et leurs composants
- [x] Catégories hiérarchiques propres à la langue ; propriétés libres (ton, classe nominale…)
- [x] Index inverse (langue d'analyse → langue documentée) ; page Index inverse
- [x] Enregistrements audio et images liés aux entrées (écoute intégrée)
- [x] Homographes numérotés, filtres (statut, catégorie, domaine), modification en masse
- [x] Import LIFT (FLEx, WeSay) : mise à jour par identifiant, rapport détaillé, rien n'est perdu
- [x] Export LIFT enrichi (citation, prononciation, variantes, composants, domaines, index inverse)
- [x] Ordre alphabétique déclaré (multigraphes, tons au niveau secondaire) et police de la langue
- [ ] Traits grammaticaux structurés (système de traits déclaré, au lieu de propriétés libres)
- [ ] Claviers (intégration Keyman)

## Phase 2 — Textes et analyse (inspiré de FLEx) — prochaine étape

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

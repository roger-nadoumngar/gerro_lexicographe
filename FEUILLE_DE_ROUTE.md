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
- [x] Import direct des projets FLEx de l'ordinateur (.fwdata, lecture seule) : lexique complet, textes
      et analyses interlinéaires ; testé sur trois projets réels (jusqu'à 8 580 entrées)
- [x] Export LIFT enrichi (citation, prononciation, variantes, composants, domaines, index inverse)
- [x] Ordre alphabétique déclaré (multigraphes, tons au niveau secondaire) et police de la langue
- [ ] Traits grammaticaux structurés (système de traits déclaré, au lieu de propriétés libres)
- [ ] Claviers (intégration Keyman)

## Phase 2 — Textes et analyse (inspiré de FLEx) ✅ (version 0.4)

- [x] Textes de terrain importés (.txt ou saisie), découpés en phrases selon des règles explicites,
      traduction alignée phrase à phrase (refusée si le nombre de phrases diffère) ; métadonnées
      (titre, genre, locuteur, lieu, date) ; traduction littérale et notes par phrase
- [x] Inventaire des formes de mots : fréquences, statut d'analyse, présence au lexique, couverture du corpus
- [x] Concordance : forme exacte, morphème, suite de caractères, expression régulière ; dans la langue
      ou dans la traduction
- [x] Analyseur morphologique à règles : préfixes, suffixes, clitiques et allomorphes déclarés dans le
      lexique ; toutes les découpes proposées, les plus simples d'abord, jamais choisies à la place du linguiste
- [x] Interlinéaire : mot, morphèmes, gloses, catégories, glose du mot ; analyses validées par forme,
      choix par occurrence pour les mots ambigus ; découpe manuelle reliée au lexique
- [ ] Conditions d'environnement des allomorphes appliquées par l'analyseur (affichées pour l'instant)
- [ ] Infixes, circonfixes, redoublement
- [ ] Export de l'interlinéaire (texte, Word, XLingPaper / FLExText)

## Phase 3 — Paratext ✅ (version 0.5)

- [x] Détection des projets Paratext de l'ordinateur (langue, nom, versification, livres présents)
- [x] Livres USFM importés verset par verset, dans la langue documentée ou dans la traduction :
      deux projets donnent un corpus parallèle (avertissement si les versifications diffèrent,
      signalement des livres sans texte)
- [x] Glossaire interlinéaire de Paratext (Lexicon.xml) : mots et morphèmes glosés ajoutés au lexique
      sans doublons
- [x] Rendus validés des termes bibliques (pas les rendus devinés), avec glose française de Paratext
      quand elle existe, catégorie et note du terme d'origine
- [x] Lecture seule : les projets Paratext ne sont jamais modifiés (vérifié par empreinte des fichiers)
- [ ] Analyses du glossaire interlinéaire de Paratext reprises comme analyses de mots dans les textes

## Phase 4 — Syllabaires (inspiré de PrimerPrep) — prochaine étape

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

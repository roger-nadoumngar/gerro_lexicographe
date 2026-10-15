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

## Phase 4 — Syllabaires (inspiré de PrimerPrep) ✅ (version 0.6)

- [x] Découpage en graphèmes selon l'alphabet déclaré (multigraphes, correspondance la plus longue) ;
      tons enseignés à part ou avec leur lettre ; caractères non déclarés signalés
- [x] Fréquences des graphèmes (occurrences, nombre de mots, exemples) ; noms propres écartés
      (majuscule dans au moins 80 % des occurrences) ; suites de lettres fréquentes proposées comme
      candidats multigraphes, au jugement du linguiste
- [x] Ordre d'enseignement proposé et justifié : à chaque leçon, le graphème qui rend lisibles le plus de
      nouveaux mots (à égalité, le plus fréquent) ; réordonnable et enregistré dans le projet
- [x] Leçons : nouveaux mots lisibles (avec glose du lexique), phrases du corpus lisibles, part du corpus
      couverte ; export texte et CSV
- [ ] Mise en page de livret (Bloom, Word) — phase 5

## Phase 5 — Publication ✅ (version 0.7)

- [x] Dictionnaire imprimé en PDF (mise en page par le logiciel) : page de titre, deux colonnes, en-têtes
      de lettre selon l'alphabet déclaré, mots-guides, numéros de page, index inverse ; A4 ou A5 ;
      statuts publiés au choix (par défaut : validé et à vérifier)
- [x] Dictionnaire en Word (.docx) : deux colonnes, mots-guides calculés par Word, styles modifiables
- [x] Application Android : dossier prêt pour Dictionary App Builder (LIFT avec sons et images, mode d'emploi)
- [x] Livret de syllabaire en PDF (une leçon par page) ; fichiers pour l'outil « Decodable Reader » de Bloom
- [ ] Export Webonary (dictionnaire en ligne)
- [ ] Projet Dictionary App Builder complet (sans passer par l'assistant de DAB)

## Phase 6 — Collecte communautaire (inspiré de WeSay) ✅ (version 1.0)

- [x] Collecte guidée par domaine sémantique : une question d'élicitation à la fois (7 945 questions avec
      la liste de FLEx), mots donnés enregistrés comme brouillons classés dans le domaine, sans doublon
      (majuscules ignorées), reprise là où la collecte s'est arrêtée
- [x] Tâches de complément, une entrée à la fois : sens manquant, exemple manquant, domaine manquant,
      prononciation manquante ; seul le champ de la tâche est modifié
- [x] Enregistrement audio direct avec le micro de l'ordinateur (WAV), lié à l'entrée, écoute immédiate
- [x] Mode locuteur : plein écran, gros caractères, sans les menus du logiciel
- [x] Fusion du travail d'un autre poste : entrées reconnues par identifiant, nouvelles ajoutées (avec sons
      et images), la version modifiée le plus récemment l'emporte, phrases et textes ajoutés ; l'autre fichier
      n'est jamais modifié ; rapport détaillé

## Version 1.1 ✅

- [x] Environnements d'allomorphes appliqués par l'analyseur (écriture « / N _ », « / _ # »…, classes de
      sons déclarées dans les réglages) ; un environnement en texte libre est affiché mais jamais appliqué
- [x] Export de l'interlinéaire d'un texte : texte aligné et Word
- [x] Traits grammaticaux déclarés (classe nominale, ton…) avec valeurs permises : listes de choix dans la
      fiche, valeur non déclarée refusée ; les propriétés non déclarées restent libres

## Version 1.2 ✅

- [x] Apostrophe dans les mots (dee'g) ; alphabet ngambay ; aperçu avant impression des PDF (feuilles A4/A5)
- [x] Bible complète en une fois (dossier ou .zip, USFM ou USX, par exemple un paquet DBL) ; marqueurs de
      mots USFM retirés sans laisser d'espace (« d’Uts »)
- [x] Import d'un dictionnaire imprimé (Word ou texte, présentation du Projet Sara-Baguirmi) : articles,
      sens, exemples séparés de leur traduction par des règles d'orthographe du français, expressions,
      prononciations, synonymes ; fusion qui complète et répare sans rien supprimer ; simulation avant ;
      réimport sans effet
- [x] Collecte à partir d'une liste de mots (Word ou texte, groupes), comme la liste de mots de WeSay
- [x] Liste des domaines sémantiques de SIL livrée en français et en anglais (CC BY-SA 4.0)
- [x] Logiciel livré sans données d'une langue documentée (le corpus ngambay ne sert qu'aux tests)

## Version 1.3 ✅

- [x] Cartes des pages Imports, Exports et Collecte dans une zone qui défile (titres plus jamais coupés)
- [x] Clavier Keyman calculé d'après l'alphabet et le lexique du projet (lettre + ;, tons avec =),
      AZERTY ou QWERTY, compilé en paquet installable si Keyman Developer est présent, aide imprimable
- [x] Contrôle des lettres d'un autre alphabet (у cyrillique pour y…) sur le tableau de bord, correction
      à la demande selon une table de sosies, avec sauvegarde avant
- [x] Application Android construite depuis le logiciel avec Dictionary App Builder (installé) : projet DAB
      créé par DAB lui-même, relié au LIFT, photos déclarées, icône et « À propos », signature avec le
      keystore de l'utilisateur (mots de passe masqués) ; essai réel : APK ngambay de 12,6 Mo en 1 minute
- [x] Analyseur : redoublement (base + copie « RED », tons de la copie libres), infixes déclarés (jamais en
      bordure, environnement respecté, affichage k‹ar›tab) ; jamais de coupure entre une lettre et ses accents
- [x] Réglage « le corpus n'écrit pas toujours les tons » : pour un mot sans analyse exacte, comparaison sans
      les signes combinants ; propositions marquées « tons différents », jamais évidentes (ngambay : mots
      inconnus du corpus de 49 % à 24 %)
- [x] Analyses de l'interlinéaire de Paratext reprises comme analyses validées (positions à une seule
      analyse, sens du glossaire, mot présent dans le verset ; choix par verset pour les mots à plusieurs
      analyses) ; Paratext seulement lu
- [x] Site web du dictionnaire (dossier autonome : index.html, données, photos) : recherche dans les deux
      langues avec ou sans tons, lettres de l'alphabet du projet, lien direct vers chaque mot, adapté au
      téléphone ; mêmes entrées que le dictionnaire imprimé
- [x] Doublons du lexique (Lexique > Doublons…) : même forme, même type, au moins une glose commune ;
      fusion sans perte (sens, exemples, photos, relations, composants, analyses), statut le plus avancé
      gardé, sauvegarde avant ; ngambay : 211 groupes, 280 entrées en trop

## Version 1.4 ✅

- [x] Nettoyage des données ngambay (sosies, doublons, interlinéaire Paratext) ; le glossaire Paratext
      retrouve une entrée « radical » ou écrite avec une majuscule (plus de doublons recréés)
- [x] Interface en anglais : textes relevés dans le code, traduction exacte / par gabarit / ligne par
      ligne, valeurs d'origine gardées dans les listes ; test de complétude des traductions
- [x] Guide d'utilisation en français et en anglais (Aide > Guide d'utilisation, F1)
- [x] Essai complet sur une autre langue (kenga, Paratext KYQbible) : import, interlinéaire (66 % du
      corpus analysé), syllabaire, clavier (saltillo ajouté), PDF, Word, site, LIFT, DAB
- [x] Programme d'installation (Inno Setup) : utilisateur ou tous, raccourcis, icône, désinstallation
      qui ne touche pas aux projets

## Version 1.5 (en cours)

- [x] Analyseur : circonfixes déclarés (« ka- -ŋ » entourant un radical déclaré) et redoublement partiel
      (copie consonne(s) + voyelle(s) du début du radical, seulement si la classe V est déclarée)

## Points restants

- Redoublement partiel en fin de mot (copie de la dernière syllabe)
- Webonary : passe par FLEx (export LIFT → FLEx → « Upload to Webonary ») ; sons dans l'application Android

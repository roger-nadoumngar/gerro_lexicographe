# Gerro Lexicographe

Logiciel de lexicographie et de documentation des langues, pensé pour les
linguistes qui travaillent sur des langues peu documentées. Il réunit à terme
dans un seul outil les fonctions de FLEx (lexique et analyse), WeSay (collecte
avec la communauté), PrimerPrep (syllabaires) et Bloom (livres), lit les
projets Paratext, et produit dictionnaires imprimés et applications Android.

Projet pilote : le **ngambay** (Tchad, code ISO 639-3 `sba`), avec le français
comme langue d'analyse.

## Principe : des règles explicites, pas de devinettes

- **Le linguiste déclare les règles** de sa langue (caractères qui font partie
  des mots, catégories grammaticales…) ; le logiciel les applique.
- **Les propositions automatiques sont justifiées.** Le moteur d'alignement
  propose une traduction pour chaque mot à partir de phrases parallèles
  (coefficient de Dice, formule affichée), et montre les phrases sur
  lesquelles repose chaque proposition. Rien n'entre dans le lexique sans
  décision humaine.
- **Aucune perte de données** : les fichiers importés ne sont jamais modifiés,
  chaque projet est sauvegardé automatiquement, et une base qui doit être mise
  à jour est copiée avant la mise à jour.

## Installation

Python 3.10 ou plus récent.

```bash
git clone https://github.com/roger-nadoumngar/gerro_lexicographe
cd gerro_lexicographe
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Sous macOS ou Linux, l'activation de l'environnement est `source .venv/bin/activate`.

## Utilisation

Au premier lancement, choisis ou crée un **projet** : un projet documente une
langue et tient dans un seul fichier `.lexique`. Une base de la version 0.1
(`lexique_ngambay.db`) est détectée et convertie automatiquement en projet,
sans modifier l'original.

| Page | Rôle |
|---|---|
| Tableau de bord | Chiffres du projet, contradictions détectées (garder ou adopter) |
| Lexique | Entrées complètes (forme de citation, prononciation, type morphologique, statut, variantes et allomorphes, formes complexes, sens, médias, relations) ; filtres, modification en masse, import LIFT |
| Domaines | Domaines sémantiques officiels de SIL, questions d'élicitation, mots classés |
| Index inverse | Partie langue d'analyse → langue documentée du dictionnaire |
| Validation | Propositions du moteur, avec les phrases qui les justifient |
| Corpus | Phrases parallèles ; import USFM / SFM, lecture Word / PDF, enregistrements audio |
| Exports | LIFT (FLEx, WeSay, Dictionary App Builder), JSON, CSV, texte |

**Réglages du projet** (menu Fichier) : langues et codes ISO, règles de
découpage en mots, mots vides de la langue d'analyse, seuil des
contradictions, alphabet (ordre de tri) et police de la langue, catégories
grammaticales hiérarchiques.

**Domaines sémantiques** : la liste officielle de SIL est copiée dans le
projet depuis l'installation de FLEx (fichiers `LocalizedLists-fr.zip` ou
`SemDom.xml`), ou depuis un de ces fichiers choisi dans la page Domaines.
Elle n'est pas distribuée avec le logiciel.

## Données

- Projets : `%LOCALAPPDATA%\GerroLexicographe\Projets\` (Windows),
  `~/Library/Application Support/GerroLexicographe/Projets/` (macOS),
  `~/.local/share/GerroLexicographe/Projets/` (Linux).
- Sauvegardes automatiques (10 dernières par projet) : dossier `Sauvegardes`
  à côté, accessible par le menu Fichier.
- Les enregistrements audio d'un projet sont copiés dans le dossier
  `<projet>_medias` à côté du fichier `.lexique`.

## Corpus d'exemple

Ruth et Job en ngambay et en français (Louis Segond 1910, domaine public,
fichiers USFM fraLSG d'[eBible.org](https://ebible.org/find/details.php?id=fraLSG)).
1 146 références communes ; neuf références ngambay sans équivalent dans la
source française consultée (JOB 34:37, 38:39–41, 40:29–32, 41:26) restent à
vérifier — aucun texte n'a été deviné. Le texte ngambay est normalisé en
Unicode NFC : la source mélangeait lettres précomposées et décomposées.

## Développement

```
app.py                      lanceur (python app.py)
lexicographe/
  texte.py                  normalisation Unicode, découpage en mots à règles
  base.py                   schéma SQLite versionné, migrations, conversion v0.1
  projet.py                 projets (.lexique), réglages, sauvegardes
  lexique.py                entrées, sens, variantes, composants, relations, catégories, index inverse
  domaines.py               domaines sémantiques (lecture des listes FLEx)
  lift_import.py            import LIFT (FLEx, WeSay)
  alignement.py             propositions de traduction, preuves, contradictions
  usfm.py                   lecture USFM / SFM, ordre canonique des livres
  corpus.py                 corpus d'exemple intégré
  exports.py                LIFT, JSON, CSV, texte
  ressources/corpus/        Ruth et Job (ngambay, français)
  ui/                       interface PySide6 (Qt)
tests/                      tests automatiques (pytest)
```

```bash
pip install pytest
python -m pytest tests
```

La feuille de route complète est dans [FEUILLE_DE_ROUTE.md](FEUILLE_DE_ROUTE.md).

## À propos

Projet développé dans le cadre d'une initiative liée à SIL International.

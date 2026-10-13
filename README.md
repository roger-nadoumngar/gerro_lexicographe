# Lexicographe Ngambay

Outil de lexicographie assisté par IA pour le ngambay (Tchad), avec le
français comme langue pivot grammatical. Projet pilote pour une future
plateforme de lexicographie destinée aux langues sous-documentées,
combinant les fonctions de FLEx, WeSay et Bloom (SIL International)
dans un seul logiciel moderne.

## Fonctionnement

Le corpus permet au moteur de proposer des hypothèses à partir des versets présents dans les deux fichiers. Les textes sources JSON ne sont pas modifiés par le logiciel.

### Couverture des références

Le contrôle des clés JSON relève 1 155 références ngambay (RUT : 85, JOB : 1 070) et 1 146 références françaises (RUT : 85, JOB : 1 061). Les 1 146 références françaises correspondent à des références présentes dans le fichier ngambay. Huit versets présents dans le fichier source français mais absents du corpus ngambay ne sont pas importés.

Lors de l'initialisation d'une base vide, les 1 146 références communes sont chargées dans la base et utilisées par le moteur. Neuf références ngambay n'ont pas de marqueur de verset correspondant dans la source USFM consultée : JOB 34:37, JOB 38:39–41, JOB 40:29–32 et JOB 41:26. Leur équivalence de versification reste à vérifier ; aucun texte n'a été deviné pour ces clés. Les nombres décrivent les références, pas l'exactitude linguistique des textes.

Les versets français ajoutés proviennent de la Louis Segond 1910, fichiers USFM fraLSG publiés par [eBible.org](https://ebible.org/find/details.php?id=fraLSG) ([archive USFM](https://ebible.org/Scriptures/fraLSG_usfm.zip)). La fiche source déclare cette édition dans le domaine public.

Le moteur apprend en continu : chaque nouvelle phrase ajoutée (onglet
"Concordance active") renforce ou contredit les hypothèses existantes.

Les textes sont normalisés en Unicode NFC avant l'analyse : le corpus
ngambay mélange lettres accentuées précomposées et décomposées, et sans
normalisation un même mot serait compté comme deux mots différents.

À chaque démarrage, les versets du corpus intégré absents d'une base
existante y sont ajoutés. Les versets importés (USFM) ou saisis à la main
ne sont jamais réécrits.

## Installation

Nécessite Python 3.10 ou plus récent (avec Tkinter, inclus par défaut
sur la plupart des installations Python Windows/Mac).

```bash
git clone https://github.com/roger-nadoumngar/gerro_lexicographe
cd gerro_lexicographe
python app.py
```

Bibliothèques optionnelles : `pip install pylexique` (suggestion
grammaticale), `python-docx` (import Word), `pypdf` (import PDF).

## Structure du projet

```
app.py                 # Logiciel complet (moteur + interface)
ngambay_verses.json     # Corpus ngambay (Ruth + Job), extrait de fichiers USFM
french_verses.json      # Références françaises du corpus (Segond 1910)
INSTRUCTIONS_EXE.txt    # Comment générer un .exe Windows avec PyInstaller
```

## Feuille de route

- [x] Extraction du corpus USFM (Ruth, Job)
- [x] Alignement automatique ngambay-français
- [x] Interface de validation humaine
- [x] Concordance active (apprentissage incrémental)
- [x] Fiche complète : exemple de phrase, définition, notes, relations lexicales
- [ ] Vérification de la couverture bilingue (références manquantes de Job et Ruth)
- [x] Résolution des contradictions (garder ou adopter la nouvelle traduction)
- [x] Export LIFT 0.13 (import dans FLEx / WeSay ; langue `sba`, glose en `fr`)
- [ ] Export Bloom, USFM
- [ ] Reconnaissance vocale ngambay (phase ultérieure)

## Licence des données sources

Le texte français utilisé comme pivot (Louis Segond 1910) est dans le
domaine public.

## À propos

Projet développé dans le cadre d'une initiative liée à SIL International.

## Stockage persistant des données

La base `lexique_ngambay.db` et les fichiers audio sont conservés dans un dossier utilisateur accessible, même si l'application est installée dans un dossier protégé :

- Windows : `%LOCALAPPDATA%\LexicographeNgambay\`
- macOS : `~/Library/Application Support/LexicographeNgambay/`
- Linux : `$XDG_DATA_HOME/LexicographeNgambay/` ou `~/.local/share/LexicographeNgambay/`

Au premier lancement, si aucune base n'existe déjà dans ce dossier, une ancienne base située à côté du logiciel y est copiée. La base d'origine est conservée. Les fichiers JSON sont lus à côté du script en développement et depuis le bundle PyInstaller en modes `--onefile` et `--onedir`.

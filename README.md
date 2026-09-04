# Lexicographe Ngambay

Outil de lexicographie assisté par IA pour le ngambay (Tchad), avec le
français comme langue pivot grammatical. Projet pilote pour une future
plateforme de lexicographie destinée aux langues sous-documentées,
combinant les fonctions de FLEx, WeSay et Bloom (SIL International)
dans un seul logiciel moderne.

## Fonctionnement

Le logiciel s'appuie sur un corpus bilingue (actuellement : Ruth et Job,
en ngambay et en français, alignés verset par verset) pour proposer
automatiquement des hypothèses de traduction mot à mot, via un moteur
de concordance statistique (coefficient de Dice). Chaque hypothèse est
ensuite validée ou corrigée par un locuteur natif.

Le moteur apprend en continu : chaque nouvelle phrase ajoutée (onglet
"Concordance active") renforce ou contredit les hypothèses existantes.

## Installation

Nécessite Python 3.10 ou plus récent (avec Tkinter, inclus par défaut
sur la plupart des installations Python Windows/Mac).

```bash
git clone <url-de-ce-depot>
cd ngambay-lexicographe
python app.py
```

## Structure du projet

```
app.py                 # Logiciel complet (moteur + interface)
ngambay_verses.json     # Corpus ngambay (Ruth + Job), extrait de fichiers USFM
french_verses.json      # Corpus français correspondant (Segond 1910, domaine public)
INSTRUCTIONS_EXE.txt    # Comment générer un .exe Windows avec PyInstaller
```

## Feuille de route

- [x] Extraction du corpus USFM (Ruth, Job)
- [x] Alignement automatique ngambay-français
- [x] Interface de validation humaine
- [x] Concordance active (apprentissage incrémental)
- [ ] Élargissement du corpus (reste de Job, autres livres)
- [ ] Export LIFT, Bloom, USFM
- [ ] Reconnaissance vocale ngambay (phase ultérieure)

## Licence des données sources

Le texte français utilisé comme pivot (Louis Segond 1910) est dans le
domaine public.

## À propos

Projet développé dans le cadre d'une initiative liée à SIL International.

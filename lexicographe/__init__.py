"""
Gerro Lexicographe — logiciel de lexicographie et de documentation des langues.

Organisation du paquet :
    texte        normalisation Unicode et découpage en mots selon des règles déclarées
    base         schéma SQLite versionné et migrations
    projet       un projet = une langue documentée = un fichier .lexique
    lexique      entrées, sens, variantes, composants, relations, catégories, index inverse
    domaines     domaines sémantiques officiels de SIL (liste français–anglais livrée)
    lift_import  import LIFT (FLEx, WeSay)
    dico_imprime import d'un dictionnaire imprimé (Word ou texte, règles déclarées)
    flex_import  import direct d'un projet FLEx (.fwdata), en lecture seule
    paratext     lecture des projets Paratext (livres, glossaire, termes bibliques)
    syllabaire   graphèmes, ordre d'enseignement et leçons (inspiré de PrimerPrep)
    publication  dictionnaire PDF / Word, livret, Bloom, Dictionary App Builder
    collecte     collecte par domaine, par liste de mots, tâches de complément (inspiré de WeSay)
    fusion       fusion du travail d'un autre poste
    traits       traits grammaticaux déclarés
    textes       textes du corpus et leurs métadonnées
    morphologie  analyseur morphologique à règles déclarées
    interlineaire analyses, interlinéaire, inventaire des formes, concordance
    alignement   hypothèses de traduction à partir de phrases parallèles
    usfm         lecture des fichiers USFM / SFM
    corpus       corpus d'exemple pour les tests (Ruth et Job, ngambay–français ; non livré)
    exports      JSON, CSV, texte, LIFT
    ui           interface graphique (PySide6 / Qt)
"""

APP_NAME = "Gerro Lexicographe"
APP_ID = "GerroLexicographe"
__version__ = "1.7.0"

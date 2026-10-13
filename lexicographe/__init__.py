"""
Gerro Lexicographe — logiciel de lexicographie et de documentation des langues.

Organisation du paquet :
    texte        normalisation Unicode et découpage en mots selon des règles déclarées
    base         schéma SQLite versionné et migrations
    projet       un projet = une langue documentée = un fichier .lexique
    lexique      entrées, sens, exemples, relations, catégories
    alignement   hypothèses de traduction à partir de phrases parallèles
    usfm         lecture des fichiers USFM / SFM
    corpus       corpus d'exemple intégré (Ruth et Job, ngambay–français)
    exports      JSON, CSV, texte, LIFT
    ui           interface graphique (PySide6 / Qt)
"""

APP_NAME = "Gerro Lexicographe"
APP_ID = "GerroLexicographe"
__version__ = "0.2.0"

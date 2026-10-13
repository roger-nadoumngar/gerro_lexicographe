"""Emplacements des ressources intégrées et des données de l'utilisateur."""

import os
import sys

from . import APP_ID

# Dossier de données de la version 0.1 (fichier unique app.py, ngambay seulement)
ANCIEN_APP_ID = "LexicographeNgambay"


def _base_ressources():
    bundle = getattr(sys, "_MEIPASS", None)  # PyInstaller --onefile / --onedir
    if bundle:
        return os.path.join(bundle, "lexicographe", "ressources")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "ressources")


def ressource(*parties):
    """Chemin d'une ressource intégrée au logiciel ; erreur explicite si elle manque."""
    chemin = os.path.join(_base_ressources(), *parties)
    if not os.path.isfile(chemin):
        raise FileNotFoundError(f"Ressource nécessaire introuvable : {chemin}")
    return chemin


def dossier_donnees(app_id=APP_ID):
    """Dossier persistant de l'utilisateur, accessible même si le logiciel est
    installé dans un dossier protégé."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, app_id)


def dossier_projets():
    dossier = os.path.join(dossier_donnees(), "Projets")
    os.makedirs(dossier, exist_ok=True)
    return dossier


def dossier_sauvegardes():
    dossier = os.path.join(dossier_donnees(), "Sauvegardes")
    os.makedirs(dossier, exist_ok=True)
    return dossier


def anciennes_bases():
    """Bases de la version 0.1 qui peuvent être importées comme projet."""
    executable = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(sys.argv[0] or ".")
    candidats = [
        os.path.join(dossier_donnees(ANCIEN_APP_ID), "lexique_ngambay.db"),
        os.path.join(os.path.dirname(executable), "lexique_ngambay.db"),
    ]
    vus, resultat = set(), []
    for chemin in candidats:
        cle = os.path.normcase(os.path.abspath(chemin))
        if cle not in vus and os.path.isfile(chemin):
            vus.add(cle)
            resultat.append(chemin)
    return resultat

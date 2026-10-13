"""Démarrage : choix ou création du projet, puis fenêtre principale."""

import os
import shutil
import sqlite3
import sys
from datetime import datetime

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from .. import APP_ID, APP_NAME, alignement, base, corpus, domaines
from ..chemins import anciennes_bases, dossier_sauvegardes
from ..projet import Projet, chemin_nouveau_projet, lister_projets
from .commun import CurseurAttente, appliquer_style, erreur
from .dialogues import DialogueProjets
from .fenetre import FenetrePrincipale


def _version_fichier(chemin):
    conn = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True)
    try:
        return base.version(conn)
    finally:
        conn.close()


def ouvrir_projet(chemin):
    """Ouvre le projet ; si son schéma doit être mis à jour, une copie est faite d'abord."""
    if os.path.isfile(chemin) and 0 < _version_fichier(chemin) < base.VERSION_SCHEMA:
        nom = os.path.splitext(os.path.basename(chemin))[0]
        horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(chemin, os.path.join(dossier_sauvegardes(), f"{nom}-avant-mise-a-jour-{horodatage}.lexique"))
    projet = Projet(chemin)
    with CurseurAttente():
        corpus.synchroniser(projet)
        # liste officielle des domaines sémantiques, copiée depuis FLEx si elle est installée
        domaines.charger_depuis_flex(projet.conn, projet.reglage("langue_analyse_code") or "fr")
        alignement.recalculer(projet)
    return projet


def importer_projet_flex(chemin_flex, statut="à vérifier", avec_textes=True):
    """Crée un projet à partir d'un projet FLEx (lu, jamais modifié) et l'ouvre."""
    from PySide6.QtWidgets import QProgressDialog
    from .. import flex_import
    from .commun import info
    nom = os.path.splitext(os.path.basename(chemin_flex))[0]
    attente = QProgressDialog(f"Import du projet FLEx « {nom} »… Cela peut prendre une demi-minute.", None, 0, 0)
    attente.setWindowTitle(APP_NAME)
    attente.setMinimumDuration(0)
    attente.show()
    QApplication.processEvents()
    try:
        with CurseurAttente():
            vern, analyse = flex_import.langues(chemin_flex)
            projet = Projet.creer(chemin_nouveau_projet(nom), nom=nom, langue_vern_code=vern, langue_vern_nom=vern,
                                  langue_analyse_code=analyse,
                                  langue_analyse_nom={"fr": "français", "en": "anglais"}.get(analyse, analyse))
            domaines.charger_depuis_flex(projet.conn, analyse)
            rapport = flex_import.importer(projet, chemin_flex, statut, avec_textes)
            projet.fermer()
    finally:
        attente.close()
    info(None, "Import FLEx", rapport.resume())
    return ouvrir_projet(projet.chemin)


def _executer_action(action):
    genre, valeur = action
    if genre == "ouvrir":
        return ouvrir_projet(valeur)
    if genre == "creer":
        projet = Projet.creer(chemin_nouveau_projet(valeur["nom"]), **valeur)
        projet.fermer()
        return ouvrir_projet(projet.chemin)
    if genre == "importer_flex":
        return importer_projet_flex(*valeur)
    if genre == "importer_v01":
        projet = Projet.importer_v01(valeur, chemin_nouveau_projet("Ngambay"))
        projet.fermer()
        return ouvrir_projet(projet.chemin)
    raise ValueError(genre)


def choisir_projet(reglages, premier_lancement):
    """Retourne un Projet ouvert, ou None si l'utilisateur abandonne."""
    dernier = reglages.value("dernier_projet", "")
    if premier_lancement and dernier and os.path.isfile(dernier):
        try:
            return ouvrir_projet(dernier)
        except Exception as e:
            erreur(None, APP_NAME, f"Le dernier projet n'a pas pu être ouvert :\n{dernier}", e)

    if premier_lancement and not lister_projets() and anciennes_bases():
        ancienne = anciennes_bases()[0]
        if QMessageBox.question(
                None, APP_NAME,
                f"Une base de la version précédente a été trouvée :\n{ancienne}\n\n"
                "La convertir en projet « Ngambay » ? La base d'origine n'est pas modifiée.") == QMessageBox.Yes:
            try:
                return _executer_action(("importer_v01", ancienne))
            except Exception as e:
                erreur(None, APP_NAME, "La conversion a échoué. La base d'origine est intacte.", e)

    while True:
        dialogue = DialogueProjets()
        if not dialogue.exec() or not dialogue.action:
            return None
        try:
            return _executer_action(dialogue.action)
        except Exception as e:
            erreur(None, APP_NAME, "Ce projet n'a pas pu être ouvert.", e)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ID)
    appliquer_style(app)
    reglages = QSettings(APP_ID, APP_ID)

    premier = True
    while True:
        projet = choisir_projet(reglages, premier)
        premier = False
        if projet is None:
            return 0
        reglages.setValue("dernier_projet", projet.chemin)
        fenetre = FenetrePrincipale(projet)
        changer = []
        fenetre.changer_de_projet.connect(lambda: changer.append(True))
        fenetre.show()
        app.exec()
        projet.fermer()
        if not changer:
            return 0

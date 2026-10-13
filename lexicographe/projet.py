"""Un projet = une langue documentée = un fichier .lexique (SQLite).

Les réglages du projet (langues, règles de découpage en mots…) sont stockés
dans le fichier lui-même : copier le fichier suffit à transmettre le projet.
"""

import os
import re
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from . import base
from .chemins import dossier_projets, dossier_sauvegardes
from .texte import MOTS_VIDES_FRANCAIS, Tokeniseur

EXTENSION = ".lexique"

REGLAGES_PAR_DEFAUT = {
    "nom": "Nouveau projet",
    "langue_vern_code": "",
    "langue_vern_nom": "",
    "langue_analyse_code": "fr",
    "langue_analyse_nom": "français",
    # caractères qui font partie des mots en plus des lettres, marques et chiffres
    "caracteres_mot_vern": "-’'ʼ",
    "caracteres_mot_analyse": "-",
    "longueur_min_mot": "1",
    "mots_vides_analyse": " ".join(MOTS_VIDES_FRANCAIS),
    # score minimal (coefficient de Dice) pour signaler une contradiction
    "seuil_contradiction": "0.5",
    "corpus_integre": "",
    # ordre alphabétique de la langue documentée (graphèmes séparés par des espaces)
    "alphabet_vern": "",
    "police_vern": "",
}


class Projet:
    def __init__(self, chemin):
        self.chemin = os.path.abspath(chemin)
        self.conn = base.connecter(self.chemin)
        base.migrer(self.conn)
        self._reglages = None

    # -- création / ouverture ----------------------------------------------------
    @classmethod
    def creer(cls, chemin, **reglages):
        if os.path.exists(chemin):
            raise FileExistsError(f"Un fichier existe déjà à cet emplacement : {chemin}")
        projet = cls(chemin)
        valeurs = dict(REGLAGES_PAR_DEFAUT, **{k: v for k, v in reglages.items() if v is not None})
        projet.definir_reglages(valeurs)
        return projet

    @classmethod
    def importer_v01(cls, ancienne_base, chemin):
        """Crée un projet à partir d'une base de la version 0.1 (ngambay).
        La base d'origine n'est jamais modifiée : on travaille sur une copie."""
        if os.path.exists(chemin):
            raise FileExistsError(f"Un fichier existe déjà à cet emplacement : {chemin}")
        source = sqlite3.connect(ancienne_base)
        try:
            cible = sqlite3.connect(chemin)
            source.backup(cible)
            cible.close()
        finally:
            source.close()
        projet = cls(chemin)
        projet.definir_reglages(dict(
            REGLAGES_PAR_DEFAUT,
            nom="Ngambay",
            langue_vern_code="sba",
            langue_vern_nom="ngambay",
            # règles de la v0.1 : l'apostrophe sépare les mots, mots d'une lettre ignorés
            caracteres_mot_vern="-",
            longueur_min_mot="2",
            corpus_integre="ngambay_ruth_job",
        ))
        return projet

    def fermer(self):
        self.conn.close()

    @contextmanager
    def en_lot(self):
        """Opérations en masse (imports) : le disque n'est pas forcé à chaque validation,
        ce qui les rend des dizaines de fois plus rapides. Une sauvegarde doit être faite
        avant : en cas de coupure de courant pendant l'import, on repart de cette sauvegarde."""
        ancien = self.conn.execute("PRAGMA synchronous").fetchone()[0]
        self.conn.execute("PRAGMA synchronous = OFF")
        try:
            yield
        finally:
            self.conn.commit()
            self.conn.execute(f"PRAGMA synchronous = {int(ancien)}")

    # -- réglages ----------------------------------------------------------------
    @property
    def reglages(self):
        if self._reglages is None:
            lus = dict(self.conn.execute("SELECT cle, valeur FROM projet").fetchall())
            self._reglages = dict(REGLAGES_PAR_DEFAUT, **lus)
        return self._reglages

    def reglage(self, cle):
        return self.reglages.get(cle, "")

    def definir_reglages(self, valeurs):
        with self.conn:
            self.conn.executemany("INSERT OR REPLACE INTO projet (cle, valeur) VALUES (?, ?)",
                                  [(k, str(v)) for k, v in valeurs.items()])
        self._reglages = None

    @property
    def nom(self):
        return self.reglage("nom")

    @property
    def tokeniseur_vern(self):
        return Tokeniseur(self.reglage("caracteres_mot_vern"), self.reglage("longueur_min_mot") or 1)

    @property
    def tokeniseur_analyse(self):
        return Tokeniseur(self.reglage("caracteres_mot_analyse"), 1,
                          self.reglage("mots_vides_analyse").split())

    @property
    def dossier_medias(self):
        racine, _ = os.path.splitext(self.chemin)
        return racine + "_medias"

    # -- sauvegarde ----------------------------------------------------------------
    def sauvegarder_vers(self, destination):
        """Copie cohérente du projet, même pendant son utilisation."""
        cible = sqlite3.connect(destination)
        try:
            self.conn.backup(cible)
        finally:
            cible.close()
        return destination

    def sauvegarde_automatique(self, garder=10):
        """Copie horodatée dans le dossier de sauvegardes ; garde les plus récentes."""
        nom = nom_fichier_sur(self.nom)
        horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
        destination = os.path.join(dossier_sauvegardes(), f"{nom}-{horodatage}{EXTENSION}")
        self.sauvegarder_vers(destination)
        anciennes = sorted(f for f in os.listdir(dossier_sauvegardes())
                           if f.startswith(nom + "-") and f.endswith(EXTENSION))
        for fichier in anciennes[:-garder]:
            try:
                os.remove(os.path.join(dossier_sauvegardes(), fichier))
            except OSError:
                pass
        return destination


def nom_fichier_sur(nom):
    nom = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", nom).strip(" .")
    return nom or "projet"


def chemin_nouveau_projet(nom):
    """Chemin libre dans le dossier des projets pour un nom donné."""
    base_nom = nom_fichier_sur(nom)
    chemin = os.path.join(dossier_projets(), base_nom + EXTENSION)
    n = 2
    while os.path.exists(chemin):
        chemin = os.path.join(dossier_projets(), f"{base_nom} ({n}){EXTENSION}")
        n += 1
    return chemin


def lister_projets():
    """[(nom affiché, chemin)] des projets du dossier par défaut."""
    resultat = []
    for fichier in sorted(os.listdir(dossier_projets())):
        if fichier.endswith(EXTENSION):
            chemin = os.path.join(dossier_projets(), fichier)
            nom = os.path.splitext(fichier)[0]
            try:
                conn = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True)
                ligne = conn.execute("SELECT valeur FROM projet WHERE cle='nom'").fetchone()
                conn.close()
                if ligne and ligne[0]:
                    nom = ligne[0]
            except sqlite3.Error:
                pass
            resultat.append((nom, chemin))
    return resultat


def copier_medias(projet, source):
    """Copie un fichier média dans le dossier du projet sans écraser d'existant."""
    os.makedirs(projet.dossier_medias, exist_ok=True)
    nom = os.path.basename(source)
    racine, extension = os.path.splitext(nom)
    destination = os.path.join(projet.dossier_medias, nom)
    n = 2
    while True:
        try:
            with open(source, "rb") as src, open(destination, "xb") as dst:
                shutil.copyfileobj(src, dst)
            break
        except FileExistsError:
            destination = os.path.join(projet.dossier_medias, f"{racine} ({n}){extension}")
            n += 1
    shutil.copystat(source, destination)
    return destination

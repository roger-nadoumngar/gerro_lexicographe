"""Construction de l'application Android avec Dictionary App Builder : réglages, puis construction
dans un fil d'exécution séparé (plusieurs minutes), avec le journal de DAB à la fin."""

import glob
import os

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QProgressDialog, QPushButton, QVBoxLayout, QWidget)

from .. import appli_android
from .commun import erreur, info

DOSSIER_APP_BUILDER = os.path.join(os.path.expanduser("~"), "Documents", "App Builder")


class _Chemin(QWidget):
    def __init__(self, texte, filtre=None, dossier=False, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        self.champ = QLineEdit(texte)
        bouton = QPushButton("…")
        bouton.setFixedWidth(34)
        bouton.clicked.connect(lambda: self._choisir(filtre, dossier))
        h.addWidget(self.champ, 1)
        h.addWidget(bouton)

    def _choisir(self, filtre, dossier):
        if dossier:
            chemin = QFileDialog.getExistingDirectory(self, "Dossier", self.champ.text())
        else:
            chemin, _ = QFileDialog.getOpenFileName(self, "Fichier", os.path.dirname(self.champ.text()), filtre or "")
        if chemin:
            self.champ.setText(os.path.normpath(chemin))

    def texte(self):
        return self.champ.text().strip()


class DialogueAppli(QDialog):
    def __init__(self, projet, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Application Android")
        self.setMinimumWidth(640)
        self.projet = projet
        v = QVBoxLayout(self)
        aide = QLabel("L'application est construite par Dictionary App Builder (SIL), à partir du lexique, des "
                      "images et des réglages ci-dessous. Gardez toujours le même keystore pour une même "
                      "application : sans lui, les téléphones refusent les mises à jour.")
        aide.setWordWrap(True)
        aide.setObjectName("sousTitre")
        v.addWidget(aide)
        f = QFormLayout()
        langue = projet.reglage("langue_vern_nom") or projet.nom
        analyse = projet.reglage("langue_analyse_nom") or "français"
        self.nom = QLineEdit(f"Dictionnaire {langue}–{analyse}")
        self.paquet = QLineEdit(appli_android.nom_de_paquet(projet.reglage("langue_vern_code"), projet.nom))
        keystores = sorted(glob.glob(os.path.join(DOSSIER_APP_BUILDER, "keystore", "*.keystore")) +
                           glob.glob(os.path.join(DOSSIER_APP_BUILDER, "keystore", "*.jks")))
        self.keystore = _Chemin(keystores[0] if keystores else "", "Keystore (*.keystore *.jks);;Tous (*)")
        self.alias = QLineEdit("key1" if keystores else "")
        self.mdp = QLineEdit()
        self.mdp.setEchoMode(QLineEdit.Password)
        self.mdp_alias = QLineEdit()
        self.mdp_alias.setEchoMode(QLineEdit.Password)
        self.mdp_alias.setPlaceholderText("vide = même mot de passe")
        self.icone = _Chemin("", "Images PNG (*.png)")
        self.icone.champ.setPlaceholderText("facultatif : PNG carré (sinon une icône simple est produite)")
        self.interface = QComboBox()
        self.interface.addItem("Français", "fr")
        self.interface.addItem("English", "en")
        self.projets = _Chemin(os.path.join(DOSSIER_APP_BUILDER, "Dictionary Apps", "App Projects"), dossier=True)
        self.sortie = _Chemin(os.path.join(DOSSIER_APP_BUILDER, "Dictionary Apps", "Apk Output"), dossier=True)
        self.apropos = QPlainTextEdit(f"{self.nom.text()}\nProduit avec Gerro Lexicographe.")
        self.apropos.setFixedHeight(80)
        for libelle, champ in [("Nom de l'application", self.nom), ("Nom de paquet", self.paquet),
                               ("Keystore", self.keystore), ("Alias de la clé", self.alias),
                               ("Mot de passe du keystore", self.mdp), ("Mot de passe de la clé", self.mdp_alias),
                               ("Icône", self.icone), ("Langue des menus", self.interface),
                               ("Projets DAB", self.projets), ("APK produits dans", self.sortie),
                               ("À propos (auteurs, sources, contact)", self.apropos)]:
            f.addRow(libelle, champ)
        v.addLayout(f)
        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        boutons.button(QDialogButtonBox.Ok).setText("Construire l'application")
        boutons.accepted.connect(self._accepter)
        boutons.rejected.connect(self.reject)
        v.addWidget(boutons)

    def _accepter(self):
        if not self.nom.text().strip() or not self.paquet.text().strip():
            erreur(self, "Application Android", "Indiquez le nom de l'application et le nom de paquet.")
            return
        if not os.path.isfile(self.keystore.texte()) or not self.alias.text().strip() or not self.mdp.text():
            erreur(self, "Application Android", "Le keystore, l'alias et le mot de passe sont nécessaires pour "
                                                "signer l'application.")
            return
        self.accept()

    def options(self):
        icones = []
        if self.icone.texte():
            icones = _icones_depuis(self.icone.texte(), self.sortie.texte())
        return appli_android.Options(
            nom_app=self.nom.text().strip(), paquet=self.paquet.text().strip(),
            dossier_projets=self.projets.texte(), dossier_apk=self.sortie.texte(),
            keystore=self.keystore.texte(), alias=self.alias.text().strip(), mot_de_passe=self.mdp.text(),
            mot_de_passe_alias=self.mdp_alias.text(), apropos=self.apropos.toPlainText().strip(),
            icones=icones, langue_interface=self.interface.currentData())


def _icones_depuis(png, dossier):
    """Icône choisie, mise aux tailles demandées par DAB (72×72 et 144×144)."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage
    image = QImage(png)
    if image.isNull():
        return []
    os.makedirs(dossier, exist_ok=True)
    chemins = []
    for taille in (72, 144):
        chemin = os.path.join(dossier, f"icone-{taille}.png")
        image.scaled(taille, taille, Qt.KeepAspectRatio, Qt.SmoothTransformation).save(chemin)
        chemins.append(chemin)
    return chemins


class _Construction(QThread):
    etape = Signal(str)
    fini = Signal(object, str)

    def __init__(self, projet_chemin, options):
        super().__init__()
        self.projet_chemin = projet_chemin
        self.options = options

    def run(self):
        from ..projet import Projet
        projet = Projet(self.projet_chemin)   # connexion propre à ce fil d'exécution
        try:
            resultat = appli_android.construire(projet, self.options, self.etape.emit)
            self.fini.emit(resultat, "")
        except Exception as e:   # transmis à l'interface
            self.fini.emit(None, str(e))
        finally:
            projet.fermer()


def construire_appli(parent, projet):
    if not appli_android.dossier_dab():
        erreur(parent, "Application Android", "Dictionary App Builder n'est pas installé. Il est gratuit : "
                                              "https://software.sil.org/dictionaryappbuilder/")
        return
    d = DialogueAppli(projet, parent)
    if d.exec() != QDialog.Accepted:
        return
    options = d.options()
    attente = QProgressDialog("Préparation…", None, 0, 0, parent)
    attente.setWindowTitle("Application Android")
    attente.setMinimumDuration(0)
    attente.setMinimumWidth(460)
    fil = _Construction(projet.chemin, options)
    fil.etape.connect(attente.setLabelText)

    def termine(resultat, message):
        attente.close()
        if message:
            erreur(parent, "Application Android", "L'application n'a pas pu être construite.", message)
        elif resultat.apk:
            info(parent, "Application Android", f"Application prête :\n{resultat.apk}\n\nCopiez ce fichier .apk sur "
                                                "un téléphone Android pour l'installer. Le projet Dictionary App "
                                                f"Builder peut être ouvert pour d'autres réglages :\n{resultat.projet_dab}")
        else:
            _journal(parent, resultat.journal)
    fil.fini.connect(termine)
    parent._construction_android = fil   # garder le fil en vie
    fil.start()
    attente.show()


def _journal(parent, texte):
    d = QDialog(parent)
    d.setWindowTitle("Application Android — journal de Dictionary App Builder")
    d.resize(820, 520)
    v = QVBoxLayout(d)
    v.addWidget(QLabel("Dictionary App Builder n'a pas produit d'application. Son journal :"))
    zone = QPlainTextEdit(texte[-20000:])
    zone.setReadOnly(True)
    v.addWidget(zone, 1)
    fermer = QPushButton("Fermer")
    fermer.clicked.connect(d.accept)
    v.addWidget(fermer)
    d.exec()

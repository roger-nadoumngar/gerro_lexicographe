"""Fenêtre principale : navigation à gauche, pages à droite."""


from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QListWidget, QMainWindow, QMessageBox, QStackedWidget,
                               QWidget)

from .. import APP_NAME, __version__, alignement
from ..chemins import dossier_sauvegardes
from ..projet import EXTENSION
from .commun import CurseurAttente, erreur, info
from .dialogues import DialogueReglages
from .pages import PageCorpus, PageExports, PageLexique, PageTableauDeBord, PageValidation


class FenetrePrincipale(QMainWindow):
    changer_de_projet = Signal()

    def __init__(self, projet):
        super().__init__()
        self.projet = projet
        self.resize(1180, 760)
        self.setMinimumSize(900, 600)

        centre = QWidget()
        h = QHBoxLayout(centre)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setFixedWidth(190)
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.pile = QStackedWidget()
        h.addWidget(self.navigation)
        h.addWidget(self.pile, 1)
        self.setCentralWidget(centre)

        self.pages = [
            ("Tableau de bord", PageTableauDeBord(projet)),
            ("Lexique", PageLexique(projet)),
            ("Validation", PageValidation(projet)),
            ("Corpus", PageCorpus(projet)),
            ("Exports", PageExports(projet)),
        ]
        for nom, page in self.pages:
            self.navigation.addItem(nom)
            self.pile.addWidget(page)
            page.donnees_modifiees.connect(self.rafraichir_tout)
        self.navigation.currentRowChanged.connect(self._changer_page)
        self._page_courante = 0
        self.navigation.setCurrentRow(0)

        self._menus()
        self._titre()
        self.rafraichir_tout()

    def _menus(self):
        fichier = self.menuBar().addMenu("&Fichier")
        for texte, raccourci, action in [
            ("Changer de projet…", QKeySequence.Open, self._changer_projet),
            ("Enregistrer une copie du projet…", None, self._copie),
            ("Ouvrir le dossier des sauvegardes", None,
             lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(dossier_sauvegardes()))),
            (None, None, None),
            ("Réglages du projet…", "Ctrl+,", self._reglages),
            (None, None, None),
            ("Quitter", QKeySequence.Quit, self.close),
        ]:
            if texte is None:
                fichier.addSeparator()
                continue
            a = QAction(texte, self)
            if raccourci:
                a.setShortcut(raccourci)
            a.triggered.connect(action)
            fichier.addAction(a)
        aide = self.menuBar().addMenu("&Aide")
        a = QAction("À propos", self)
        a.triggered.connect(lambda: QMessageBox.about(
            self, APP_NAME, f"<b>{APP_NAME}</b> {__version__}<br>Lexicographie et documentation des langues.<br>"
                            f"Projet : {self.projet.chemin}"))
        aide.addAction(a)

    def _titre(self):
        langue = self.projet.reglage("langue_vern_nom")
        code = self.projet.reglage("langue_vern_code")
        self.setWindowTitle(f"{self.projet.nom} — {langue} [{code}] — {APP_NAME}")

    def _changer_page(self, index):
        if index == self._page_courante:
            return
        if not self.pages[self._page_courante][1].peut_quitter():
            self.navigation.blockSignals(True)
            self.navigation.setCurrentRow(self._page_courante)
            self.navigation.blockSignals(False)
            return
        self._page_courante = index
        self.pile.setCurrentIndex(index)
        self.pages[index][1].rafraichir()

    def rafraichir_tout(self):
        for _, page in self.pages:
            page.rafraichir()

    def _reglages(self):
        d = DialogueReglages(self.projet, self)
        if d.exec():
            if d.decoupage_modifie:
                with CurseurAttente():
                    alignement.recalculer(self.projet)
            self._titre()
            self.rafraichir_tout()

    def _copie(self):
        chemin, _ = QFileDialog.getSaveFileName(self, "Enregistrer une copie", f"{self.projet.nom}{EXTENSION}",
                                                f"Projet (*{EXTENSION})")
        if chemin:
            try:
                self.projet.sauvegarder_vers(chemin)
            except Exception as e:
                erreur(self, "Copie impossible", "La copie n'a pas pu être enregistrée.", e)
                return
            info(self, "Copie enregistrée", f"Copie du projet enregistrée :\n{chemin}")

    def _changer_projet(self):
        if self.close():
            self.changer_de_projet.emit()

    def closeEvent(self, event):
        if not self.pages[self._page_courante][1].peut_quitter():
            event.ignore()
            return
        try:
            self.projet.sauvegarde_automatique()
        except Exception as e:
            erreur(self, "Sauvegarde", "La sauvegarde automatique a échoué. Le projet lui-même est intact.", e)
        event.accept()

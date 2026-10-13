"""Navigation dans les domaines sémantiques : arbre, recherche, description et
questions d'élicitation."""

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QLineEdit, QSplitter, QTextBrowser,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import domaines


class ArbreDomaines(QWidget):
    """Arbre filtrable + panneau de détails. Signal `choisi(guid)` au double-clic."""
    choisi = Signal(str)
    selection_changee = Signal(str)

    def __init__(self, projet, parent=None):
        super().__init__(parent)
        self.projet = projet
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Chercher un domaine (code, nom ou mot-exemple : « 1.1 », « ciel », « pluie »…)")
        self.recherche.setClearButtonEnabled(True)
        self.recherche.textChanged.connect(self._filtrer)
        v.addWidget(self.recherche)
        separateur = QSplitter(Qt.Horizontal)
        self.arbre = QTreeWidget()
        self.arbre.setHeaderHidden(True)
        self.arbre.currentItemChanged.connect(self._details)
        self.arbre.itemDoubleClicked.connect(lambda item, _: self.choisi.emit(item.data(0, Qt.UserRole)))
        separateur.addWidget(self.arbre)
        self.details = QTextBrowser()
        separateur.addWidget(self.details)
        separateur.setSizes([380, 420])
        v.addWidget(separateur, 1)
        self.items = {}
        self.charger()

    @property
    def langue(self):
        return self.projet.reglage("langue_analyse_code") or "fr"

    def charger(self):
        self.arbre.clear()
        self.items = {}
        for guid, code, nom, parent in domaines.arbre(self.projet.conn, self.langue):
            item = QTreeWidgetItem([f"{code}  {nom}"])
            item.setData(0, Qt.UserRole, guid)
            self.items[guid] = item
            parent_item = self.items.get(parent)
            (parent_item.addChild(item) if parent_item else self.arbre.addTopLevelItem(item))
        if not self.items:
            self.details.setHtml("<p>Aucune liste de domaines dans ce projet.</p><p>Elle est copiée automatiquement "
                                 "depuis FLEx s'il est installé ; sinon, utilise « Importer une liste de domaines » "
                                 "dans la page Domaines.</p>")

    def guid_courant(self):
        item = self.arbre.currentItem()
        return item.data(0, Qt.UserRole) if item else None

    def selectionner(self, guid):
        item = self.items.get(guid)
        if item:
            self.arbre.setCurrentItem(item)
            self.arbre.scrollToItem(item)

    def _filtrer(self, texte):
        texte = texte.strip()
        if not texte:
            for item in self.items.values():
                item.setHidden(False)
            self.arbre.collapseAll()
            return
        visibles = {g for g, _, _ in domaines.chercher(self.projet.conn, texte, self.langue, limite=5000)}
        # un domaine visible garde ses parents visibles
        for guid, item in self.items.items():
            item.setHidden(True)
        for guid in visibles:
            item = self.items.get(guid)
            while item is not None:
                item.setHidden(False)
                item.setExpanded(True)
                item = item.parent()
        premier = next((self.items[g] for g in self.items if g in visibles), None)
        if premier:
            self.arbre.setCurrentItem(premier)

    def _details(self, item, _ancien=None):
        if not item:
            return
        guid = item.data(0, Qt.UserRole)
        d = domaines.details(self.projet.conn, guid, self.langue)
        morceaux = [f"<h3>{html.escape(d['code'])} {html.escape(d['nom'])}</h3>"]
        if d["description"]:
            morceaux.append(f"<p>{html.escape(d['description'])}</p>")
        for q in d["questions"]:
            morceaux.append(f"<p><b>{html.escape(q['question'])}</b><br>"
                            f"<span style='color:#6B6857'>{html.escape(q['mots'])}</span></p>")
        self.details.setHtml("".join(morceaux))
        self.selection_changee.emit(guid)


class DialogueDomaine(QDialog):
    """Choix d'un domaine ; `guid` contient le choix après acceptation."""

    def __init__(self, projet, parent=None, guid=None):
        super().__init__(parent)
        self.setWindowTitle("Choisir un domaine sémantique")
        self.resize(860, 600)
        self.guid = None
        v = QVBoxLayout(self)
        self.arbre = ArbreDomaines(projet)
        self.arbre.choisi.connect(self._accepter)
        v.addWidget(self.arbre, 1)
        aide = QLabel("Double-clique sur un domaine, ou sélectionne-le puis valide.")
        aide.setObjectName("sousTitre")
        v.addWidget(aide)
        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        boutons.accepted.connect(lambda: self._accepter(self.arbre.guid_courant()))
        boutons.rejected.connect(self.reject)
        v.addWidget(boutons)
        if guid:
            self.arbre.selectionner(guid)
        self.arbre.recherche.setFocus()

    def _accepter(self, guid):
        if guid:
            self.guid = guid
            self.accept()

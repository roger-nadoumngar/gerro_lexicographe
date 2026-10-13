"""Éditeur d'une entrée lexicale : forme, sens (glose, catégorie, domaine,
définition, exemples), notes, propriétés et relations."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QFormLayout, QFrame, QScrollArea, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget, QCompleter)

from .. import lexique
from ..lexique import Entree, Exemple, Sens
from .commun import confirmer, erreur

# liste provisoire : la phase 1 la remplace par les domaines sémantiques officiels de SIL
DOMAINES_SUGGERES = [
    "", "personne", "famille / relations", "corps humain", "animal", "plante", "nourriture",
    "objet / outil", "vêtement", "habitation / lieu", "nature / environnement", "temps",
    "quantité / nombre", "action / mouvement", "sentiment / état", "religion / spirituel", "couleur", "autre",
]


def _texte(table, ligne, col):
    item = table.item(ligne, col)
    return item.text().strip() if item else ""


class OngletSens(QGroupBox):
    """Un sens de l'entrée, dans son cadre « Sens n »."""
    modifie = Signal()
    retirer_demande = Signal(object)

    def __init__(self, categories, parent=None):
        super().__init__(parent)
        self.sens_id = None
        form = QFormLayout(self)
        retirer_sens = QPushButton("Retirer ce sens")
        retirer_sens.clicked.connect(lambda: self.retirer_demande.emit(self))
        form.addRow("", retirer_sens)
        form.itemAt(form.rowCount() - 1, QFormLayout.FieldRole).setAlignment(Qt.AlignRight)
        self.glose = QLineEdit()
        self.glose.setPlaceholderText("traduction courte, ex. : arbre")
        self.categorie = QComboBox()
        self.categorie.addItem("", None)
        for cid, nom, abrev, _ in categories:
            self.categorie.addItem(nom + (f"  ({abrev})" if abrev else ""), cid)
        self.domaine = QComboBox()
        self.domaine.setEditable(True)
        self.domaine.addItems(DOMAINES_SUGGERES)
        self.definition = QPlainTextEdit()
        self.definition.setFixedHeight(60)
        self.exemples = QTableWidget(0, 3)
        self.exemples.setHorizontalHeaderLabels(["Exemple (langue)", "Traduction", "Référence"])
        self.exemples.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.exemples.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.exemples.setWordWrap(True)
        self.exemples.setMinimumHeight(110)
        boutons = QHBoxLayout()
        ajouter = QPushButton("+ Exemple")
        retirer = QPushButton("Retirer l'exemple")
        ajouter.clicked.connect(lambda: self._ajouter_exemple(Exemple()))
        retirer.clicked.connect(self._retirer_exemple)
        boutons.addWidget(ajouter)
        boutons.addWidget(retirer)
        boutons.addStretch()

        form.addRow("Glose :", self.glose)
        form.addRow("Catégorie :", self.categorie)
        form.addRow("Domaine sémantique :", self.domaine)
        form.addRow("Définition :", self.definition)
        form.addRow("Exemples :", self.exemples)
        form.addRow("", self._envelopper(boutons))

        self.glose.textEdited.connect(self.modifie)
        self.categorie.currentIndexChanged.connect(self.modifie)
        self.domaine.editTextChanged.connect(self.modifie)
        self.definition.textChanged.connect(self.modifie)
        self.exemples.itemChanged.connect(self.modifie)

    @staticmethod
    def _envelopper(layout):
        w = QWidget()
        layout.setContentsMargins(0, 0, 0, 0)
        w.setLayout(layout)
        return w

    def _ajouter_exemple(self, ex):
        n = self.exemples.rowCount()
        self.exemples.insertRow(n)
        for col, valeur in enumerate((ex.vernaculaire, ex.traduction, ex.reference)):
            self.exemples.setItem(n, col, QTableWidgetItem(valeur))
        self.exemples.resizeRowsToContents()
        self.modifie.emit()

    def _retirer_exemple(self):
        ligne = self.exemples.currentRow()
        if ligne >= 0:
            self.exemples.removeRow(ligne)
            self.modifie.emit()

    def charger(self, sens: Sens):
        self.blockSignals(True)
        self.sens_id = sens.id
        self.glose.setText(sens.glose)
        i = self.categorie.findData(sens.categorie_id)
        self.categorie.setCurrentIndex(i if i >= 0 else 0)
        self.domaine.setEditText(sens.domaine)
        self.definition.setPlainText(sens.definition)
        self.exemples.setRowCount(0)
        for ex in sens.exemples:
            self._ajouter_exemple(ex)
        self.blockSignals(False)

    def valeur(self) -> Sens:
        exemples = [Exemple(_texte(self.exemples, r, 0), _texte(self.exemples, r, 1), _texte(self.exemples, r, 2))
                    for r in range(self.exemples.rowCount())]
        return Sens(id=self.sens_id, glose=self.glose.text().strip(), definition=self.definition.toPlainText().strip(),
                    categorie_id=self.categorie.currentData(), domaine=self.domaine.currentText().strip(),
                    exemples=exemples)


class PileSens(QWidget):
    """Les sens de l'entrée, empilés verticalement comme dans FLEx."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._sens = []

    def count(self):
        return len(self._sens)

    def widget(self, i):
        return self._sens[i]

    def ajouter(self, onglet):
        self._sens.append(onglet)
        self._layout.addWidget(onglet)
        self._numeroter()

    def retirer(self, onglet):
        self._sens.remove(onglet)
        self._layout.removeWidget(onglet)
        onglet.deleteLater()
        self._numeroter()

    def clear(self):
        for onglet in list(self._sens):
            self.retirer(onglet)

    def _numeroter(self):
        for i, onglet in enumerate(self._sens, start=1):
            onglet.setTitle(f"Sens {i}")


class EditeurEntree(QWidget):
    """Signaux : `enregistree(id)` après enregistrement, `supprimee()` après suppression."""
    enregistree = Signal(int)
    supprimee = Signal()
    modifie = Signal()

    def __init__(self, projet, mode_validation=False, parent=None):
        super().__init__(parent)
        self.projet = projet
        self.mode_validation = mode_validation
        self.entree = Entree()
        self.modifiee = False

        exterieur = QVBoxLayout(self)
        exterieur.setContentsMargins(0, 0, 0, 0)
        # le contenu défile quand la fenêtre est petite, au lieu d'écraser les champs
        zone = QScrollArea()
        zone.setWidgetResizable(True)
        zone.setFrameShape(QFrame.NoFrame)
        zone.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        interieur = QWidget()
        racine = QVBoxLayout(interieur)
        racine.setContentsMargins(0, 0, 8, 0)
        zone.setWidget(interieur)
        exterieur.addWidget(zone, 1)

        haut = QFormLayout()
        self.forme = QLineEdit()
        self.forme.setObjectName("grandeForme")
        self.forme.setStyleSheet("font-size: 20px; font-weight: 600;")
        haut.addRow("Forme :", self.forme)
        racine.addLayout(haut)

        self.onglets = PileSens()
        racine.addWidget(self.onglets)
        ligne = QHBoxLayout()
        self.btn_ajouter_sens = QPushButton("+ Ajouter un sens")
        self.btn_ajouter_sens.clicked.connect(lambda: self._ajouter_onglet(Sens(), selectionner=True))
        ligne.addWidget(self.btn_ajouter_sens)
        ligne.addStretch()
        racine.addLayout(ligne)

        bas = QHBoxLayout()
        notes_boite = QGroupBox("Notes")
        nb = QVBoxLayout(notes_boite)
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("étymologie, usage, remarques…")
        nb.addWidget(self.notes)
        bas.addWidget(notes_boite, 1)

        prop_boite = QGroupBox("Propriétés")
        pb = QVBoxLayout(prop_boite)
        self.proprietes = QTableWidget(0, 2)
        self.proprietes.setHorizontalHeaderLabels(["Nom", "Valeur"])
        self.proprietes.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        pb.addWidget(self.proprietes)
        pl = QHBoxLayout()
        b1, b2 = QPushButton("+"), QPushButton("−")
        b1.setToolTip("Ajouter une propriété (ton, classe nominale, emprunt…)")
        b1.clicked.connect(self._ajouter_propriete)
        b2.clicked.connect(lambda: self.proprietes.removeRow(self.proprietes.currentRow()) or self._marquer())
        pl.addWidget(b1)
        pl.addWidget(b2)
        pl.addStretch()
        pb.addLayout(pl)
        bas.addWidget(prop_boite, 1)
        racine.addLayout(bas, 1)

        self.relations_boite = QGroupBox("Relations lexicales")
        rb = QVBoxLayout(self.relations_boite)
        self.relations = QListWidget()
        self.relations.setMaximumHeight(90)
        rb.addWidget(self.relations)
        rl = QHBoxLayout()
        self.type_relation = QComboBox()
        self.type_relation.addItems(lexique.TYPES_RELATIONS)
        self.cible_relation = QComboBox()
        self.cible_relation.setEditable(True)
        self.cible_relation.setInsertPolicy(QComboBox.NoInsert)
        self.cible_relation.completer().setCompletionMode(QCompleter.PopupCompletion)
        self.cible_relation.setMinimumWidth(160)
        ajouter_rel = QPushButton("Relier")
        retirer_rel = QPushButton("Retirer")
        ajouter_rel.clicked.connect(self._ajouter_relation)
        retirer_rel.clicked.connect(self._retirer_relation)
        for w in (QLabel("Type :"), self.type_relation, QLabel("Entrée :"), self.cible_relation,
                  ajouter_rel, retirer_rel):
            rl.addWidget(w)
        rl.addStretch()
        rb.addLayout(rl)
        racine.addWidget(self.relations_boite)
        self.relations_boite.setVisible(not mode_validation)

        actions = QHBoxLayout()
        self.etat = QLabel("")
        self.etat.setProperty("class", "discret")
        actions.addWidget(self.etat)
        actions.addStretch()
        self.btn_supprimer = QPushButton("Supprimer l'entrée")
        self.btn_annuler = QPushButton("Annuler les modifications")
        self.btn_enregistrer = QPushButton("Enregistrer")
        self.btn_enregistrer.setObjectName("principal")
        self.btn_enregistrer.setShortcut("Ctrl+S")
        self.btn_supprimer.clicked.connect(self._supprimer)
        self.btn_annuler.clicked.connect(lambda: self.charger(self.entree.id))
        self.btn_enregistrer.clicked.connect(self.enregistrer)
        for b in (self.btn_supprimer, self.btn_annuler, self.btn_enregistrer):
            actions.addWidget(b)
            b.setVisible(not mode_validation)
        exterieur.addLayout(actions)

        self.forme.textEdited.connect(self._marquer)
        self.notes.textChanged.connect(self._marquer)
        self.proprietes.itemChanged.connect(self._marquer)
        self.setEnabled(False)

    # -- chargement --------------------------------------------------------------
    def _categories(self):
        return lexique.categories(self.projet.conn)

    def charger(self, entree_id):
        entree = lexique.lire_entree(self.projet.conn, entree_id) if entree_id else None
        self.charger_entree(entree)

    def charger_entree(self, entree):
        """Affiche une entrée (existante ou nouvelle, non enregistrée)."""
        self.setEnabled(entree is not None)
        self.entree = entree or Entree()
        self.blockSignals(True)
        self.forme.setText(self.entree.forme)
        self.notes.setPlainText(self.entree.notes)
        self.onglets.clear()
        for sens in self.entree.sens or [Sens()]:
            self._ajouter_onglet(sens)
        self.proprietes.setRowCount(0)
        for nom, valeur in self.entree.proprietes.items():
            self._ajouter_propriete(nom, valeur)
        self._charger_relations()
        self.blockSignals(False)
        self.modifiee = False
        self._maj_etat()

    def _charger_relations(self):
        self.relations.clear()
        self.cible_relation.clear()
        if self.entree.id is None:
            self.relations_boite.setEnabled(False)
            return
        self.relations_boite.setEnabled(True)
        for rid, typ, _, forme in lexique.relations(self.projet.conn, self.entree.id):
            item = QListWidgetItem(f"{typ} → {forme}")
            item.setData(256, rid)
            self.relations.addItem(item)
        for eid, forme, gloses, _, _ in lexique.lister_entrees(self.projet.conn):
            if eid != self.entree.id:
                self.cible_relation.addItem(f"{forme} — {gloses}" if gloses else forme, eid)
        self.cible_relation.setCurrentIndex(-1)

    def _ajouter_onglet(self, sens, selectionner=False):
        onglet = OngletSens(self._categories())
        onglet.charger(sens)
        onglet.modifie.connect(self._marquer)
        onglet.retirer_demande.connect(self._retirer_onglet)
        self.onglets.ajouter(onglet)
        if selectionner:
            onglet.glose.setFocus()
            self._marquer()

    def _retirer_onglet(self, onglet):
        if self.onglets.count() <= 1:
            erreur(self, "Sens", "Une entrée garde au moins un sens.")
            return
        self.onglets.retirer(onglet)
        self._marquer()

    def _ajouter_propriete(self, nom="", valeur=""):
        n = self.proprietes.rowCount()
        self.proprietes.insertRow(n)
        self.proprietes.setItem(n, 0, QTableWidgetItem(nom))
        self.proprietes.setItem(n, 1, QTableWidgetItem(valeur))
        if not nom:
            self.proprietes.editItem(self.proprietes.item(n, 0))

    # -- état ----------------------------------------------------------------------
    def _marquer(self, *_):
        if self.signalsBlocked():
            return
        self.modifiee = True
        self._maj_etat()
        self.modifie.emit()

    def _maj_etat(self):
        if self.entree.id is None:
            self.etat.setText("Nouvelle entrée (non enregistrée)" if self.isEnabled() else "")
        elif self.modifiee:
            self.etat.setText("Modifications non enregistrées")
        else:
            self.etat.setText(f"Modifiée le {self.entree.date_modification.split('.')[0].replace('T', ' à ')}"
                              if self.entree.date_modification else "")
        self.btn_supprimer.setEnabled(self.entree.id is not None)
        self.btn_annuler.setEnabled(self.modifiee and self.entree.id is not None)

    def valeur(self) -> Entree:
        proprietes = {}
        for r in range(self.proprietes.rowCount()):
            nom, val = _texte(self.proprietes, r, 0), _texte(self.proprietes, r, 1)
            if nom and val:
                proprietes[nom] = val
        return Entree(id=self.entree.id, guid=self.entree.guid, date_creation=self.entree.date_creation,
                      forme=self.forme.text().strip(), notes=self.notes.toPlainText().strip(),
                      sens=[self.onglets.widget(i).valeur() for i in range(self.onglets.count())],
                      proprietes=proprietes)

    # -- actions -----------------------------------------------------------------
    def enregistrer(self):
        entree = self.valeur()
        if not entree.forme:
            erreur(self, "Enregistrement", "La forme de l'entrée est vide.")
            return None
        try:
            eid = lexique.enregistrer_entree(self.projet.conn, entree)
        except Exception as e:
            erreur(self, "Enregistrement impossible", "L'entrée n'a pas pu être enregistrée.", e)
            return None
        self.charger(eid)
        self.enregistree.emit(eid)
        return eid

    def demander_si_modifiee(self):
        """True si on peut quitter l'entrée courante (enregistrée, ou modifications abandonnées)."""
        if not self.modifiee or self.mode_validation:
            return True
        reponse = confirmer(self, "Modifications non enregistrées",
                            f"Enregistrer les modifications de « {self.forme.text()} » ?")
        if reponse:
            return self.enregistrer() is not None
        return True

    def _supprimer(self):
        if self.entree.id is None:
            return
        if not confirmer(self, "Supprimer l'entrée",
                         f"Supprimer définitivement « {self.entree.forme} » et tous ses sens ?"):
            return
        lexique.supprimer_entree(self.projet.conn, self.entree.id)
        self.charger_entree(None)
        self.supprimee.emit()

    def _ajouter_relation(self):
        cible = self.cible_relation.currentData()
        if cible is None:
            i = self.cible_relation.findText(self.cible_relation.currentText())
            cible = self.cible_relation.itemData(i) if i >= 0 else None
        if cible is None:
            erreur(self, "Relation", "Choisis une entrée existante dans la liste.")
            return
        try:
            if not lexique.ajouter_relation(self.projet.conn, self.entree.id, cible, self.type_relation.currentText()):
                erreur(self, "Relation", "Cette relation existe déjà.")
        except ValueError as e:
            erreur(self, "Relation", str(e))
        self._charger_relations()

    def _retirer_relation(self):
        item = self.relations.currentItem()
        if item:
            lexique.supprimer_relation(self.projet.conn, item.data(256))
            self._charger_relations()

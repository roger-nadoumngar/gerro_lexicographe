"""Éditeur d'une entrée lexicale, inspiré de FLEx : forme et prononciation,
sens (glose, index inverse, catégorie, domaines, définition, exemples),
variantes et allomorphes, forme complexe, médias, notes, propriétés, relations."""

import os

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QPixmap
from PySide6.QtWidgets import (QComboBox, QCompleter, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from .. import domaines, lexique
from ..lexique import Entree, Exemple, Sens, Variante
from ..projet import copier_medias
from .commun import confirmer, erreur
from .domaines_ui import DialogueDomaine

ROLE_DONNEE = Qt.UserRole


def _texte(table, ligne, col):
    item = table.item(ligne, col)
    return item.text().strip() if item else ""


def police_vernaculaire(projet, taille=None):
    """Police déclarée pour la langue documentée, ou None."""
    nom = projet.reglage("police_vern")
    if not nom:
        return None
    police = QFont(nom)
    if taille:
        police.setPointSize(taille)
    return police


def _boutons(*specs):
    """Ligne de boutons : specs = (texte, fonction)."""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    for texte, fonction in specs:
        b = QPushButton(texte)
        b.clicked.connect(fonction)
        h.addWidget(b)
    h.addStretch()
    return w


def remplir_categories(combo, conn, vide=True):
    """Catégories en arbre (sous-catégories en retrait)."""
    combo.clear()
    if vide:
        combo.addItem("", None)
    for cid, nom, abrev, profondeur in lexique.categories_arbre(conn):
        combo.addItem("    " * profondeur + nom + (f"  ({abrev})" if abrev else ""), cid)


class OngletSens(QGroupBox):
    """Un sens de l'entrée, dans son cadre « Sens n »."""
    modifie = Signal()
    retirer_demande = Signal(object)

    def __init__(self, projet, parent=None):
        super().__init__(parent)
        self.projet = projet
        self.sens_id = None
        form = QFormLayout(self)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)  # étiquette au-dessus du champ si la place manque
        form.addRow("", _boutons(("Retirer ce sens", lambda: self.retirer_demande.emit(self))))

        self.glose = QLineEdit()
        self.glose.setPlaceholderText("traduction courte, ex. : arbre")
        self.inverse = QLineEdit()
        self.inverse.setPlaceholderText("vide = la glose ; plusieurs formes séparées par « ; »")
        self.categorie = QComboBox()
        remplir_categories(self.categorie, projet.conn)

        self.domaines = QListWidget()
        self.domaines.setMaximumHeight(72)
        boite_dom = QWidget()
        bd = QVBoxLayout(boite_dom)
        bd.setContentsMargins(0, 0, 0, 0)
        bd.addWidget(self.domaines)
        bd.addWidget(_boutons(("Ajouter un domaine…", self._ajouter_domaine), ("Retirer", self._retirer_domaine)))
        self.ancien_domaine = QLineEdit()
        self.ancien_domaine.setToolTip("Étiquette libre d'une version précédente : classe ce sens dans un "
                                       "domaine officiel, puis vide ce champ.")

        self.definition = QPlainTextEdit()
        self.definition.setFixedHeight(56)
        self.exemples = QTableWidget(0, 3)
        self.exemples.setHorizontalHeaderLabels(["Exemple (langue)", "Traduction", "Référence"])
        self.exemples.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.exemples.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.exemples.setWordWrap(True)
        self.exemples.setMinimumHeight(100)

        form.addRow("Glose :", self.glose)
        form.addRow("Index inverse :", self.inverse)
        form.addRow("Catégorie :", self.categorie)
        form.addRow("Domaines sémantiques :", boite_dom)
        self.ligne_ancien = form.rowCount()
        form.addRow("Ancien domaine (à reclasser) :", self.ancien_domaine)
        form.addRow("Définition :", self.definition)
        form.addRow("Exemples :", self.exemples)
        form.addRow("", _boutons(("+ Exemple", lambda: self._ajouter_exemple(Exemple())),
                                 ("Retirer l'exemple", self._retirer_exemple)))
        self._form = form

        self.glose.textEdited.connect(self.modifie)
        self.inverse.textEdited.connect(self.modifie)
        self.categorie.currentIndexChanged.connect(self.modifie)
        self.ancien_domaine.textEdited.connect(self.modifie)
        self.definition.textChanged.connect(self.modifie)
        self.exemples.itemChanged.connect(self.modifie)

    def _ajouter_domaine(self):
        d = DialogueDomaine(self.projet, self)
        if d.exec() and d.guid:
            if d.guid not in self._guids():
                self._item_domaine(d.guid)
                self.modifie.emit()

    def _item_domaine(self, guid):
        langue = self.projet.reglage("langue_analyse_code") or "fr"
        item = QListWidgetItem(domaines.libelle(self.projet.conn, guid, langue) or guid)
        item.setData(ROLE_DONNEE, guid)
        self.domaines.addItem(item)

    def _retirer_domaine(self):
        item = self.domaines.currentItem()
        if item:
            self.domaines.takeItem(self.domaines.row(item))
            self.modifie.emit()

    def _guids(self):
        return [self.domaines.item(i).data(ROLE_DONNEE) for i in range(self.domaines.count())]

    def _ajouter_exemple(self, ex):
        n = self.exemples.rowCount()
        self.exemples.insertRow(n)
        police = police_vernaculaire(self.projet)
        for col, valeur in enumerate((ex.vernaculaire, ex.traduction, ex.reference)):
            item = QTableWidgetItem(valeur)
            if col == 0 and police:
                item.setFont(police)
            self.exemples.setItem(n, col, item)
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
        self.inverse.setText(sens.inverse)
        i = self.categorie.findData(sens.categorie_id)
        self.categorie.setCurrentIndex(i if i >= 0 else 0)
        self.domaines.clear()
        for guid in sens.domaines:
            self._item_domaine(guid)
        self.ancien_domaine.setText(sens.domaine)
        self._form.setRowVisible(self.ligne_ancien, bool(sens.domaine))
        self.definition.setPlainText(sens.definition)
        self.exemples.setRowCount(0)
        for ex in sens.exemples:
            self._ajouter_exemple(ex)
        self.blockSignals(False)

    def valeur(self) -> Sens:
        exemples = [Exemple(_texte(self.exemples, r, 0), _texte(self.exemples, r, 1), _texte(self.exemples, r, 2))
                    for r in range(self.exemples.rowCount())]
        return Sens(id=self.sens_id, glose=self.glose.text().strip(), inverse=self.inverse.text().strip(),
                    definition=self.definition.toPlainText().strip(), categorie_id=self.categorie.currentData(),
                    domaine=self.ancien_domaine.text().strip(), domaines=self._guids(), exemples=exemples)


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


class ChoixEntree(QComboBox):
    """Liste déroulante de toutes les entrées, avec complétion."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.completer().setCompletionMode(QCompleter.PopupCompletion)
        self.completer().setFilterMode(Qt.MatchContains)
        self.setMinimumWidth(140)

    def remplir(self, conn, sauf=None, lignes=None):
        self.clear()
        for ligne in lignes if lignes is not None else lexique.lister_entrees(conn):
            if ligne.id != sauf:
                texte = lexique.vedette(ligne.tete, ligne.homographe)
                self.addItem(f"{texte} — {ligne.gloses}" if ligne.gloses else texte, ligne.id)
        self.setCurrentIndex(-1)

    def entree_choisie(self):
        if self.currentIndex() >= 0 and self.currentText() == self.itemText(self.currentIndex()):
            return self.currentData()
        i = self.findText(self.currentText())
        return self.itemData(i) if i >= 0 else None


class EditeurEntree(QWidget):
    """Signaux : `enregistree(id)` après enregistrement, `supprimee()` après suppression,
    `ouvrir_demande(id)` pour naviguer vers une autre entrée."""
    enregistree = Signal(int)
    supprimee = Signal()
    modifie = Signal()
    ouvrir_demande = Signal(int)

    def __init__(self, projet, mode_validation=False, parent=None):
        super().__init__(parent)
        self.projet = projet
        self.mode_validation = mode_validation
        self.entree = Entree()
        self.modifiee = False
        self._lecteur = None

        exterieur = QVBoxLayout(self)
        exterieur.setContentsMargins(0, 0, 0, 0)
        # le contenu défile quand la fenêtre est petite, au lieu d'écraser les champs
        zone = QScrollArea()
        zone.setWidgetResizable(True)
        zone.setFrameShape(QFrame.NoFrame)
        zone.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        interieur = QWidget()
        racine = QVBoxLayout(interieur)
        racine.setContentsMargins(0, 0, 8, 0)
        zone.setWidget(interieur)
        exterieur.addWidget(zone, 1)

        # -- forme -------------------------------------------------------------
        haut = QFormLayout()
        haut.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.forme = QLineEdit()
        self.forme.setStyleSheet("font-size: 20px; font-weight: 600;")
        self.homographe = QLabel("")
        self.homographe.setObjectName("sousTitre")
        ligne_forme = QHBoxLayout()
        ligne_forme.addWidget(self.forme, 1)
        ligne_forme.addWidget(self.homographe)
        haut.addRow("Forme :", ligne_forme)
        self.forme_citation = QLineEdit()
        self.forme_citation.setPlaceholderText("si la forme de dictionnaire diffère (ex. : infinitif, singulier)")
        self.prononciation = QLineEdit()
        self.prononciation.setPlaceholderText("transcription API, ex. : kóˈman")
        self.type_morph = QComboBox()
        self.type_morph.addItem("", "")
        for cle, libelle in lexique.TYPES_MORPH.items():
            self.type_morph.addItem(libelle, cle)
        self.statut = QComboBox()
        self.statut.addItems(lexique.STATUTS)
        ligne_types = QHBoxLayout()
        ligne_types.addWidget(self.type_morph, 1)
        ligne_types.addWidget(QLabel("Statut :"))
        ligne_types.addWidget(self.statut, 1)
        haut.addRow("Forme de citation :", self.forme_citation)
        haut.addRow("Prononciation :", self.prononciation)
        haut.addRow("Type morphologique :", ligne_types)
        racine.addLayout(haut)

        # -- sens ----------------------------------------------------------------
        self.onglets = PileSens()
        racine.addWidget(self.onglets)
        self.btn_ajouter_sens = QPushButton("+ Ajouter un sens")
        self.btn_ajouter_sens.clicked.connect(lambda: self._ajouter_onglet(Sens(), selectionner=True))
        ligne = QHBoxLayout()
        ligne.addWidget(self.btn_ajouter_sens)
        ligne.addStretch()
        racine.addLayout(ligne)

        # -- variantes et allomorphes ----------------------------------------------
        boite_var = QGroupBox("Variantes et allomorphes")
        bv = QVBoxLayout(boite_var)
        self.variantes = QTableWidget(0, 4)
        self.variantes.setHorizontalHeaderLabels(["Forme", "Type", "Environnement", "Note"])
        for col in (0, 2, 3):
            self.variantes.horizontalHeader().setSectionResizeMode(col, QHeaderView.Stretch)
        self.variantes.setMinimumHeight(90)
        bv.addWidget(self.variantes)
        bv.addWidget(_boutons(("+ Variante", lambda: self._ajouter_variante(Variante())),
                              ("Retirer", self._retirer_variante)))
        racine.addWidget(boite_var)

        # -- forme complexe ----------------------------------------------------------
        self.boite_complexe = QGroupBox("Forme complexe (composé, dérivé, expression…)")
        bc = QFormLayout(self.boite_complexe)
        bc.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.type_complexe = QComboBox()
        self.type_complexe.setEditable(True)
        self.type_complexe.addItems([""] + lexique.TYPES_FORMES_COMPLEXES)
        self.composants = QListWidget()
        self.composants.setMaximumHeight(80)
        self.choix_composant = ChoixEntree()
        bc.addRow("Type :", self.type_complexe)
        bc.addRow("Composants :", self.composants)
        bc.addRow("", self.choix_composant)
        bc.addRow("", _boutons(("Ajouter", self._ajouter_composant), ("↑", lambda: self._deplacer_composant(-1)),
                               ("↓", lambda: self._deplacer_composant(1)), ("Retirer", self._retirer_composant)))
        self.contenu_dans = QLabel("")
        self.contenu_dans.setWordWrap(True)
        self.contenu_dans.linkActivated.connect(lambda lien: self.ouvrir_demande.emit(int(lien)))
        bc.addRow("Apparaît dans :", self.contenu_dans)
        racine.addWidget(self.boite_complexe)

        # -- médias -----------------------------------------------------------------
        self.boite_medias = QGroupBox("Enregistrements et images")
        bm = QHBoxLayout(self.boite_medias)
        colonne = QVBoxLayout()
        self.medias = QListWidget()
        self.medias.setMaximumHeight(90)
        self.medias.currentItemChanged.connect(self._apercu_media)
        self.medias.itemDoubleClicked.connect(lambda _: self._lire_media())
        colonne.addWidget(self.medias)
        colonne.addWidget(_boutons(("+ Audio…", lambda: self._ajouter_media("prononciation")),
                                   ("+ Image…", lambda: self._ajouter_media("image"))))
        colonne.addWidget(_boutons(("▶ Écouter / ouvrir", self._lire_media), ("Retirer", self._retirer_media)))
        bm.addLayout(colonne, 1)
        self.apercu = QLabel()
        self.apercu.setFixedSize(110, 90)
        self.apercu.setAlignment(Qt.AlignCenter)
        bm.addWidget(self.apercu)
        racine.addWidget(self.boite_medias)

        # -- notes et propriétés ----------------------------------------------------
        bas = QHBoxLayout()
        notes_boite = QGroupBox("Notes")
        nb = QVBoxLayout(notes_boite)
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("étymologie, usage, remarques…")
        self.notes.setMinimumHeight(70)
        nb.addWidget(self.notes)
        bas.addWidget(notes_boite, 1)
        prop_boite = QGroupBox("Propriétés")
        pb = QVBoxLayout(prop_boite)
        self.proprietes = QTableWidget(0, 2)
        self.proprietes.setHorizontalHeaderLabels(["Nom", "Valeur"])
        self.proprietes.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.proprietes.setMinimumHeight(70)
        pb.addWidget(self.proprietes)
        pb.addWidget(_boutons(("+", lambda: self._ajouter_propriete()),
                              ("−", lambda: self.proprietes.removeRow(self.proprietes.currentRow()) or self._marquer())))
        bas.addWidget(prop_boite, 1)
        racine.addLayout(bas)

        # -- relations -----------------------------------------------------------------
        self.relations_boite = QGroupBox("Relations lexicales")
        rb = QVBoxLayout(self.relations_boite)
        self.relations = QListWidget()
        self.relations.setMaximumHeight(80)
        self.relations.itemDoubleClicked.connect(lambda item: self.ouvrir_demande.emit(item.data(ROLE_DONNEE + 1)))
        rb.addWidget(self.relations)
        rl = QHBoxLayout()
        self.type_relation = QComboBox()
        self.type_relation.addItems(lexique.TYPES_RELATIONS)
        self.type_relation.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.type_relation.setMinimumContentsLength(12)
        self.cible_relation = ChoixEntree()
        rl.addWidget(self.type_relation, 1)
        rl.addWidget(QLabel("→"))
        rl.addWidget(self.cible_relation, 2)
        rb.addLayout(rl)
        rb.addWidget(_boutons(("Relier", self._ajouter_relation), ("Retirer la relation", self._retirer_relation)))
        racine.addWidget(self.relations_boite)
        racine.addStretch()

        for boite in (self.relations_boite, self.boite_medias, self.boite_complexe):
            boite.setVisible(not mode_validation)

        # -- actions ---------------------------------------------------------------------
        actions = QHBoxLayout()
        self.etat = QLabel("")
        self.etat.setObjectName("sousTitre")
        actions.addWidget(self.etat)
        actions.addStretch()
        self.btn_supprimer = QPushButton("Supprimer l'entrée")
        self.btn_annuler = QPushButton("Annuler")
        self.btn_annuler.setToolTip("Annuler les modifications non enregistrées")
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

        for champ in (self.forme, self.forme_citation, self.prononciation):
            champ.textEdited.connect(self._marquer)
        self.type_morph.currentIndexChanged.connect(self._marquer)
        self.statut.currentIndexChanged.connect(self._marquer)
        self.type_complexe.editTextChanged.connect(self._marquer)
        self.notes.textChanged.connect(self._marquer)
        self.proprietes.itemChanged.connect(self._marquer)
        self.variantes.itemChanged.connect(self._marquer)
        self.appliquer_police()
        self.setEnabled(False)

    def appliquer_police(self):
        police = police_vernaculaire(self.projet)
        if police:
            self.forme_citation.setFont(police)
            grande = QFont(police)
            grande.setPointSize(16)
            self.forme.setFont(grande)

    # -- chargement --------------------------------------------------------------
    def charger(self, entree_id):
        entree = lexique.lire_entree(self.projet.conn, entree_id) if entree_id else None
        self.charger_entree(entree)

    def charger_entree(self, entree, lignes=None):
        """Affiche une entrée (existante ou nouvelle, non enregistrée). `lignes` :
        liste des entrées déjà calculée, pour éviter de la recalculer."""
        self.setEnabled(entree is not None)
        self.entree = entree or Entree()
        e = self.entree
        self.blockSignals(True)
        self.forme.setText(e.forme)
        numero = lexique.homographes(self.projet.conn).get(e.id, 0) if e.id else 0
        self.homographe.setText(f"homographe {numero}" if numero else "")
        self.forme_citation.setText(e.forme_citation)
        self.prononciation.setText(e.prononciation)
        self.type_morph.setCurrentIndex(max(0, self.type_morph.findData(e.type_morph)))
        self.statut.setCurrentText(e.statut)
        self.notes.setPlainText(e.notes)
        self.onglets.clear()
        for sens in e.sens or [Sens()]:
            self._ajouter_onglet(sens)
        self.variantes.setRowCount(0)
        for v in e.variantes:
            self._ajouter_variante(v)
        self.type_complexe.setEditText(e.type_forme_complexe)
        self.composants.clear()
        for cid in e.composants:
            self._item_composant(cid)
        self.proprietes.setRowCount(0)
        for nom, valeur in e.proprietes.items():
            self._ajouter_propriete(nom, valeur)
        self._charger_liens(lignes)
        self.blockSignals(False)
        self.modifiee = False
        self._maj_etat()

    def _charger_liens(self, lignes=None):
        """Relations, composants possibles, médias : ce qui suppose une entrée enregistrée."""
        conn = self.projet.conn
        self.relations.clear()
        self.medias.clear()
        self.apercu.clear()
        self.contenu_dans.setText("")
        enregistree = self.entree.id is not None
        self.relations_boite.setEnabled(enregistree)
        self.boite_medias.setEnabled(enregistree)
        if self.mode_validation:
            return
        if lignes is None:
            lignes = lexique.lister_entrees(conn)
        self.choix_composant.remplir(conn, sauf=self.entree.id, lignes=lignes)
        if not enregistree:
            return
        for rid, typ, cible_id, _ in lexique.relations(conn, self.entree.id):
            item = QListWidgetItem(f"{typ} → {lexique.libelle_entree(conn, cible_id)}")
            item.setData(ROLE_DONNEE, rid)
            item.setData(ROLE_DONNEE + 1, cible_id)
            self.relations.addItem(item)
        self.cible_relation.remplir(conn, sauf=self.entree.id, lignes=lignes)
        for lien, _, role, _, nom, chemin, note in lexique.medias_de(conn, self.entree.id):
            icone = "🔊" if role == "prononciation" else "🖼"
            item = QListWidgetItem(f"{icone} {nom}" + (f" — {note}" if note else ""))
            item.setData(ROLE_DONNEE, lien)
            item.setData(ROLE_DONNEE + 1, chemin)
            item.setData(ROLE_DONNEE + 2, role)
            self.medias.addItem(item)
        liens = [f'<a href="{eid}">{forme}</a>' for eid, forme in lexique.formes_complexes_de(conn, self.entree.id)]
        self.contenu_dans.setText(", ".join(liens) or "—")

    def _ajouter_onglet(self, sens, selectionner=False):
        onglet = OngletSens(self.projet)
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

    def _ajouter_variante(self, v):
        n = self.variantes.rowCount()
        self.variantes.insertRow(n)
        self.variantes.setItem(n, 0, QTableWidgetItem(v.forme))
        combo = QComboBox()
        combo.addItems(lexique.TYPES_VARIANTES)
        combo.setCurrentText(v.type)
        combo.currentIndexChanged.connect(self._marquer)
        self.variantes.setCellWidget(n, 1, combo)
        self.variantes.setItem(n, 2, QTableWidgetItem(v.environnement))
        self.variantes.setItem(n, 3, QTableWidgetItem(v.note))
        self._marquer()

    def _retirer_variante(self):
        if self.variantes.currentRow() >= 0:
            self.variantes.removeRow(self.variantes.currentRow())
            self._marquer()

    def _item_composant(self, cid):
        item = QListWidgetItem(lexique.libelle_entree(self.projet.conn, cid))
        item.setData(ROLE_DONNEE, cid)
        self.composants.addItem(item)

    def _ajouter_composant(self):
        cid = self.choix_composant.entree_choisie()
        if cid is None:
            erreur(self, "Composant", "Choisis une entrée existante dans la liste.")
            return
        self._item_composant(cid)
        self.choix_composant.setCurrentIndex(-1)
        self._marquer()

    def _deplacer_composant(self, decalage):
        i = self.composants.currentRow()
        j = i + decalage
        if i < 0 or not 0 <= j < self.composants.count():
            return
        item = self.composants.takeItem(i)
        self.composants.insertItem(j, item)
        self.composants.setCurrentRow(j)
        self._marquer()

    def _retirer_composant(self):
        if self.composants.currentRow() >= 0:
            self.composants.takeItem(self.composants.currentRow())
            self._marquer()

    def _ajouter_propriete(self, nom="", valeur=""):
        n = self.proprietes.rowCount()
        self.proprietes.insertRow(n)
        self.proprietes.setItem(n, 0, QTableWidgetItem(nom))
        self.proprietes.setItem(n, 1, QTableWidgetItem(valeur))
        if not nom and not self.signalsBlocked():
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
            date = self.entree.date_modification.split(".")[0]
            if date:
                jour, _, heure = date.partition("T")
                a, m, j = jour.split("-")
                self.etat.setText(f"Modifiée le {j}/{m}/{a} {heure[:5]}")
            else:
                self.etat.setText("")
        self.btn_supprimer.setEnabled(self.entree.id is not None)
        self.btn_annuler.setEnabled(self.modifiee and self.entree.id is not None)

    def valeur(self) -> Entree:
        proprietes = {}
        for r in range(self.proprietes.rowCount()):
            nom, val = _texte(self.proprietes, r, 0), _texte(self.proprietes, r, 1)
            if nom and val:
                proprietes[nom] = val
        variantes = [Variante(forme=_texte(self.variantes, r, 0), type=self.variantes.cellWidget(r, 1).currentText(),
                              environnement=_texte(self.variantes, r, 2), note=_texte(self.variantes, r, 3))
                     for r in range(self.variantes.rowCount()) if _texte(self.variantes, r, 0)]
        return Entree(id=self.entree.id, guid=self.entree.guid, date_creation=self.entree.date_creation,
                      forme=self.forme.text().strip(), forme_citation=self.forme_citation.text().strip(),
                      prononciation=self.prononciation.text().strip(), type_morph=self.type_morph.currentData() or "",
                      statut=self.statut.currentText(), type_forme_complexe=self.type_complexe.currentText().strip(),
                      composants=[self.composants.item(i).data(ROLE_DONNEE) for i in range(self.composants.count())],
                      notes=self.notes.toPlainText().strip(),
                      sens=[self.onglets.widget(i).valeur() for i in range(self.onglets.count())],
                      variantes=variantes, proprietes=proprietes)

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
        if confirmer(self, "Modifications non enregistrées",
                     f"Enregistrer les modifications de « {self.forme.text()} » ?"):
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
        cible = self.cible_relation.entree_choisie()
        if cible is None:
            erreur(self, "Relation", "Choisis une entrée existante dans la liste.")
            return
        try:
            if not lexique.ajouter_relation(self.projet.conn, self.entree.id, cible, self.type_relation.currentText()):
                erreur(self, "Relation", "Cette relation existe déjà.")
        except ValueError as e:
            erreur(self, "Relation", str(e))
        self._charger_liens()

    def _retirer_relation(self):
        item = self.relations.currentItem()
        if item:
            lexique.supprimer_relation(self.projet.conn, item.data(ROLE_DONNEE))
            self._charger_liens()

    def _ajouter_media(self, role):
        filtre = ("Audio (*.wav *.mp3 *.m4a *.ogg *.flac)" if role == "prononciation"
                  else "Images (*.png *.jpg *.jpeg *.gif *.bmp)")
        chemin, _ = QFileDialog.getOpenFileName(self, "Ajouter un fichier", "", filtre)
        if not chemin:
            return
        note, ok = QInputDialog.getText(self, "Note", "Note (locuteur, source, droits…) :")
        if not ok:
            return
        try:
            copie = copier_medias(self.projet, chemin)
            lexique.lier_media(self.projet.conn, self.entree.id, copie, role, note)
        except Exception as e:
            erreur(self, "Fichier", "Le fichier n'a pas pu être ajouté.", e)
            return
        self._charger_liens()

    def _apercu_media(self, item, _ancien=None):
        self.apercu.clear()
        if item and item.data(ROLE_DONNEE + 2) == "image" and os.path.isfile(item.data(ROLE_DONNEE + 1)):
            self.apercu.setPixmap(QPixmap(item.data(ROLE_DONNEE + 1)).scaled(
                self.apercu.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _lire_media(self):
        item = self.medias.currentItem()
        if not item:
            return
        chemin = item.data(ROLE_DONNEE + 1)
        if not os.path.isfile(chemin):
            erreur(self, "Fichier introuvable", f"Le fichier n'existe plus :\n{chemin}")
            return
        if item.data(ROLE_DONNEE + 2) == "prononciation":
            try:
                from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
                if self._lecteur is None:
                    self._sortie = QAudioOutput(self)
                    self._lecteur = QMediaPlayer(self)
                    self._lecteur.setAudioOutput(self._sortie)
                self._lecteur.setSource(QUrl.fromLocalFile(chemin))
                self._lecteur.play()
                return
            except Exception:
                pass  # lecture intégrée indisponible : on passe par le lecteur du système
        QDesktopServices.openUrl(QUrl.fromLocalFile(chemin))

    def _retirer_media(self):
        item = self.medias.currentItem()
        if item and confirmer(self, "Retirer", "Retirer ce fichier de l'entrée ? (il reste dans le dossier du projet)"):
            lexique.delier_media(self.projet.conn, item.data(ROLE_DONNEE))
            self._charger_liens()

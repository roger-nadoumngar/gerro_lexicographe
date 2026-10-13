"""Pages de la fenêtre principale. Chaque page a une méthode `rafraichir()` et
émet `donnees_modifiees` quand elle change le projet."""

import json
import os
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
                               QTextBrowser, QVBoxLayout, QWidget, QDialog, QDialogButtonBox)

from .. import alignement, domaines, exports, lexique, lift_import, usfm
from ..lexique import Entree, Exemple, Sens
from ..projet import copier_medias
from .commun import CurseurAttente, carte, confirmer, erreur, info, surligner, titre
from .domaines_ui import ArbreDomaines, DialogueDomaine
from .editeur_entree import EditeurEntree, police_vernaculaire, remplir_categories


class Page(QWidget):
    donnees_modifiees = Signal()

    def __init__(self, projet, titre_page, sous_titre=None):
        super().__init__()
        self.projet = projet
        self.racine = QVBoxLayout(self)
        self.racine.setContentsMargins(22, 18, 22, 18)
        t, s = titre(titre_page, sous_titre)
        self.racine.addWidget(t)
        if s:
            self.racine.addWidget(s)
        self.racine.addSpacing(8)

    def rafraichir(self):
        pass

    def peut_quitter(self):
        return True


def _item(texte, donnee=None):
    item = QTableWidgetItem(texte if texte is not None else "")
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    if donnee is not None:
        item.setData(Qt.UserRole, donnee)
    return item


def _table(colonnes, etirer=()):
    t = QTableWidget(0, len(colonnes))
    t.setHorizontalHeaderLabels(colonnes)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    t.setAlternatingRowColors(True)
    for i in range(len(colonnes)):
        t.horizontalHeader().setSectionResizeMode(
            i, QHeaderView.Stretch if i in etirer else QHeaderView.ResizeToContents)
    return t


# =============================================================================
class PageTableauDeBord(Page):
    def __init__(self, projet):
        super().__init__(projet, "Tableau de bord")
        grille = QGridLayout()
        self.chiffres = {}
        for i, (cle, libelle) in enumerate([("entrees", "entrées"), ("sens", "sens"),
                                            ("a_verifier", "entrées à vérifier"),
                                            ("sans_domaine", "sens sans domaine sémantique"),
                                            ("phrases_paralleles", "phrases parallèles"),
                                            ("en_attente", "propositions à examiner"),
                                            ("rejetees", "propositions rejetées")]):
            c = carte()
            v = QVBoxLayout(c)
            chiffre = QLabel("0")
            chiffre.setObjectName("chiffre")
            v.addWidget(chiffre)
            l = QLabel(libelle)
            l.setObjectName("sousTitre")
            v.addWidget(l)
            grille.addWidget(c, i // 4, i % 4)
            self.chiffres[cle] = chiffre
        self.racine.addLayout(grille)

        self.racine.addSpacing(14)
        self.racine.addWidget(QLabel("<b>Contradictions détectées</b>"))
        aide = QLabel("Un mot validé dont la traduction semble contredite par de nouvelles phrases. "
                      "Le score (coefficient de Dice) dépasse le seuil fixé dans les réglages du projet.")
        aide.setObjectName("sousTitre")
        aide.setWordWrap(True)
        self.racine.addWidget(aide)
        self.contradictions = QListWidget()
        self.racine.addWidget(self.contradictions, 1)
        ligne = QHBoxLayout()
        garder = QPushButton("Garder la traduction validée")
        adopter = QPushButton("Adopter la nouvelle traduction")
        garder.clicked.connect(lambda: self._resoudre(False))
        adopter.clicked.connect(lambda: self._resoudre(True))
        recalculer = QPushButton("Recalculer les propositions")
        recalculer.clicked.connect(self._recalculer)
        ligne.addWidget(garder)
        ligne.addWidget(adopter)
        ligne.addStretch()
        ligne.addWidget(recalculer)
        self.racine.addLayout(ligne)

    def rafraichir(self):
        stats = lexique.statistiques(self.projet.conn)
        for cle, label in self.chiffres.items():
            label.setText(f"{stats[cle]:,}".replace(",", " "))
        self.contradictions.clear()
        lignes = alignement.contradictions_ouvertes(self.projet)
        if not lignes:
            item = QListWidgetItem("Aucune contradiction ouverte.")
            item.setFlags(Qt.NoItemFlags)
            self.contradictions.addItem(item)
        for cid, forme, ancienne, nouvelle in lignes:
            item = QListWidgetItem(f"« {forme} » : validé comme « {ancienne} », "
                                   f"les phrases suggèrent maintenant « {nouvelle} »")
            item.setData(Qt.UserRole, cid)
            self.contradictions.addItem(item)

    def _resoudre(self, adopter):
        item = self.contradictions.currentItem()
        if not item or item.data(Qt.UserRole) is None:
            erreur(self, "Contradictions", "Sélectionne d'abord une contradiction dans la liste.")
            return
        alignement.resoudre_contradiction(self.projet, item.data(Qt.UserRole), adopter)
        self.donnees_modifiees.emit()

    def _recalculer(self):
        with CurseurAttente():
            n = alignement.recalculer(self.projet)
        self.donnees_modifiees.emit()
        if n:
            info(self, "Contradictions", f"{n} nouvelle(s) contradiction(s) détectée(s).")


# =============================================================================
class PageValidation(Page):
    def __init__(self, projet):
        super().__init__(projet, "Validation des propositions",
                         "Le moteur propose une traduction pour chaque mot du corpus parallèle. "
                         "Rien n'entre dans le lexique sans ta décision ; les phrases ci-dessous "
                         "montrent sur quoi repose la proposition.")
        self.passes = set()
        self.forme_courante = None

        tete = QHBoxLayout()
        self.forme = QLabel("—")
        self.forme.setObjectName("grandeForme")
        self.meta = QLabel("")
        self.meta.setObjectName("sousTitre")
        col = QVBoxLayout()
        col.addWidget(self.forme)
        col.addWidget(self.meta)
        tete.addLayout(col, 1)
        self.reste = QLabel("")
        self.reste.setObjectName("sousTitre")
        tete.addWidget(self.reste, 0, Qt.AlignTop)
        self.racine.addLayout(tete)

        self.candidats = QHBoxLayout()
        self.racine.addLayout(self.candidats)

        separateur = QSplitter(Qt.Horizontal)
        gauche = QWidget()
        gl = QVBoxLayout(gauche)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.addWidget(QLabel("<b>Pourquoi cette proposition ?</b>"))
        self.preuves = QTextBrowser()
        gl.addWidget(self.preuves)
        separateur.addWidget(gauche)
        self.editeur = EditeurEntree(projet, mode_validation=True)
        separateur.addWidget(self.editeur)
        separateur.setSizes([420, 560])
        self.racine.addWidget(separateur, 1)

        boutons = QHBoxLayout()
        self.btn_valider = QPushButton("✓ Valider et ajouter au lexique")
        self.btn_valider.setObjectName("principal")
        self.btn_valider.setShortcut("Ctrl+Return")
        self.btn_rejeter = QPushButton("✗ Rejeter")
        self.btn_passer = QPushButton("Passer →")
        self.btn_valider.clicked.connect(self._valider)
        self.btn_rejeter.clicked.connect(self._rejeter)
        self.btn_passer.clicked.connect(self._passer)
        boutons.addWidget(self.btn_valider)
        boutons.addWidget(self.btn_rejeter)
        boutons.addWidget(self.btn_passer)
        boutons.addStretch()
        self.racine.addLayout(boutons)

    def rafraichir(self):
        file = alignement.file_validation(self.projet, self.passes)
        if not file and self.passes:
            self.passes.clear()  # tous les mots restants ont été passés : nouveau tour
            file = alignement.file_validation(self.projet)
        self.reste.setText(f"{len(file)} proposition(s) à examiner")
        for i in reversed(range(self.candidats.count())):
            w = self.candidats.itemAt(i).widget()
            if w:
                w.deleteLater()
            self.candidats.removeItem(self.candidats.itemAt(i))
        if not file:
            self.forme_courante = None
            self.forme.setText("File terminée")
            self.meta.setText("Toutes les propositions ont été examinées.")
            self.preuves.clear()
            self.editeur.charger_entree(None)
            for b in (self.btn_valider, self.btn_rejeter, self.btn_passer):
                b.setEnabled(False)
            return
        for b in (self.btn_valider, self.btn_rejeter, self.btn_passer):
            b.setEnabled(True)
        forme, freq, candidat, score, cooc, autres = file[0]
        self.forme_courante = forme
        self.forme.setText(forme)
        self.meta.setText(f"apparaît dans {freq} phrase(s) · {cooc} avec « {candidat or '—'} » · "
                          f"Dice = {score:.2f}")
        self.candidats.addWidget(QLabel("Autres candidats :"))
        for alt in json.loads(autres or "[]"):
            b = QPushButton(alt)
            b.setObjectName("candidat")
            b.clicked.connect(lambda _=False, a=alt: self._choisir(a))
            self.candidats.addWidget(b)
        self.candidats.addStretch()
        self._afficher_preuves(candidat)

        exemples = alignement.preuves(self.projet, forme, candidat, limite=1)
        sens = Sens(glose=candidat or "")
        if exemples:
            ref, vern, analyse = exemples[0]
            sens.exemples = [Exemple(vern, analyse, ref)]
        # la décision humaine de la page Validation vaut validation de l'entrée
        self.editeur.charger_entree(Entree(forme=forme, statut="validé", sens=[sens]))

    def _afficher_preuves(self, candidat):
        lignes = alignement.preuves(self.projet, self.forme_courante, candidat)
        tv, ta = self.projet.tokeniseur_vern, self.projet.tokeniseur_analyse
        morceaux = [f"<p><i>{len(lignes)} phrase(s) contiennent les deux mots"
                    f"{' (50 premières)' if len(lignes) >= 50 else ''}.</i></p>"]
        for ref, vern, analyse in lignes:
            morceaux.append(f"<p><b>{ref}</b><br>{surligner(tv, vern, {self.forme_courante})}"
                            f"<br><span style='color:#6B6857'>{surligner(ta, analyse, {candidat})}</span></p>")
        self.preuves.setHtml("".join(morceaux))

    def _choisir(self, candidat):
        onglet = self.editeur.onglets.widget(0)
        onglet.glose.setText(candidat)
        self._afficher_preuves(candidat)

    def _valider(self):
        entree = self.editeur.valeur()
        if not entree.forme or not any(s.glose for s in entree.sens):
            erreur(self, "Validation", "Il faut au moins une forme et une glose.")
            return
        try:
            alignement.valider(self.projet, self.forme_courante, entree)
        except Exception as e:
            erreur(self, "Validation impossible", "La validation n'a pas pu être enregistrée.", e)
            return
        self.donnees_modifiees.emit()

    def _rejeter(self):
        alignement.rejeter(self.projet, self.forme_courante)
        self.donnees_modifiees.emit()

    def _passer(self):
        self.passes.add(self.forme_courante)
        self.rafraichir()


# =============================================================================
class DialogueMasse(QDialog):
    """Modification de plusieurs entrées à la fois."""

    def __init__(self, projet, nombre, parent=None):
        super().__init__(parent)
        self.projet = projet
        self.setWindowTitle("Modifier la sélection")
        self.domaine = None
        form = QFormLayout(self)
        form.addRow(QLabel(f"<b>{nombre} entrée(s) sélectionnée(s).</b> Seuls les champs choisis sont modifiés."))
        self.statut = QComboBox()
        self.statut.addItem("(ne pas changer)", None)
        for s in lexique.STATUTS:
            self.statut.addItem(s, s)
        self.categorie = QComboBox()
        remplir_categories(self.categorie, projet.conn, vide=False)
        self.categorie.insertItem(0, "(ne pas changer)", None)
        self.categorie.setCurrentIndex(0)
        self.btn_domaine = QPushButton("(ne pas ajouter)")
        self.btn_domaine.clicked.connect(self._choisir_domaine)
        form.addRow("Statut :", self.statut)
        form.addRow("Catégorie (tous les sens) :", self.categorie)
        form.addRow("Ajouter le domaine (tous les sens) :", self.btn_domaine)
        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)
        form.addRow(boutons)

    def _choisir_domaine(self):
        d = DialogueDomaine(self.projet, self)
        if d.exec() and d.guid:
            self.domaine = d.guid
            self.btn_domaine.setText(domaines.libelle(self.projet.conn, d.guid,
                                                      self.projet.reglage("langue_analyse_code") or "fr"))


class PageLexique(Page):
    def __init__(self, projet):
        super().__init__(projet, "Lexique")
        separateur = QSplitter(Qt.Horizontal)

        gauche = QWidget()
        gl = QVBoxLayout(gauche)
        gl.setContentsMargins(0, 0, 0, 0)
        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Rechercher une forme, une variante ou une glose…")
        self.recherche.setClearButtonEnabled(True)
        self.recherche.textChanged.connect(self.rafraichir)
        gl.addWidget(self.recherche)

        filtres = QHBoxLayout()
        self.f_statut = QComboBox()
        self.f_statut.addItem("tous statuts", None)
        for s in lexique.STATUTS:
            self.f_statut.addItem(s, s)
        self.f_categorie = QComboBox()
        self.f_domaine = QPushButton("tous domaines")
        self.f_domaine.setToolTip("Filtrer par domaine sémantique (sous-domaines compris). Clic droit : retirer le filtre.")
        self.f_domaine.clicked.connect(self._choisir_filtre_domaine)
        self.f_domaine.setContextMenuPolicy(Qt.CustomContextMenu)
        self.f_domaine.customContextMenuRequested.connect(lambda _: self._choisir_filtre_domaine(effacer=True))
        self.filtre_domaine = None
        for w in (self.f_statut, self.f_categorie):
            w.currentIndexChanged.connect(self.rafraichir)
            filtres.addWidget(w, 1)
        filtres.addWidget(self.f_domaine, 1)
        gl.addLayout(filtres)

        self.liste = _table(["Vedette", "Glose(s)", "Catégorie", "Statut"], etirer=(1,))
        self.liste.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.liste.itemSelectionChanged.connect(self._selection)
        gl.addWidget(self.liste)
        bas = QHBoxLayout()
        nouvelle = QPushButton("+ Nouvelle entrée")
        nouvelle.clicked.connect(self._nouvelle)
        self.btn_masse = QPushButton("Modifier la sélection…")
        self.btn_masse.clicked.connect(self._modifier_en_masse)
        importer = QPushButton("Importer LIFT…")
        importer.setToolTip("Reprendre un lexique FLEx ou WeSay (fichier .lift)")
        importer.clicked.connect(self._importer_lift)
        bas.addWidget(nouvelle)
        bas.addWidget(self.btn_masse)
        bas.addWidget(importer)
        bas.addStretch()
        gl.addLayout(bas)
        self.compte = QLabel("")
        self.compte.setObjectName("sousTitre")
        gl.addWidget(self.compte)
        separateur.addWidget(gauche)

        self.editeur = EditeurEntree(projet)
        self.editeur.enregistree.connect(self._enregistree)
        self.editeur.supprimee.connect(self.donnees_modifiees)
        self.editeur.ouvrir_demande.connect(self.ouvrir_entree)
        separateur.addWidget(self.editeur)
        separateur.setSizes([340, 720])
        self.racine.addWidget(separateur, 1)
        self._selection_en_cours = False
        self._remplir_filtre_categories()

    def _remplir_filtre_categories(self):
        courant = self.f_categorie.currentData()
        self.f_categorie.blockSignals(True)
        remplir_categories(self.f_categorie, self.projet.conn, vide=False)
        self.f_categorie.insertItem(0, "toutes catégories", None)
        i = self.f_categorie.findData(courant)
        self.f_categorie.setCurrentIndex(i if i >= 0 else 0)
        self.f_categorie.blockSignals(False)

    def _choisir_filtre_domaine(self, effacer=False):
        if effacer:
            self.filtre_domaine = None
            self.f_domaine.setText("tous domaines")
        else:
            d = DialogueDomaine(self.projet, self)
            if not (d.exec() and d.guid):
                return
            self.filtre_domaine = self.projet.conn.execute("SELECT code FROM domaines WHERE guid=?",
                                                           (d.guid,)).fetchone()[0]
            self.f_domaine.setText(domaines.libelle(self.projet.conn, d.guid,
                                                    self.projet.reglage("langue_analyse_code") or "fr"))
        self.rafraichir()

    def rafraichir(self):
        self._remplir_filtre_categories()
        courant = self.editeur.entree.id
        lignes = lexique.lister_entrees(self.projet.conn, self.recherche.text(), statut=self.f_statut.currentData(),
                                        categorie_id=self.f_categorie.currentData(), domaine_code=self.filtre_domaine)
        police = police_vernaculaire(self.projet)
        self._selection_en_cours = True
        self.liste.setRowCount(len(lignes))
        for r, l in enumerate(lignes):
            vedette = _item(lexique.vedette(l.tete, l.homographe), l.id)
            if police:
                vedette.setFont(police)
            self.liste.setItem(r, 0, vedette)
            self.liste.setItem(r, 1, _item(l.gloses))
            self.liste.setItem(r, 2, _item(l.categories))
            self.liste.setItem(r, 3, _item(l.statut))
            if l.id == courant:
                self.liste.selectRow(r)
        self._selection_en_cours = False
        total = self.projet.conn.execute("SELECT COUNT(*) FROM entrees").fetchone()[0]
        self.compte.setText(f"{len(lignes)} / {total} entrées")
        if courant and not self.editeur.modifiee:
            if lexique.lire_entree(self.projet.conn, courant):
                self.editeur.charger_entree(lexique.lire_entree(self.projet.conn, courant), lignes=None)
            else:
                self.editeur.charger_entree(None)

    def ids_selectionnes(self):
        return [self.liste.item(i.row(), 0).data(Qt.UserRole) for i in self.liste.selectionModel().selectedRows()]

    def _selection(self):
        if self._selection_en_cours:
            return
        ids = self.ids_selectionnes()
        self.btn_masse.setEnabled(len(ids) > 1)
        if len(ids) != 1 or ids[0] == self.editeur.entree.id:
            return
        if not self.editeur.demander_si_modifiee():
            return
        self.editeur.charger(ids[0])

    def _nouvelle(self):
        if not self.editeur.demander_si_modifiee():
            return
        self.liste.clearSelection()
        self.editeur.charger_entree(Entree(sens=[Sens()]))
        self.editeur.forme.setFocus()

    def _modifier_en_masse(self):
        ids = self.ids_selectionnes()
        if len(ids) < 2:
            erreur(self, "Modifier la sélection", "Sélectionne plusieurs entrées (Ctrl+clic ou Maj+clic).")
            return
        d = DialogueMasse(self.projet, len(ids), self)
        if not d.exec():
            return
        if d.statut.currentData() is None and d.categorie.currentData() is None and d.domaine is None:
            return
        lexique.modifier_en_masse(self.projet.conn, ids, statut=d.statut.currentData(),
                                  categorie_id=d.categorie.currentData(), ajouter_domaine=d.domaine)
        self.donnees_modifiees.emit()

    def _importer_lift(self):
        chemin, _ = QFileDialog.getOpenFileName(self, "Importer un lexique LIFT", "", "LIFT (*.lift)")
        if not chemin:
            return
        if not confirmer(self, "Importer LIFT",
                         "Les entrées du fichier seront ajoutées au projet ; celles qui existent déjà (même "
                         "identifiant) seront mises à jour. Une sauvegarde du projet est faite avant. Continuer ?"):
            return
        try:
            self.projet.sauvegarde_automatique()
            with CurseurAttente():
                rapport = lift_import.importer(self.projet, chemin)
        except Exception as e:
            erreur(self, "Import LIFT", "Le fichier n'a pas pu être importé.", e)
            return
        self.donnees_modifiees.emit()
        info(self, "Import LIFT", rapport.resume())

    def _enregistree(self, _eid):
        self.donnees_modifiees.emit()

    def ouvrir_entree(self, eid):
        if self.editeur.demander_si_modifiee():
            self.recherche.clear()
            self.f_statut.setCurrentIndex(0)
            self.f_categorie.setCurrentIndex(0)
            self._choisir_filtre_domaine(effacer=True)
            self.editeur.charger(eid)
            self.rafraichir()

    def peut_quitter(self):
        return self.editeur.demander_si_modifiee()


# =============================================================================
class PageDomaines(Page):
    """Le lexique classé par domaine sémantique (vue « dictionnaire thématique »)."""
    ouvrir_entree = Signal(int)

    def __init__(self, projet):
        super().__init__(projet, "Domaines sémantiques",
                         "Liste officielle de SIL. Les questions de chaque domaine aident à collecter le "
                         "vocabulaire de façon systématique ; à droite, les mots déjà classés.")
        separateur = QSplitter(Qt.Horizontal)
        self.arbre = ArbreDomaines(projet)
        self.arbre.selection_changee.connect(self._afficher_mots)
        separateur.addWidget(self.arbre)
        droite = QWidget()
        dl = QVBoxLayout(droite)
        dl.setContentsMargins(0, 0, 0, 0)
        self.titre_mots = QLabel("<b>Mots classés dans ce domaine</b>")
        dl.addWidget(self.titre_mots)
        self.mots = _table(["Forme", "Glose"], etirer=(1,))
        self.mots.itemDoubleClicked.connect(lambda item: self.ouvrir_entree.emit(
            self.mots.item(item.row(), 0).data(Qt.UserRole)))
        dl.addWidget(self.mots, 1)
        separateur.addWidget(droite)
        separateur.setSizes([700, 300])
        self.racine.addWidget(separateur, 1)
        ligne = QHBoxLayout()
        self.etat = QLabel("")
        self.etat.setObjectName("sousTitre")
        importer = QPushButton("Importer une liste de domaines…")
        importer.setToolTip("Fichier SemDom.xml ou LocalizedLists-xx.zip de FLEx")
        importer.clicked.connect(self._importer)
        ligne.addWidget(self.etat)
        ligne.addStretch()
        ligne.addWidget(importer)
        self.racine.addLayout(ligne)

    def rafraichir(self):
        n = domaines.nombre(self.projet.conn)
        if n != len(self.arbre.items):
            self.arbre.charger()
        self.etat.setText(f"{n} domaine(s) dans le projet")
        guid = self.arbre.guid_courant()
        if guid:
            self._afficher_mots(guid)

    def _afficher_mots(self, guid):
        lignes = domaines.sens_du_domaine(self.projet.conn, guid)
        self.titre_mots.setText(f"<b>Mots classés dans ce domaine : {len(lignes)}</b>")
        self.mots.setRowCount(len(lignes))
        for r, (eid, forme, glose) in enumerate(lignes):
            self.mots.setItem(r, 0, _item(forme, eid))
            self.mots.setItem(r, 1, _item(glose))

    def _importer(self):
        chemin, _ = QFileDialog.getOpenFileName(self, "Liste de domaines", "",
                                                "Listes FLEx (*.xml *.zip);;Tous (*)")
        if not chemin:
            return
        try:
            with CurseurAttente():
                n = domaines.importer(self.projet.conn, domaines.lire_liste(chemin))
        except Exception as e:
            erreur(self, "Domaines", "La liste n'a pas pu être lue.", e)
            return
        self.arbre.charger()
        self.donnees_modifiees.emit()
        info(self, "Domaines", f"{n} domaines importés.")


# =============================================================================
class PageIndexInverse(Page):
    """Index inverse : de la langue d'analyse vers la langue documentée."""
    ouvrir_entree = Signal(int)

    def __init__(self, projet):
        super().__init__(projet, "Index inverse",
                         "Chaque sens apparaît sous les formes de son champ « Index inverse » (ou, s'il est "
                         "vide, sous sa glose). C'est la partie « français → langue » du dictionnaire.")
        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Rechercher dans l'index…")
        self.recherche.setClearButtonEnabled(True)
        self.recherche.textChanged.connect(self.rafraichir)
        self.racine.addWidget(self.recherche)
        self.table = _table(["Index", "Entrée", "Glose", "Catégorie"], etirer=(0, 2))
        self.table.itemDoubleClicked.connect(lambda item: self.ouvrir_entree.emit(
            self.table.item(item.row(), 1).data(Qt.UserRole)))
        self.racine.addWidget(self.table, 1)
        self.compte = QLabel("")
        self.compte.setObjectName("sousTitre")
        self.racine.addWidget(self.compte)

    def rafraichir(self):
        index = lexique.index_inverse(self.projet.conn, self.recherche.text())
        lignes = [(mot, eid, vedette, glose, cat) for mot, entrees in index for eid, vedette, glose, cat in entrees]
        self.table.setRowCount(len(lignes))
        police = police_vernaculaire(self.projet)
        precedent = None
        for r, (mot, eid, vedette, glose, cat) in enumerate(lignes):
            self.table.setItem(r, 0, _item(mot if mot != precedent else ""))
            item = _item(vedette, eid)
            if police:
                item.setFont(police)
            self.table.setItem(r, 1, item)
            self.table.setItem(r, 2, _item(glose))
            self.table.setItem(r, 3, _item(cat))
            precedent = mot
        self.compte.setText(f"{len(index)} forme(s) d'index, {len(lignes)} renvoi(s)")


# =============================================================================
class PageCorpus(Page):
    def __init__(self, projet):
        super().__init__(projet, "Corpus",
                         "Phrases parallèles (langue documentée / langue d'analyse) exploitées par le moteur "
                         "de propositions. Les textes importés ne modifient jamais leurs fichiers d'origine.")
        outils = QHBoxLayout()
        for texte, action in [("Importer USFM / SFM…", self._importer_usfm),
                              ("Lire un document Word / PDF…", self._lire_document),
                              ("Ajouter un enregistrement audio…", self._importer_audio)]:
            b = QPushButton(texte)
            b.clicked.connect(action)
            outils.addWidget(b)
        outils.addStretch()
        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Filtrer (référence ou texte)…")
        self.recherche.setClearButtonEnabled(True)
        self.recherche.textChanged.connect(self.rafraichir)
        outils.addWidget(self.recherche)
        self.racine.addLayout(outils)

        self.table = _table(["Référence", "Langue documentée", "Traduction", "Source"], etirer=(1, 2))
        self.table.setWordWrap(True)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.racine.addWidget(self.table, 1)
        ligne = QHBoxLayout()
        self.compte = QLabel("")
        self.compte.setObjectName("sousTitre")
        supprimer = QPushButton("Supprimer les phrases sélectionnées")
        supprimer.clicked.connect(self._supprimer)
        ligne.addWidget(self.compte)
        ligne.addStretch()
        ligne.addWidget(supprimer)
        self.racine.addLayout(ligne)

        boite = carte()
        bl = QGridLayout(boite)
        bl.addWidget(QLabel("<b>Ajouter une phrase</b>"), 0, 0, 1, 2)
        self.lbl_vern = QLabel()
        self.lbl_analyse = QLabel()
        self.nouvelle_vern = QPlainTextEdit()
        self.nouvelle_analyse = QPlainTextEdit()
        for w in (self.nouvelle_vern, self.nouvelle_analyse):
            w.setFixedHeight(54)
        bl.addWidget(self.lbl_vern, 1, 0)
        bl.addWidget(self.nouvelle_vern, 1, 1)
        bl.addWidget(self.lbl_analyse, 2, 0)
        bl.addWidget(self.nouvelle_analyse, 2, 1)
        ajouter = QPushButton("Ajouter et recalculer les propositions")
        ajouter.setObjectName("principal")
        ajouter.clicked.connect(self._ajouter)
        bl.addWidget(ajouter, 3, 1, Qt.AlignLeft)
        self.racine.addWidget(boite)

    def rafraichir(self):
        self.lbl_vern.setText(f"{self.projet.reglage('langue_vern_nom') or 'Langue'} :")
        self.lbl_analyse.setText(f"{self.projet.reglage('langue_analyse_nom') or 'Traduction'} :")
        filtre = f"%{self.recherche.text().strip()}%"
        lignes = self.projet.conn.execute(
            """SELECT ref, vernaculaire, analyse, source FROM phrases
               WHERE ref LIKE ? OR vernaculaire LIKE ? OR analyse LIKE ?""", (filtre, filtre, filtre)).fetchall()
        # phrases saisies à la main d'abord (les plus récentes en tête), puis ordre canonique
        manuelles = sorted((l for l in lignes if l[3] == "saisie_manuelle"), key=lambda l: l[0], reverse=True)
        autres = sorted((l for l in lignes if l[3] != "saisie_manuelle"), key=lambda l: usfm.cle_reference(l[0]))
        lignes = (manuelles + autres)[:2000]
        self.table.setRowCount(len(lignes))
        for r, ligne in enumerate(lignes):
            for c, valeur in enumerate(ligne):
                self.table.setItem(r, c, _item(valeur, ligne[0] if c == 0 else None))
        total = self.projet.conn.execute("SELECT COUNT(*) FROM phrases").fetchone()[0]
        self.compte.setText(f"{len(lignes)} affichée(s) sur {total}" + (" (2000 au plus)" if len(lignes) == 2000 else ""))

    def _recalculer_et_signaler(self):
        with CurseurAttente():
            n = alignement.recalculer(self.projet)
        self.donnees_modifiees.emit()
        return n

    def _ajouter(self):
        vern = self.nouvelle_vern.toPlainText().strip()
        analyse = self.nouvelle_analyse.toPlainText().strip()
        if not vern or not analyse:
            erreur(self, "Phrase incomplète", "Remplis la phrase et sa traduction.")
            return
        alignement.ajouter_phrase(self.projet, vern, analyse)
        self.nouvelle_vern.clear()
        self.nouvelle_analyse.clear()
        n = self._recalculer_et_signaler()
        if n:
            info(self, "Contradictions", f"{n} nouvelle(s) contradiction(s) — voir le tableau de bord.")

    def _supprimer(self):
        refs = sorted({self.table.item(i.row(), 0).data(Qt.UserRole)
                       for i in self.table.selectionModel().selectedRows()})
        if not refs or not confirmer(self, "Supprimer", f"Supprimer {len(refs)} phrase(s) du corpus ?"):
            return
        with self.projet.conn:
            self.projet.conn.executemany("DELETE FROM phrases WHERE ref=?", [(r,) for r in refs])
        self._recalculer_et_signaler()

    def _importer_usfm(self):
        chemin, _ = QFileDialog.getOpenFileName(self, "Fichier USFM", "", "USFM / SFM (*.usfm *.sfm *.SFM *.ptx *.txt);;Tous (*)")
        if not chemin:
            return
        langues = [f"{self.projet.reglage('langue_vern_nom') or 'langue documentée'} (langue du projet)",
                   f"{self.projet.reglage('langue_analyse_nom') or 'langue d analyse'} (traduction)"]
        choix, ok = QInputDialog.getItem(self, "Langue du fichier", "Ce fichier est en :", langues, 0, False)
        if not ok:
            return
        try:
            versets, code = usfm.lire_usfm(chemin)
            nouveaux, completes = usfm.importer(self.projet, versets,
                                                "vernaculaire" if choix == langues[0] else "analyse",
                                                os.path.basename(chemin))
        except Exception as e:
            erreur(self, "Import USFM", "Le fichier n'a pas pu être importé.", e)
            return
        self._recalculer_et_signaler()
        info(self, "Import USFM", f"Livre {code} : {len(versets)} versets ({nouveaux} nouveaux, {completes} complétés).")

    def _lire_document(self):
        chemin, _ = QFileDialog.getOpenFileName(self, "Document", "", "Word ou PDF (*.docx *.pdf)")
        if not chemin:
            return
        try:
            if chemin.lower().endswith(".docx"):
                from docx import Document
                texte = "\n".join(p.text for p in Document(chemin).paragraphs if p.text.strip())
            else:
                from pypdf import PdfReader
                texte = "\n\n".join(page.extract_text() or "" for page in PdfReader(chemin).pages)
        except ImportError:
            erreur(self, "Bibliothèque manquante",
                   "Pour lire ce type de document, installe la bibliothèque :\n\npip install python-docx pypdf")
            return
        except Exception as e:
            erreur(self, "Lecture impossible", "Le document n'a pas pu être lu.", e)
            return
        d = QDialog(self)
        d.setWindowTitle(os.path.basename(chemin))
        d.resize(720, 560)
        v = QVBoxLayout(d)
        v.addWidget(QLabel("Texte extrait (lecture seule). Copie les phrases utiles dans « Ajouter une phrase »."))
        zone = QPlainTextEdit(texte)
        zone.setReadOnly(True)
        v.addWidget(zone)
        b = QDialogButtonBox(QDialogButtonBox.Close)
        b.rejected.connect(d.reject)
        v.addWidget(b)
        d.exec()

    def _importer_audio(self):
        chemin, _ = QFileDialog.getOpenFileName(self, "Enregistrement audio", "",
                                                "Audio (*.wav *.mp3 *.m4a *.ogg *.flac);;Tous (*)")
        if not chemin:
            return
        note, ok = QInputDialog.getText(self, "Note", "Note sur l'enregistrement (locuteur, lieu, contexte) :")
        if not ok:
            return
        try:
            destination = copier_medias(self.projet, chemin)
            with self.projet.conn:
                self.projet.conn.execute("INSERT INTO medias (nom_fichier, chemin, note, date_ajout) VALUES (?,?,?,?)",
                                         (os.path.basename(destination), destination, note,
                                          datetime.now().isoformat(timespec="seconds")))
        except Exception as e:
            erreur(self, "Import audio", "L'enregistrement n'a pas pu être ajouté.", e)
            return
        info(self, "Import audio", f"Enregistrement copié dans le dossier du projet :\n{destination}")


# =============================================================================
class PageExports(Page):
    FORMATS = [
        ("LIFT (FLEx, WeSay, Dictionary App Builder)", "lift", "LIFT (*.lift)", exports.exporter_lift,
         "Format d'échange de SIL : s'importe dans FLEx et WeSay, et sert de source à Dictionary App "
         "Builder pour créer une application Android."),
        ("JSON", "json", "JSON (*.json)", exports.exporter_json, "Données complètes, pour d'autres programmes."),
        ("CSV (Excel, LibreOffice)", "csv", "CSV (*.csv)", exports.exporter_csv, "Une ligne par sens."),
        ("Texte imprimable", "txt", "Texte (*.txt)", exports.exporter_texte, "Liste lisible des entrées."),
    ]

    def __init__(self, projet):
        super().__init__(projet, "Exports", "Le dictionnaire imprimé mis en page (PDF / Word) et la préparation "
                                            "complète d'applications Android arrivent en phase 5.")
        for nom, extension, filtre, fonction, aide in self.FORMATS:
            c = carte()
            h = QHBoxLayout(c)
            v = QVBoxLayout()
            v.addWidget(QLabel(f"<b>{nom}</b>"))
            a = QLabel(aide)
            a.setObjectName("sousTitre")
            a.setWordWrap(True)
            v.addWidget(a)
            h.addLayout(v, 1)
            b = QPushButton("Exporter…")
            b.clicked.connect(lambda _=False, e=extension, f=filtre, fn=fonction: self._exporter(e, f, fn))
            h.addWidget(b)
            self.racine.addWidget(c)
        self.racine.addStretch()

    def _exporter(self, extension, filtre, fonction):
        nom = f"{self.projet.nom}.{extension}"
        chemin, _ = QFileDialog.getSaveFileName(self, "Exporter", nom, filtre)
        if not chemin:
            return
        try:
            n = fonction(self.projet, chemin)
        except Exception as e:
            erreur(self, "Export impossible", "Le fichier n'a pas pu être écrit.", e)
            return
        info(self, "Export terminé", f"{n} entrée(s) exportée(s) vers :\n{chemin}")

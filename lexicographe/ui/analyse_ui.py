"""Composants de l'analyse de textes : affichage interlinéaire en flux, panneau
d'analyse d'un mot, création rapide d'entrée."""


from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QLayout, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from .. import interlineaire as il
from .. import lexique
from ..lexique import Entree, Sens
from ..morphologie import MARQUES
from ..texte import normaliser
from .commun import BORDURE, DISCRET, SARCELLE, erreur
from .editeur_entree import remplir_categories

COULEURS_STATUT = {il.VALIDEE: "#1F5B57", il.PROPOSEE: "#8A6D1F", il.AMBIGUE: "#9C4A1A", il.INCONNUE: "#9A9583"}
LIBELLES_STATUT = {il.VALIDEE: "analyse validée", il.PROPOSEE: "proposition unique de l'analyseur (à valider)",
                   il.AMBIGUE: "plusieurs découpes possibles : à choisir", il.INCONNUE: "aucune analyse"}


class DispositionFlux(QLayout):
    """Place les widgets de gauche à droite et passe à la ligne quand la place manque."""

    def __init__(self, parent=None, espacement=10):
        super().__init__(parent)
        self._items = []
        self._esp = espacement

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, largeur):
        return self._disposer(QRect(0, 0, largeur, 0), simuler=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._disposer(rect, simuler=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        taille = QSize()
        for item in self._items:
            taille = taille.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return taille + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _disposer(self, rect, simuler):
        m = self.contentsMargins()
        x, y = rect.x() + m.left(), rect.y() + m.top()
        droite = rect.right() - m.right()
        hauteur_ligne = 0
        for item in self._items:
            taille = item.sizeHint()
            if x + taille.width() > droite and hauteur_ligne > 0:
                x = rect.x() + m.left()
                y += hauteur_ligne + self._esp
                hauteur_ligne = 0
            if not simuler:
                item.setGeometry(QRect(QPoint(x, y), taille))
            x += taille.width() + self._esp
            hauteur_ligne = max(hauteur_ligne, taille.height())
        return y + hauteur_ligne - rect.y() + m.bottom()


class BlocMot(QFrame):
    """Un mot de l'interlinéaire : forme, morphèmes, gloses, catégories, glose du mot."""
    clique = Signal(object)

    def __init__(self, mot: il.MotInterlineaire, parent=None):
        super().__init__(parent)
        self.mot = mot
        self.setCursor(Qt.PointingHandCursor)
        couleur = COULEURS_STATUT[mot.statut]
        self.setToolTip(LIBELLES_STATUT[mot.statut])
        self._style(False)
        grille = QGridLayout(self)
        grille.setContentsMargins(6, 4, 6, 4)
        grille.setSpacing(1)
        # polices fixées par setFont (et non par feuille de style) : la taille du bloc est alors exacte
        police_tete = QFont(self.font())
        police_tete.setPointSizeF(police_tete.pointSizeF() * 1.25)
        police_tete.setBold(True)
        police_petite = QFont(self.font())
        police_petite.setPointSizeF(police_petite.pointSizeF() * 0.85)
        tete = QLabel(mot.texte)
        tete.setFont(police_tete)
        grille.addWidget(tete, 0, 0, 1, max(1, len(mot.analyse.morphemes) if mot.analyse else 1))
        style_ligne = f"color: {couleur};" + (" font-style: italic;" if mot.statut == il.PROPOSEE else "")
        if mot.analyse:
            for col, m in enumerate(mot.analyse.morphemes):
                for ligne, texte in ((1, m.forme), (2, m.glose or "?"), (3, m.categorie or "")):
                    l = QLabel(texte)
                    l.setStyleSheet(style_ligne)
                    if ligne > 1:
                        l.setFont(police_petite)
                    grille.addWidget(l, ligne, col)
            if mot.analyse.glose_mot:
                l = QLabel(f"‘{mot.analyse.glose_mot}’")
                l.setStyleSheet(f"color: {DISCRET};")
                grille.addWidget(l, 4, 0, 1, len(mot.analyse.morphemes))
        else:
            texte = f"{mot.possibilites} découpes" if mot.statut == il.AMBIGUE else "—"
            l = QLabel(texte)
            l.setStyleSheet(style_ligne)
            l.setFont(police_petite)
            grille.addWidget(l, 1, 0)
        # la taille doit tenir compte des polices du style avant la mise en page en flux,
        # sinon les blocs se chevauchent
        for enfant in self.findChildren(QLabel):
            enfant.setTextFormat(Qt.PlainText)
            enfant.ensurePolished()
        self.ensurePolished()
        grille.activate()
        self.setFixedSize(self.sizeHint())

    def _style(self, actif):
        bord = SARCELLE if actif else BORDURE
        fond = "#EAF2F1" if actif else "white"
        self.setStyleSheet(f"BlocMot {{ background: {fond}; border: 1px solid {bord}; border-radius: 4px; }}")

    def selectionner(self, actif):
        self._style(actif)

    def mousePressEvent(self, event):
        self.clique.emit(self)
        super().mousePressEvent(event)


class VueInterlineaire(QWidget):
    """Les blocs de mots d'une phrase, en flux."""
    mot_choisi = Signal(object)   # MotInterlineaire

    def __init__(self, parent=None):
        super().__init__(parent)
        self.flux = DispositionFlux(self)
        self.blocs = []
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

    def afficher(self, mots):
        for b in self.blocs:
            self.flux.removeWidget(b)
            b.hide()          # deleteLater est différé : sans hide(), l'ancien bloc reste affiché un moment
            b.deleteLater()
        self.blocs = []
        for mot in mots:
            b = BlocMot(mot, self)
            b.clique.connect(self._clic)
            self.flux.addWidget(b)
            self.blocs.append(b)
        self.updateGeometry()

    def _clic(self, bloc):
        for b in self.blocs:
            b.selectionner(b is bloc)
        self.mot_choisi.emit(bloc.mot)

    def selectionner_position(self, position):
        for b in self.blocs:
            if b.mot.position == position:
                self._clic(b)
                return


class DialogueEntreeRapide(QDialog):
    """Création rapide d'une entrée (radical ou affixe) depuis l'analyse."""

    def __init__(self, projet, forme="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nouvelle entrée")
        self.projet = projet
        self.entree_id = None
        form = QFormLayout(self)
        self.forme = QLineEdit(forme)
        self.type_morph = QComboBox()
        self.type_morph.addItem("", "")
        for cle, libelle in lexique.TYPES_MORPH.items():
            self.type_morph.addItem(libelle, cle)
        self.type_morph.setCurrentIndex(self.type_morph.findData("stem"))
        self.glose = QLineEdit()
        self.categorie = QComboBox()
        remplir_categories(self.categorie, projet.conn)
        aide = QLabel("Pour un affixe, choisis préfixe, suffixe ou clitique : l'analyseur s'en servira pour "
                      "découper les mots. Tu peux noter la frontière dans la forme (« ka- », « -je », « =g »).")
        aide.setWordWrap(True)
        aide.setObjectName("sousTitre")
        form.addRow("Forme :", self.forme)
        form.addRow("Type :", self.type_morph)
        form.addRow("Glose :", self.glose)
        form.addRow("Catégorie :", self.categorie)
        form.addRow(aide)
        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        boutons.accepted.connect(self._accepter)
        boutons.rejected.connect(self.reject)
        form.addRow(boutons)
        self.glose.setFocus()

    def _accepter(self):
        if not self.forme.text().strip() or not self.glose.text().strip():
            erreur(self, "Nouvelle entrée", "Indique la forme et la glose.")
            return
        self.entree_id = lexique.enregistrer_entree(self.projet.conn, Entree(
            forme=self.forme.text().strip(), type_morph=self.type_morph.currentData() or "", statut="brouillon",
            sens=[Sens(glose=self.glose.text().strip(), categorie_id=self.categorie.currentData())]))
        self.accept()


class PanneauAnalyse(QWidget):
    """Analyse d'une forme de mot : analyses validées, découpes proposées par
    l'analyseur, segmentation manuelle reliée au lexique."""
    analyse_modifiee = Signal()

    def __init__(self, projet, parent=None):
        super().__init__(parent)
        self.projet = projet
        self.forme = None
        self.ref = None
        self.position = None
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.titre = QLabel("Clique sur un mot pour l'analyser.")
        self.titre.setStyleSheet("font-size: 15px; font-weight: 600;")
        v.addWidget(self.titre)
        self.etat = QLabel("")
        self.etat.setObjectName("sousTitre")
        self.etat.setWordWrap(True)
        v.addWidget(self.etat)

        colonnes = QHBoxLayout()
        gauche = QVBoxLayout()
        gauche.addWidget(QLabel("<b>Analyses validées</b>"))
        self.validees = QListWidget()
        self.validees.setMaximumHeight(110)
        gauche.addWidget(self.validees)
        ligne = QHBoxLayout()
        self.btn_occurrence = QPushButton("Pour cette occurrence seulement")
        self.btn_occurrence.setToolTip("Mot ambigu : utiliser l'analyse sélectionnée ici, et seulement ici")
        self.btn_occurrence.clicked.connect(self._pour_occurrence)
        self.btn_supprimer = QPushButton("Supprimer")
        self.btn_supprimer.clicked.connect(self._supprimer)
        ligne.addWidget(self.btn_occurrence)
        ligne.addWidget(self.btn_supprimer)
        ligne.addStretch()
        gauche.addLayout(ligne)
        colonnes.addLayout(gauche, 1)

        droite = QVBoxLayout()
        droite.addWidget(QLabel("<b>Découpes trouvées par l'analyseur</b>"))
        self.propositions = QListWidget()
        self.propositions.setMaximumHeight(110)
        self.propositions.itemDoubleClicked.connect(lambda _: self._valider_proposition())
        droite.addWidget(self.propositions)
        ligne = QHBoxLayout()
        b = QPushButton("Valider la découpe sélectionnée")
        b.setObjectName("principal")
        b.clicked.connect(self._valider_proposition)
        ligne.addWidget(b)
        ligne.addStretch()
        droite.addLayout(ligne)
        colonnes.addLayout(droite, 1)
        v.addLayout(colonnes)

        manuel = QHBoxLayout()
        manuel.addWidget(QLabel("Découpe manuelle :"))
        self.segmentation = QLineEdit()
        self.segmentation.setPlaceholderText("morphèmes séparés par des tirets, ex. : kó-je")
        self.segmentation.textChanged.connect(self._preparer_manuel)
        manuel.addWidget(self.segmentation, 1)
        self.glose_mot = QLineEdit()
        self.glose_mot.setPlaceholderText("glose du mot (facultatif)")
        manuel.addWidget(self.glose_mot, 1)
        v.addLayout(manuel)
        self.zone_morphemes = QHBoxLayout()
        v.addLayout(self.zone_morphemes)
        ligne = QHBoxLayout()
        b = QPushButton("Valider la découpe manuelle")
        b.clicked.connect(self._valider_manuel)
        nouvelle = QPushButton("Créer une entrée…")
        nouvelle.setToolTip("Ajouter au lexique un radical ou un affixe qui manque")
        nouvelle.clicked.connect(self._creer_entree)
        ligne.addWidget(b)
        ligne.addWidget(nouvelle)
        ligne.addStretch()
        v.addLayout(ligne)
        self.combos = []
        self.setEnabled(False)

    def afficher(self, forme, ref=None, position=None):
        self.forme, self.ref, self.position = normaliser(forme).lower(), ref, position
        self.setEnabled(True)
        self.rafraichir()

    def rafraichir(self):
        if not self.forme:
            return
        ctx = il.Contexte(self.projet)
        statut, _, _ = ctx.statut(self.forme)
        self.titre.setText(self.forme)
        self.etat.setText(LIBELLES_STATUT[statut].capitalize())
        self.validees.clear()
        for a in ctx.analyses(self.forme):
            item = QListWidgetItem(f"{a.segmentation}   « {a.gloses} »" + (f"   ‘{a.glose_mot}’" if a.glose_mot else ""))
            item.setData(Qt.UserRole, a.id)
            self.validees.addItem(item)
        self.btn_occurrence.setEnabled(self.ref is not None and self.validees.count() > 1)
        self.propositions.clear()
        self._decompositions = ctx.decompositions(self.forme)
        for i, d in enumerate(self._decompositions):
            envs = [m.environnement for m in d.morphemes if m.environnement]
            texte = f"{d.segmentation}   « {d.gloses} »" + (f"   (allomorphe : {'; '.join(envs)})" if envs else "")
            item = QListWidgetItem(texte)
            item.setData(Qt.UserRole, i)
            self.propositions.addItem(item)
        if self._decompositions:
            self.propositions.setCurrentRow(0)
        self.segmentation.setText(self._decompositions[0].segmentation if self._decompositions else self.forme)

    def _preparer_manuel(self, texte):
        for c in self.combos:
            self.zone_morphemes.removeWidget(c)
            c.deleteLater()
        self.combos = []
        index = {}
        for eid, forme, citation in self.projet.conn.execute("SELECT id, forme, forme_citation FROM entrees"):
            for f in (forme, citation):
                if f:
                    index.setdefault(normaliser(f).strip(MARQUES).lower(), []).append(eid)
        for morceau in [m for m in texte.split("-") if m.strip()]:
            combo = QComboBox()
            combo.addItem(f"{morceau} (non relié)", None)
            for eid in dict.fromkeys(index.get(normaliser(morceau).lower(), [])):
                combo.addItem(lexique.libelle_entree(self.projet.conn, eid), eid)
            if combo.count() > 1:
                combo.setCurrentIndex(1)
            combo.setProperty("morceau", morceau)
            self.zone_morphemes.addWidget(combo)
            self.combos.append(combo)

    def _valider(self, analyse):
        try:
            aid = il.valider(self.projet.conn, analyse)
        except ValueError as e:
            erreur(self, "Analyse", str(e))
            return None
        self.rafraichir()
        self.analyse_modifiee.emit()
        return aid

    def _valider_proposition(self):
        item = self.propositions.currentItem()
        if not item:
            return
        analyse = il.depuis_decomposition(self.forme, self._decompositions[item.data(Qt.UserRole)])
        analyse.glose_mot = self.glose_mot.text().strip()
        self._valider(analyse)

    def _valider_manuel(self):
        morphemes = []
        for c in self.combos:
            eid = c.currentData()
            sid = None
            if eid:
                ligne = self.projet.conn.execute("SELECT id FROM sens WHERE entree_id=? ORDER BY ordre, id LIMIT 1",
                                                 (eid,)).fetchone()
                sid = ligne[0] if ligne else None
            morphemes.append(il.MorphemeAnalyse(normaliser(c.property("morceau")).lower(), eid, sid))
        if not morphemes:
            return
        self._valider(il.Analyse(self.forme, morphemes, self.glose_mot.text().strip()))

    def _pour_occurrence(self):
        item = self.validees.currentItem()
        if item and self.ref is not None:
            il.choisir_pour_occurrence(self.projet.conn, self.ref, self.position, item.data(Qt.UserRole))
            self.analyse_modifiee.emit()

    def _supprimer(self):
        item = self.validees.currentItem()
        if item:
            il.supprimer(self.projet.conn, item.data(Qt.UserRole))
            self.rafraichir()
            self.analyse_modifiee.emit()

    def _creer_entree(self):
        selection = self.segmentation.text().split("-")
        d = DialogueEntreeRapide(self.projet, selection[0] if len(selection) == 1 else "", self)
        if d.exec():
            self.rafraichir()
            self.analyse_modifiee.emit()

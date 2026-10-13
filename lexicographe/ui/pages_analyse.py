"""Pages de la phase 2 : textes (interlinéaire), formes de mots, concordance."""

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QScrollArea,
                               QSplitter, QVBoxLayout, QWidget)

from .. import interlineaire as il
from .. import textes
from ..lexique import Entree, Exemple, Sens, enregistrer_entree
from .analyse_ui import COULEURS_STATUT, PanneauAnalyse, VueInterlineaire
from .commun import CurseurAttente, carte, erreur, info
from .pages import Page, _item, _table


class DialogueTexte(QDialog):
    """Métadonnées d'un texte ; en mode import, aussi le texte et sa traduction."""

    def __init__(self, texte: textes.Texte, importer=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Importer un texte" if importer else "Informations sur le texte")
        self.resize(640, 560 if importer else 320)
        self.texte = texte
        form = QFormLayout(self)
        self.titre = QLineEdit(texte.titre)
        self.genre = QComboBox()
        self.genre.setEditable(True)
        self.genre.addItems([""] + textes.GENRES)
        self.genre.setEditText(texte.genre)
        self.locuteur = QLineEdit(texte.locuteur)
        self.lieu = QLineEdit(texte.lieu)
        self.date = QLineEdit(texte.date)
        self.date.setPlaceholderText("ex. : 2026-10-13")
        self.notes = QPlainTextEdit(texte.notes)
        self.notes.setFixedHeight(50)
        form.addRow("Titre :", self.titre)
        form.addRow("Genre :", self.genre)
        form.addRow("Locuteur / auteur :", self.locuteur)
        form.addRow("Lieu :", self.lieu)
        form.addRow("Date :", self.date)
        form.addRow("Notes :", self.notes)
        self.vern = self.trad = None
        if importer:
            aide = QLabel("Une phrase par ligne, ou un texte continu (découpé après . ! ? …). Si tu donnes une "
                          "traduction, elle doit avoir le même nombre de phrases : rien n'est aligné au hasard.")
            aide.setWordWrap(True)
            aide.setObjectName("sousTitre")
            form.addRow(aide)
            self.vern = QPlainTextEdit()
            self.trad = QPlainTextEdit()
            ligne = QHBoxLayout()
            for zone, libelle in ((self.vern, "Texte dans la langue…"), (self.trad, "Traduction…")):
                b = QPushButton(f"Charger {libelle.lower()[:-1]} (.txt)")
                b.clicked.connect(lambda _=False, z=zone: self._charger(z))
                ligne.addWidget(b)
            form.addRow(ligne)
            form.addRow("Texte :", self.vern)
            form.addRow("Traduction :", self.trad)
        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        boutons.accepted.connect(self._accepter)
        boutons.rejected.connect(self.reject)
        form.addRow(boutons)

    def _charger(self, zone):
        chemin, _ = QFileDialog.getOpenFileName(self, "Fichier texte", "", "Texte (*.txt);;Tous (*)")
        if chemin:
            for encodage in ("utf-8-sig", "cp1252"):
                try:
                    with open(chemin, encoding=encodage) as f:
                        zone.setPlainText(f.read())
                    return
                except UnicodeDecodeError:
                    continue
            erreur(self, "Fichier", "Encodage du fichier non reconnu (enregistre-le en UTF-8).")

    def _accepter(self):
        if self.vern is not None and not self.vern.toPlainText().strip():
            erreur(self, "Importer un texte", "Le texte est vide.")
            return
        t = self.texte
        t.titre, t.genre, t.locuteur = self.titre.text().strip(), self.genre.currentText().strip(), self.locuteur.text().strip()
        t.lieu, t.date, t.notes = self.lieu.text().strip(), self.date.text().strip(), self.notes.toPlainText().strip()
        self.accept()


# =============================================================================
class PageTextes(Page):
    """Textes du corpus en interlinéaire."""

    def __init__(self, projet):
        super().__init__(projet, "Textes",
                         "Clique sur un mot pour l'analyser. Couleurs : vert = analyse validée, ocre italique = "
                         "proposition unique de l'analyseur, rouille = plusieurs découpes, gris = inconnu.")
        separateur = QSplitter(Qt.Horizontal)
        gauche = QWidget()
        gl = QVBoxLayout(gauche)
        gl.setContentsMargins(0, 0, 0, 0)
        self.liste_textes = QListWidget()
        self.liste_textes.setMaximumHeight(170)
        self.liste_textes.currentItemChanged.connect(self._texte_choisi)
        gl.addWidget(self.liste_textes)
        ligne = QHBoxLayout()
        importer = QPushButton("Importer un texte…")
        importer.clicked.connect(self._importer)
        infos = QPushButton("Informations…")
        infos.clicked.connect(self._infos)
        ligne.addWidget(importer)
        ligne.addWidget(infos)
        gl.addLayout(ligne)
        self.meta = QLabel("")
        self.meta.setObjectName("sousTitre")
        self.meta.setWordWrap(True)
        gl.addWidget(self.meta)
        self.liste_phrases = QListWidget()
        self.liste_phrases.setWordWrap(True)
        self.liste_phrases.currentItemChanged.connect(self._phrase_choisie)
        gl.addWidget(self.liste_phrases, 1)
        separateur.addWidget(gauche)

        droite = QSplitter(Qt.Vertical)
        haut = QWidget()
        hl = QVBoxLayout(haut)
        hl.setContentsMargins(0, 0, 0, 0)
        self.ref = QLabel("")
        self.ref.setStyleSheet("font-weight: 600;")
        hl.addWidget(self.ref)
        zone = QScrollArea()
        zone.setWidgetResizable(True)
        self.vue = VueInterlineaire()
        self.vue.mot_choisi.connect(self._mot_choisi)
        zone.setWidget(self.vue)
        hl.addWidget(zone, 1)
        self.traduction = QLabel("")
        self.traduction.setWordWrap(True)
        hl.addWidget(self.traduction)
        champs = QFormLayout()
        self.litterale = QLineEdit()
        self.notes = QLineEdit()
        for champ in (self.litterale, self.notes):
            champ.editingFinished.connect(self._enregistrer_champs)
        champs.addRow("Traduction littérale :", self.litterale)
        champs.addRow("Notes :", self.notes)
        hl.addLayout(champs)
        droite.addWidget(haut)
        self.panneau = PanneauAnalyse(projet)
        self.panneau.analyse_modifiee.connect(self._analyse_modifiee)
        boite = carte()
        bl = QVBoxLayout(boite)
        bl.addWidget(self.panneau)
        droite.addWidget(boite)
        droite.setSizes([380, 300])
        separateur.addWidget(droite)
        separateur.setSizes([300, 760])
        self.racine.addWidget(separateur, 1)
        self.contexte = None
        self._ref_courante = None

    def rafraichir(self):
        courant = self.liste_textes.currentItem().data(Qt.UserRole) if self.liste_textes.currentItem() else None
        self.liste_textes.blockSignals(True)
        self.liste_textes.clear()
        for t in textes.lister(self.projet.conn):
            item = QListWidgetItem(f"{t.titre}  ({t.phrases})")
            item.setData(Qt.UserRole, t.code)
            self.liste_textes.addItem(item)
            if t.code == courant:
                self.liste_textes.setCurrentItem(item)
        self.liste_textes.blockSignals(False)
        if self.liste_textes.currentItem() is None and self.liste_textes.count():
            self.liste_textes.setCurrentRow(0)
        else:
            self._texte_choisi(self.liste_textes.currentItem())

    def _texte_courant(self):
        item = self.liste_textes.currentItem()
        if not item:
            return None
        return next((t for t in textes.lister(self.projet.conn) if t.code == item.data(Qt.UserRole)), None)

    def _texte_choisi(self, item, _ancien=None):
        self.contexte = il.Contexte(self.projet)
        self.liste_phrases.blockSignals(True)
        self.liste_phrases.clear()
        t = self._texte_courant()
        self.meta.setText(" · ".join(x for x in (t.genre, t.locuteur, t.lieu, t.date) if x) if t else "")
        if t:
            for ref, vern, _ in textes.phrases(self.projet.conn, t.code):
                li = QListWidgetItem(f"{ref.split(' ', 1)[-1]}  {vern or '—'}")
                li.setData(Qt.UserRole, ref)
                self.liste_phrases.addItem(li)
        self.liste_phrases.blockSignals(False)
        cible = next((i for i in range(self.liste_phrases.count())
                      if self.liste_phrases.item(i).data(Qt.UserRole) == self._ref_courante), 0)
        if self.liste_phrases.count():
            self.liste_phrases.setCurrentRow(cible)

    def _phrase_choisie(self, item, _ancien=None):
        if not item:
            return
        self._ref_courante = item.data(Qt.UserRole)
        self._afficher_phrase()

    def _afficher_phrase(self, position=None):
        ref = self._ref_courante
        ligne = self.projet.conn.execute(
            "SELECT vernaculaire, analyse, traduction_litterale, notes FROM phrases WHERE ref=?", (ref,)).fetchone()
        if not ligne:
            return
        vern, analyse, litterale, notes = ligne
        self.ref.setText(ref)
        self.vue.afficher(il.phrase(self.projet, ref, vern, self.contexte or il.Contexte(self.projet)))
        self.traduction.setText(f"<i>{html.escape(analyse or '(pas de traduction)')}</i>")
        self.litterale.setText(litterale or "")
        self.notes.setText(notes or "")
        if position is not None:
            self.vue.selectionner_position(position)

    def _mot_choisi(self, mot):
        self.panneau.afficher(mot.forme, self._ref_courante, mot.position)

    def _analyse_modifiee(self):
        self.contexte = il.Contexte(self.projet)
        self._afficher_phrase(self.panneau.position)
        self.donnees_modifiees.emit()

    def _enregistrer_champs(self):
        if self._ref_courante:
            with self.projet.conn:
                self.projet.conn.execute("UPDATE phrases SET traduction_litterale=?, notes=? WHERE ref=?",
                                         (self.litterale.text().strip() or None, self.notes.text().strip() or None,
                                          self._ref_courante))

    def ouvrir_phrase(self, ref):
        code = textes.code_texte(ref)
        self._ref_courante = ref
        for i in range(self.liste_textes.count()):
            if self.liste_textes.item(i).data(Qt.UserRole) == code:
                self.liste_textes.setCurrentRow(i)
                self._texte_choisi(self.liste_textes.item(i))
                return

    def _importer(self):
        d = DialogueTexte(textes.Texte(code=""), importer=True, parent=self)
        if not d.exec():
            return
        try:
            code = textes.importer_texte(self.projet, d.texte, d.vern.toPlainText(), d.trad.toPlainText())
        except ValueError as e:
            erreur(self, "Importer un texte", str(e))
            return
        self.donnees_modifiees.emit()   # rafraîchit la liste (et change la phrase courante)
        self.ouvrir_phrase(f"{code} 1")

    def _infos(self):
        t = self._texte_courant()
        if t and DialogueTexte(t, parent=self).exec():
            textes.enregistrer_meta(self.projet.conn, t)
            self.rafraichir()


# =============================================================================
class PageFormes(Page):
    """Inventaire des formes de mots du corpus."""
    voir_concordance = Signal(str)

    FILTRES = [("toutes les formes", None), ("à analyser (non validées)", "non_validees"),
               ("inconnues de l'analyseur", il.INCONNUE), ("plusieurs découpes", il.AMBIGUE),
               ("absentes du lexique", "hors_lexique")]

    def __init__(self, projet):
        super().__init__(projet, "Formes de mots",
                         "Tous les mots du corpus (langue documentée), les plus fréquents d'abord. "
                         "Analyser d'abord les formes fréquentes couvre vite une grande part des textes.")
        ligne = QHBoxLayout()
        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Filtrer les formes…")
        self.recherche.setClearButtonEnabled(True)
        self.recherche.textChanged.connect(self._afficher)
        self.filtre = QComboBox()
        for libelle, valeur in self.FILTRES:
            self.filtre.addItem(libelle, valeur)
        self.filtre.currentIndexChanged.connect(self._afficher)
        ligne.addWidget(self.recherche, 2)
        ligne.addWidget(self.filtre, 1)
        self.racine.addLayout(ligne)
        self.couverture = QLabel("")
        self.couverture.setObjectName("sousTitre")
        self.racine.addWidget(self.couverture)

        separateur = QSplitter(Qt.Vertical)
        self.table = _table(["Forme", "Occurrences", "Phrases", "Statut", "Au lexique", "Analyse"], etirer=(5,))
        self.table.currentItemChanged.connect(self._selection)
        self.table.itemDoubleClicked.connect(lambda _: self._concordance())
        separateur.addWidget(self.table)
        bas = QWidget()
        bl = QVBoxLayout(bas)
        bl.setContentsMargins(0, 0, 0, 0)
        boutons = QHBoxLayout()
        for texte, action in (("Voir la concordance", self._concordance),
                              ("Ajouter au lexique (avec un exemple)", self._ajouter_au_lexique)):
            b = QPushButton(texte)
            b.clicked.connect(action)
            boutons.addWidget(b)
        boutons.addStretch()
        bl.addLayout(boutons)
        self.panneau = PanneauAnalyse(projet)
        self.panneau.analyse_modifiee.connect(self.rafraichir)
        boite = carte()
        QVBoxLayout(boite).addWidget(self.panneau)
        bl.addWidget(boite)
        separateur.addWidget(bas)
        separateur.setSizes([380, 320])
        self.racine.addWidget(separateur, 1)
        self.formes = []

    def rafraichir(self):
        with CurseurAttente():
            self.formes = il.inventaire(self.projet)
        total = sum(f.frequence for f in self.formes) or 1
        par_statut = {}
        for f in self.formes:
            par_statut[f.statut] = par_statut.get(f.statut, 0) + f.frequence
        morceaux = [f"{len(self.formes)} formes, {total} occurrences"]
        for statut in (il.VALIDEE, il.PROPOSEE, il.AMBIGUE, il.INCONNUE):
            if par_statut.get(statut):
                morceaux.append(f"{statut} : {100 * par_statut[statut] / total:.1f} %")
        self.couverture.setText(" · ".join(morceaux))
        self._afficher()

    def _afficher(self):
        filtre = self.filtre.currentData()
        recherche = self.recherche.text().strip().lower()
        lignes = []
        for f in self.formes:
            if recherche and recherche not in f.forme:
                continue
            if filtre == "non_validees" and f.statut == il.VALIDEE:
                continue
            if filtre in (il.INCONNUE, il.AMBIGUE) and f.statut != filtre:
                continue
            if filtre == "hors_lexique" and f.au_lexique:
                continue
            lignes.append(f)
        lignes = lignes[:3000]
        self.table.setRowCount(len(lignes))
        for r, f in enumerate(lignes):
            self.table.setItem(r, 0, _item(f.forme, f.forme))
            for c, valeur in ((1, f.frequence), (2, f.phrases)):
                item = _item("")
                item.setData(Qt.DisplayRole, valeur)
                self.table.setItem(r, c, item)
            statut = _item(f.statut)
            statut.setForeground(QColor(COULEURS_STATUT[f.statut]))
            self.table.setItem(r, 3, statut)
            self.table.setItem(r, 4, _item("oui" if f.au_lexique else ""))
            self.table.setItem(r, 5, _item(f.analyse))

    def forme_courante(self):
        item = self.table.item(self.table.currentRow(), 0) if self.table.currentRow() >= 0 else None
        return item.data(Qt.UserRole) if item else None

    def _selection(self, *_):
        forme = self.forme_courante()
        if forme:
            self.panneau.afficher(forme)

    def _concordance(self):
        forme = self.forme_courante()
        if forme:
            self.voir_concordance.emit(forme)

    def _ajouter_au_lexique(self):
        forme = self.forme_courante()
        if not forme:
            return
        lignes = il.concordance(self.projet, forme, limite=1)
        sens = Sens()
        if lignes:
            l = lignes[0]
            sens.exemples = [Exemple(l.gauche + l.cle + l.droite, l.traduction, l.ref)]
        eid = enregistrer_entree(self.projet.conn, Entree(forme=forme, statut="brouillon", sens=[sens]))
        self.donnees_modifiees.emit()
        info(self, "Lexique", f"« {forme} » ajouté au lexique (statut brouillon), avec un exemple du corpus. "
                              "Complète sa glose dans la page Lexique.")
        return eid


# =============================================================================
class PageConcordance(Page):
    ouvrir_phrase = Signal(str)

    MODES = [("forme de mot exacte", "mot"), ("morphème (analyses validées)", "morphème"),
             ("suite de caractères", "texte"), ("expression régulière", "regex")]

    def __init__(self, projet):
        super().__init__(projet, "Concordance", "Chaque occurrence dans son contexte. Double-clic : ouvrir la phrase "
                                                "dans la page Textes.")
        ligne = QHBoxLayout()
        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Mot, morphème ou motif à chercher…")
        self.recherche.returnPressed.connect(self.chercher)
        self.mode = QComboBox()
        for libelle, valeur in self.MODES:
            self.mode.addItem(libelle, valeur)
        self.cote = QComboBox()
        self.cote.addItem("dans la langue documentée", "vernaculaire")
        self.cote.addItem("dans la traduction", "analyse")
        chercher = QPushButton("Chercher")
        chercher.setObjectName("principal")
        chercher.clicked.connect(self.chercher)
        ligne.addWidget(self.recherche, 2)
        ligne.addWidget(self.mode, 1)
        ligne.addWidget(self.cote, 1)
        ligne.addWidget(chercher)
        self.racine.addLayout(ligne)
        self.table = _table(["Référence", "Contexte gauche", "Mot", "Contexte droit", "Traduction"], etirer=(1, 3, 4))
        self.table.itemDoubleClicked.connect(lambda item: self.ouvrir_phrase.emit(
            self.table.item(item.row(), 0).data(Qt.UserRole)))
        self.racine.addWidget(self.table, 1)
        self.compte = QLabel("")
        self.compte.setObjectName("sousTitre")
        self.racine.addWidget(self.compte)

    def chercher_forme(self, forme):
        self.recherche.setText(forme)
        self.mode.setCurrentIndex(0)
        self.cote.setCurrentIndex(0)
        self.chercher()

    def chercher(self):
        try:
            with CurseurAttente():
                lignes = il.concordance(self.projet, self.recherche.text(), self.mode.currentData(),
                                        self.cote.currentData())
        except ValueError as e:
            erreur(self, "Concordance", str(e))
            return
        self.table.setRowCount(len(lignes))
        for r, l in enumerate(lignes):
            self.table.setItem(r, 0, _item(l.ref, l.ref))
            gauche = _item(("…" if len(l.gauche) >= 60 else "") + l.gauche)
            gauche.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(r, 1, gauche)
            cle = _item(l.cle)
            police = cle.font()
            police.setBold(True)
            cle.setFont(police)
            self.table.setItem(r, 2, cle)
            self.table.setItem(r, 3, _item(l.droite + ("…" if len(l.droite) >= 60 else "")))
            self.table.setItem(r, 4, _item(l.traduction))
        self.compte.setText(f"{len(lignes)} occurrence(s)" + (" (2000 au plus)" if len(lignes) >= 2000 else ""))

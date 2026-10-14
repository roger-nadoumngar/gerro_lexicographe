"""Page Syllabaire : alphabet, graphèmes du corpus, ordre des leçons, contenu de chaque leçon."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPushButton, QSplitter, QVBoxLayout, QWidget)

from .. import syllabaire as sy
from .commun import CurseurAttente, erreur, info
from .pages import Page, _item, _table, remplissage

COULEURS_NATURE = {"lettre": "#2B2A1F", "ton": "#1F5B57", "non déclaré": "#9C4A1A"}


class PageSyllabaire(Page):
    def __init__(self, projet):
        super().__init__(projet, "Syllabaire",
                         "Ordre d'enseignement des lettres et contenu des leçons, calculés sur le corpus. À chaque "
                         "leçon, le logiciel propose la lettre qui rend lisibles le plus de nouveaux mots ; tu peux "
                         "réordonner librement.")
        ligne = QHBoxLayout()
        ligne.addWidget(QLabel("Alphabet :"))
        self.alphabet = QLineEdit()
        self.alphabet.setPlaceholderText("graphèmes dans l'ordre, séparés par des espaces, multigraphes compris : "
                                         "a b ɓ d … ng ŋ ŋg nj …")
        ligne.addWidget(self.alphabet, 1)
        enregistrer = QPushButton("Enregistrer l'alphabet")
        enregistrer.clicked.connect(self._enregistrer_alphabet)
        ligne.addWidget(enregistrer)
        self.racine.addLayout(ligne)
        options = QHBoxLayout()
        self.tons = QCheckBox("Tons enseignés à part (« ká » = k + a + ◌́)")
        self.tons.setChecked(True)
        self.noms_propres = QCheckBox("Écarter les noms propres")
        self.noms_propres.setChecked(True)
        for case in (self.tons, self.noms_propres):
            case.toggled.connect(self.rafraichir)
            options.addWidget(case)
        options.addStretch()
        self.resume = QLabel("")
        self.resume.setObjectName("sousTitre")
        options.addWidget(self.resume)
        self.racine.addLayout(options)

        separateur = QSplitter(Qt.Horizontal)
        # graphèmes et candidats multigraphes
        gauche = QWidget()
        gl = QVBoxLayout(gauche)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.addWidget(QLabel("<b>Graphèmes du corpus</b>"))
        self.graphemes = _table(["Graphème", "Nature", "Occurrences", "Mots", "Exemples"], etirer=(4,))
        gl.addWidget(self.graphemes, 3)
        gl.addWidget(QLabel("<b>Suites de lettres fréquentes</b> — candidats multigraphes, à toi de juger"))
        self.suites = QListWidget()
        gl.addWidget(self.suites, 1)
        ajouter = QPushButton("Ajouter la suite choisie à l'alphabet")
        ajouter.clicked.connect(self._ajouter_suite)
        gl.addWidget(ajouter, 0, Qt.AlignLeft)
        separateur.addWidget(gauche)

        # ordre des leçons
        milieu = QWidget()
        ml = QVBoxLayout(milieu)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.addWidget(QLabel("<b>Ordre des leçons</b>"))
        self.ordre = QListWidget()
        self.ordre.currentRowChanged.connect(self._afficher_lecon)
        ml.addWidget(self.ordre, 1)
        boutons = QHBoxLayout()
        for texte, action in (("↑", lambda: self._deplacer(-1)), ("↓", lambda: self._deplacer(1))):
            b = QPushButton(texte)
            b.clicked.connect(action)
            boutons.addWidget(b)
        proposer = QPushButton("Proposer un ordre")
        proposer.setToolTip("À chaque leçon, la lettre qui rend lisibles le plus de nouveaux mots")
        proposer.clicked.connect(self._proposer)
        boutons.addWidget(proposer)
        ml.addLayout(boutons)
        self.btn_enregistrer_ordre = QPushButton("Enregistrer cet ordre")
        self.btn_enregistrer_ordre.setObjectName("principal")
        self.btn_enregistrer_ordre.clicked.connect(self._enregistrer_ordre)
        ml.addWidget(self.btn_enregistrer_ordre)
        separateur.addWidget(milieu)

        # contenu de la leçon
        droite = QWidget()
        dl = QVBoxLayout(droite)
        dl.setContentsMargins(0, 0, 0, 0)
        self.titre_lecon = QLabel("<b>Leçon</b>")
        dl.addWidget(self.titre_lecon)
        self.detail = QLabel("")
        self.detail.setObjectName("sousTitre")
        self.detail.setWordWrap(True)
        dl.addWidget(self.detail)
        self.mots = _table(["Nouveau mot", "Fréquence", "Glose"], etirer=(2,))
        dl.addWidget(self.mots, 2)
        dl.addWidget(QLabel("<b>Phrases du corpus lisibles à cette leçon</b>"))
        self.phrases = QListWidget()
        self.phrases.setWordWrap(True)
        dl.addWidget(self.phrases, 1)
        separateur.addWidget(droite)
        separateur.setSizes([380, 220, 420])
        self.racine.addWidget(separateur, 1)

        bas = QHBoxLayout()
        bas.addStretch()
        for texte, action in (("Exporter en texte…", lambda: self._exporter("txt")),
                              ("Exporter en CSV…", lambda: self._exporter("csv"))):
            b = QPushButton(texte)
            b.clicked.connect(action)
            bas.addWidget(b)
        self.racine.addLayout(bas)
        self.calcul = None
        self.lecons = []
        self._ordre_courant = []
        self._modifie = False

    # -- calcul ------------------------------------------------------------------------------
    def rafraichir(self):
        self.alphabet.setText(self.projet.reglage("alphabet_vern"))
        with CurseurAttente():
            self.calcul = sy.Syllabaire(self.projet, self.tons.isChecked(), self.noms_propres.isChecked())
            inventaire = self.calcul.inventaire()
        presents = {g.grapheme for g in inventaire}
        enregistre = [g for g in sy.ordre_enregistre(self.projet) if g in presents]
        manquants = [g.grapheme for g in inventaire if g.grapheme not in enregistre]
        if enregistre:
            ordre, self._modifie = enregistre + manquants, bool(manquants)
        else:
            ordre, self._modifie = [g for g, _ in self.calcul.ordre_propose()], True
        self._remplir_graphemes(inventaire)
        self.suites.clear()
        for suite, n in self.calcul.suites_frequentes(25):
            item = QListWidgetItem(f"{suite}    ({n} occurrences)")
            item.setData(Qt.UserRole, suite)
            self.suites.addItem(item)
        self._appliquer_ordre(ordre)
        non_declares = [g.grapheme for g in inventaire if g.nature == "non déclaré"]
        texte = f"{len(self.calcul.mots_utiles())} mots différents, {len(inventaire)} graphèmes"
        if not self.projet.reglage("alphabet_vern"):
            texte += " — aucun alphabet déclaré : chaque lettre compte seule"
        elif non_declares:
            texte += f" — {len(non_declares)} non déclaré(s) : {' '.join(non_declares[:12])}"
        self.resume.setText(texte)

    def _remplir_graphemes(self, inventaire):
        with remplissage(self.graphemes):
            self.graphemes.setRowCount(len(inventaire))
            for r, g in enumerate(inventaire):
                tete = _item(sy.affichage(g.grapheme), g.grapheme)
                police = tete.font()
                police.setPointSizeF(police.pointSizeF() * 1.3)
                tete.setFont(police)
                self.graphemes.setItem(r, 0, tete)
                nature = _item(g.nature)
                nature.setForeground(QColor(COULEURS_NATURE[g.nature]))
                self.graphemes.setItem(r, 1, nature)
                for c, valeur in ((2, g.occurrences), (3, g.mots)):
                    item = _item("")
                    item.setData(Qt.DisplayRole, valeur)
                    self.graphemes.setItem(r, c, item)
                self.graphemes.setItem(r, 4, _item(", ".join(g.exemples)))

    def _appliquer_ordre(self, ordre):
        """Recalcule les leçons pour cet ordre et met à jour la liste."""
        courant = max(0, self.ordre.currentRow())
        self._ordre_courant = list(ordre)
        self.lecons = self.calcul.lecons(self._ordre_courant)
        self.ordre.blockSignals(True)
        self.ordre.clear()
        for l in self.lecons:
            item = QListWidgetItem(f"{l.numero:>2}.  {sy.affichage(l.grapheme)}    +{l.debloques} mots  "
                                   f"({100 * l.occurrences_lisibles:.0f} %)")
            item.setToolTip(f"Après cette leçon : {l.lisibles} mots lisibles, "
                            f"{100 * l.occurrences_lisibles:.1f} % des mots du corpus")
            self.ordre.addItem(item)
        self.ordre.blockSignals(False)
        self.btn_enregistrer_ordre.setEnabled(self._modifie)
        if self.lecons:
            self.ordre.setCurrentRow(min(courant, len(self.lecons) - 1))
            self._afficher_lecon(self.ordre.currentRow())

    def _afficher_lecon(self, index):
        if not (0 <= index < len(self.lecons)):
            return
        l = self.lecons[index]
        self.titre_lecon.setText(f"<b>Leçon {l.numero} : {sy.affichage(l.grapheme)}</b>")
        self.detail.setText(f"{l.debloques} nouveau(x) mot(s) lisible(s) ; {l.lisibles} en tout, soit "
                            f"{100 * l.occurrences_lisibles:.1f} % des mots du corpus.")
        gloses = sy.gloses(self.projet.conn)
        with remplissage(self.mots):
            self.mots.setRowCount(len(l.mots))
            for r, (mot, n) in enumerate(l.mots):
                self.mots.setItem(r, 0, _item(mot))
                item = _item("")
                item.setData(Qt.DisplayRole, n)
                self.mots.setItem(r, 1, item)
                self.mots.setItem(r, 2, _item(gloses.get(mot, "")))
        self.phrases.clear()
        for ref, texte in l.phrases:
            self.phrases.addItem(f"{texte}   [{ref}]")
        if not l.phrases:
            self.phrases.addItem("(aucune phrase du corpus n'est encore entièrement lisible)")

    # -- actions ------------------------------------------------------------------------------
    def _enregistrer_alphabet(self):
        self.projet.definir_reglages({"alphabet_vern": " ".join(self.alphabet.text().split())})
        self.donnees_modifiees.emit()

    def _ajouter_suite(self):
        item = self.suites.currentItem()
        if not item:
            erreur(self, "Alphabet", "Choisis d'abord une suite dans la liste.")
            return
        suite = item.data(Qt.UserRole)
        graphemes = self.alphabet.text().split()
        if suite not in graphemes:
            self.alphabet.setText(" ".join(graphemes + [suite]))
            self._enregistrer_alphabet()

    def _deplacer(self, decalage):
        i = self.ordre.currentRow()
        j = i + decalage
        if i < 0 or not 0 <= j < len(self._ordre_courant):
            return
        ordre = list(self._ordre_courant)
        ordre[i], ordre[j] = ordre[j], ordre[i]
        self._modifie = True
        self.ordre.blockSignals(True)
        self.ordre.setCurrentRow(j)
        self.ordre.blockSignals(False)
        self._appliquer_ordre(ordre)

    def _proposer(self):
        self._modifie = True
        self._appliquer_ordre([g for g, _ in self.calcul.ordre_propose()])

    def _enregistrer_ordre(self):
        sy.enregistrer_ordre(self.projet, self._ordre_courant)
        self._modifie = False
        self.btn_enregistrer_ordre.setEnabled(False)

    def _exporter(self, extension):
        filtre = "Texte (*.txt)" if extension == "txt" else "CSV (*.csv)"
        chemin, _ = QFileDialog.getSaveFileName(self, "Exporter le syllabaire", f"syllabaire.{extension}", filtre)
        if not chemin:
            return
        try:
            (sy.exporter_texte if extension == "txt" else sy.exporter_csv)(self.projet, self.lecons, chemin)
        except OSError as e:
            erreur(self, "Export", "Le fichier n'a pas pu être écrit.", e)
            return
        info(self, "Export", f"{len(self.lecons)} leçon(s) exportée(s) vers :\n{chemin}")

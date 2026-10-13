"""Dialogues : choix du projet, nouveau projet, réglages du projet."""


from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from .. import APP_NAME, lexique
from ..chemins import anciennes_bases
from ..projet import EXTENSION, lister_projets
from .commun import confirmer, erreur, titre


class DialogueNouveauProjet(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nouveau projet")
        self.setMinimumWidth(460)
        form = QFormLayout(self)
        self.langue = QLineEdit()
        self.langue.setPlaceholderText("ex. : ngambay")
        self.code = QLineEdit()
        self.code.setPlaceholderText("ex. : sba")
        self.code.setMaxLength(8)
        self.analyse = QLineEdit("français")
        self.code_analyse = QLineEdit("fr")
        self.code_analyse.setMaxLength(8)
        self.corpus = QCheckBox("Charger le corpus d'exemple Ruth et Job (ngambay–français)")
        self.corpus.setEnabled(False)
        self.code.textChanged.connect(lambda t: self.corpus.setEnabled(t.strip().lower() == "sba"))
        aide = QLabel("Code ISO 639-3 de la langue : voir <a href='https://www.ethnologue.com'>ethnologue.com</a>. "
                      "Il identifie la langue dans les exports LIFT (FLEx, WeSay, applications).")
        aide.setOpenExternalLinks(True)
        aide.setWordWrap(True)
        aide.setObjectName("sousTitre")
        form.addRow("Langue documentée :", self.langue)
        form.addRow("Code ISO 639-3 :", self.code)
        form.addRow("", aide)
        form.addRow("Langue d'analyse :", self.analyse)
        form.addRow("Code de la langue d'analyse :", self.code_analyse)
        form.addRow("", self.corpus)
        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        boutons.accepted.connect(self._accepter)
        boutons.rejected.connect(self.reject)
        form.addRow(boutons)

    def _accepter(self):
        if not self.langue.text().strip() or not self.code.text().strip():
            erreur(self, "Nouveau projet", "Indique le nom et le code de la langue documentée.")
            return
        self.accept()

    def reglages(self):
        nom_langue = self.langue.text().strip()
        valeurs = dict(nom=nom_langue[:1].upper() + nom_langue[1:], langue_vern_nom=nom_langue,
                       langue_vern_code=self.code.text().strip().lower(),
                       langue_analyse_nom=self.analyse.text().strip(),
                       langue_analyse_code=self.code_analyse.text().strip().lower())
        if self.corpus.isEnabled() and self.corpus.isChecked():
            valeurs["corpus_integre"] = "ngambay_ruth_job"
        return valeurs


class DialogueProjets(QDialog):
    """Choix du projet à ouvrir. Après exec(), `action` vaut ('ouvrir', chemin),
    ('creer', réglages), ou ('importer_v01', chemin_ancienne_base)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.action = None
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(560, 420)
        v = QVBoxLayout(self)
        t, s = titre(APP_NAME, "Choisis un projet. Chaque projet documente une langue.")
        v.addWidget(t)
        v.addWidget(s)
        self.liste = QListWidget()
        self.liste.itemDoubleClicked.connect(lambda _: self._ouvrir())
        v.addWidget(self.liste, 1)
        ligne = QHBoxLayout()
        for texte, action, principal in [("Ouvrir", self._ouvrir, True), ("Nouveau projet…", self._nouveau, False),
                                         ("Ouvrir un fichier…", self._fichier, False),
                                         ("Importer une base v0.1…", self._importer, False)]:
            b = QPushButton(texte)
            if principal:
                b.setObjectName("principal")
            b.clicked.connect(action)
            ligne.addWidget(b)
        ligne.addStretch()
        v.addLayout(ligne)
        self._remplir()

    def _remplir(self):
        self.liste.clear()
        for nom, chemin in lister_projets():
            item = QListWidgetItem(f"{nom}\n{chemin}")
            item.setData(Qt.UserRole, chemin)
            self.liste.addItem(item)
        if self.liste.count():
            self.liste.setCurrentRow(0)

    def _ouvrir(self):
        item = self.liste.currentItem()
        if item:
            self.action = ("ouvrir", item.data(Qt.UserRole))
            self.accept()

    def _nouveau(self):
        d = DialogueNouveauProjet(self)
        if d.exec():
            self.action = ("creer", d.reglages())
            self.accept()

    def _fichier(self):
        chemin, _ = QFileDialog.getOpenFileName(self, "Ouvrir un projet", "", f"Projet (*{EXTENSION})")
        if chemin:
            self.action = ("ouvrir", chemin)
            self.accept()

    def _importer(self):
        trouvees = anciennes_bases()
        chemin = None
        if trouvees:
            choix, ok = QInputDialog.getItem(self, "Importer une base v0.1", "Base trouvée :",
                                             trouvees + ["Autre fichier…"], 0, False)
            if not ok:
                return
            chemin = None if choix == "Autre fichier…" else choix
        if chemin is None:
            chemin, _ = QFileDialog.getOpenFileName(self, "Base de la version 0.1", "", "Base (*.db)")
        if chemin:
            self.action = ("importer_v01", chemin)
            self.accept()


class DialogueReglages(QDialog):
    """Réglages du projet. Après acceptation, `decoupage_modifie` indique s'il faut
    recalculer les propositions."""

    CLES_DECOUPAGE = ("caracteres_mot_vern", "caracteres_mot_analyse", "longueur_min_mot", "mots_vides_analyse")

    def __init__(self, projet, parent=None):
        super().__init__(parent)
        self.projet = projet
        self.decoupage_modifie = False
        self.setWindowTitle("Réglages du projet")
        self.setMinimumSize(620, 520)
        v = QVBoxLayout(self)
        onglets = QTabWidget()
        v.addWidget(onglets)
        r = projet.reglages

        langues = QWidget()
        f = QFormLayout(langues)
        self.nom = QLineEdit(r["nom"])
        self.vern_nom = QLineEdit(r["langue_vern_nom"])
        self.vern_code = QLineEdit(r["langue_vern_code"])
        self.analyse_nom = QLineEdit(r["langue_analyse_nom"])
        self.analyse_code = QLineEdit(r["langue_analyse_code"])
        f.addRow("Nom du projet :", self.nom)
        f.addRow("Langue documentée :", self.vern_nom)
        f.addRow("Code ISO 639-3 :", self.vern_code)
        f.addRow("Langue d'analyse :", self.analyse_nom)
        f.addRow("Code de la langue d'analyse :", self.analyse_code)
        onglets.addTab(langues, "Langues")

        decoupage = QWidget()
        f = QFormLayout(decoupage)
        explication = QLabel(
            "Un mot est une suite de lettres, de marques combinantes (tons, nasalisation…) et de chiffres. "
            "Indique ici les autres caractères qui font partie des mots. Par exemple, avec ’ "
            "dans la liste, « dee’g » reste un seul mot ; sans lui, il donne « dee » et « g ».")
        explication.setWordWrap(True)
        explication.setObjectName("sousTitre")
        f.addRow(explication)
        self.car_vern = QLineEdit(r["caracteres_mot_vern"])
        self.car_analyse = QLineEdit(r["caracteres_mot_analyse"])
        self.longueur = QSpinBox()
        self.longueur.setRange(1, 5)
        self.longueur.setValue(int(r["longueur_min_mot"] or 1))
        self.mots_vides = QPlainTextEdit(r["mots_vides_analyse"])
        self.seuil = QDoubleSpinBox()
        self.seuil.setRange(0.05, 1.0)
        self.seuil.setSingleStep(0.05)
        self.seuil.setValue(float(r["seuil_contradiction"] or 0.5))
        f.addRow("Caractères de mot (langue documentée) :", self.car_vern)
        f.addRow("Caractères de mot (langue d'analyse) :", self.car_analyse)
        f.addRow("Longueur minimale d'un mot (lettres) :", self.longueur)
        f.addRow("Mots vides de la langue d'analyse\n(ignorés par le moteur) :", self.mots_vides)
        f.addRow("Seuil de contradiction (Dice) :", self.seuil)
        onglets.addTab(decoupage, "Découpage en mots")

        cats = QWidget()
        cv = QVBoxLayout(cats)
        aide = QLabel("Catégories grammaticales propres à la langue documentée.")
        aide.setObjectName("sousTitre")
        cv.addWidget(aide)
        self.categories = QListWidget()
        cv.addWidget(self.categories)
        cl = QHBoxLayout()
        for texte, action in [("Ajouter…", self._ajouter_cat), ("Renommer…", self._renommer_cat),
                              ("Supprimer", self._supprimer_cat)]:
            b = QPushButton(texte)
            b.clicked.connect(action)
            cl.addWidget(b)
        cl.addStretch()
        cv.addLayout(cl)
        onglets.addTab(cats, "Catégories")
        self._remplir_categories()

        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        boutons.accepted.connect(self._accepter)
        boutons.rejected.connect(self.reject)
        v.addWidget(boutons)

    def _remplir_categories(self):
        self.categories.clear()
        for cid, nom, abrev, _ in lexique.categories(self.projet.conn):
            item = QListWidgetItem(nom + (f"  ({abrev})" if abrev else ""))
            item.setData(Qt.UserRole, (cid, nom, abrev or ""))
            self.categories.addItem(item)

    def _demander_cat(self, nom="", abrev=""):
        nom, ok = QInputDialog.getText(self, "Catégorie", "Nom :", text=nom)
        if not ok or not nom.strip():
            return None
        abrev, ok = QInputDialog.getText(self, "Catégorie", "Abréviation :", text=abrev)
        return (nom.strip(), abrev.strip()) if ok else None

    def _ajouter_cat(self):
        valeurs = self._demander_cat()
        if valeurs:
            try:
                lexique.ajouter_categorie(self.projet.conn, *valeurs)
            except Exception as e:
                erreur(self, "Catégorie", "Cette catégorie n'a pas pu être ajoutée (nom déjà utilisé ?).", e)
            self._remplir_categories()

    def _renommer_cat(self):
        item = self.categories.currentItem()
        if item:
            cid, nom, abrev = item.data(Qt.UserRole)
            valeurs = self._demander_cat(nom, abrev)
            if valeurs:
                try:
                    lexique.renommer_categorie(self.projet.conn, cid, *valeurs)
                except Exception as e:
                    erreur(self, "Catégorie", "Renommage impossible (nom déjà utilisé ?).", e)
                self._remplir_categories()

    def _supprimer_cat(self):
        item = self.categories.currentItem()
        if item:
            cid, nom, _ = item.data(Qt.UserRole)
            n = self.projet.conn.execute("SELECT COUNT(*) FROM sens WHERE categorie_id=?", (cid,)).fetchone()[0]
            if confirmer(self, "Supprimer", f"Supprimer la catégorie « {nom} » ?"
                                            + (f"\n{n} sens l'utilisent et resteront sans catégorie." if n else "")):
                lexique.supprimer_categorie(self.projet.conn, cid)
                self._remplir_categories()

    def _accepter(self):
        if not self.nom.text().strip():
            erreur(self, "Réglages", "Le nom du projet est vide.")
            return
        valeurs = {
            "nom": self.nom.text().strip(),
            "langue_vern_nom": self.vern_nom.text().strip(),
            "langue_vern_code": self.vern_code.text().strip().lower(),
            "langue_analyse_nom": self.analyse_nom.text().strip(),
            "langue_analyse_code": self.analyse_code.text().strip().lower(),
            "caracteres_mot_vern": self.car_vern.text().replace(" ", ""),
            "caracteres_mot_analyse": self.car_analyse.text().replace(" ", ""),
            "longueur_min_mot": str(self.longueur.value()),
            "mots_vides_analyse": " ".join(self.mots_vides.toPlainText().split()),
            "seuil_contradiction": f"{self.seuil.value():.2f}",
        }
        avant = self.projet.reglages
        self.decoupage_modifie = any(avant.get(k) != valeurs[k] for k in self.CLES_DECOUPAGE)
        self.projet.definir_reglages(valeurs)
        self.accept()

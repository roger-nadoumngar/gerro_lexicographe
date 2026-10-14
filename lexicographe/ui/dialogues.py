"""Dialogues : choix du projet, nouveau projet, réglages du projet."""


from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFontComboBox, QFormLayout,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from .. import APP_NAME, corpus, lexique, traits
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
        self.corpus.setVisible(corpus.disponible("ngambay_ruth_job"))
        self.code.textChanged.connect(lambda t: self.corpus.setEnabled(t.strip().lower() == "sba"
                                                                     and corpus.disponible("ngambay_ruth_job")))
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


class DialogueFlex(QDialog):
    """Choix d'un projet FLEx à importer. Après acceptation : `chemin`, `statut`, `avec_textes`."""

    def __init__(self, parent=None, titre_fenetre="Importer un projet FLEx"):
        super().__init__(parent)
        from datetime import datetime
        from .. import flex_import
        self.setWindowTitle(titre_fenetre)
        self.setMinimumSize(620, 440)
        self.chemin = None
        v = QVBoxLayout(self)
        dossier = flex_import.dossier_projets_flex()
        aide = QLabel(f"Projets FLEx trouvés dans <b>{dossier}</b>. Le projet FLEx est seulement lu : "
                      "il n'est jamais modifié. Réimporter le même projet met à jour au lieu de dupliquer.")
        aide.setWordWrap(True)
        v.addWidget(aide)
        self.liste = QListWidget()
        self.liste.itemDoubleClicked.connect(lambda _: self._accepter())
        for p in flex_import.lister_projets_flex(dossier):
            date = datetime.fromtimestamp(p.modifie).strftime("%d/%m/%Y")
            texte = f"{p.nom}    ({p.taille // 1_000_000} Mo, modifié le {date})"
            if p.ouvert_dans_flex:
                texte += "   — ouvert dans FLEx : ferme FLEx pour importer la dernière version"
            item = QListWidgetItem(texte)
            item.setData(Qt.UserRole, p.chemin)
            self.liste.addItem(item)
        if self.liste.count():
            self.liste.setCurrentRow(0)
        else:
            self.liste.addItem(QListWidgetItem("Aucun projet FLEx trouvé : utilise « Autre fichier… »."))
        v.addWidget(self.liste, 1)
        autre = QPushButton("Autre fichier .fwdata…")
        autre.clicked.connect(self._autre)
        v.addWidget(autre, 0, Qt.AlignLeft)
        form = QFormLayout()
        self.statut = QComboBox()
        self.statut.addItems(lexique.STATUTS)
        self.statut.setCurrentText("à vérifier")
        self.avec_textes = QCheckBox("Importer aussi les textes et leurs analyses interlinéaires")
        self.avec_textes.setChecked(True)
        form.addRow("Statut des entrées importées :", self.statut)
        form.addRow(self.avec_textes)
        v.addLayout(form)
        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        boutons.button(QDialogButtonBox.Ok).setText("Importer")
        boutons.accepted.connect(self._accepter)
        boutons.rejected.connect(self.reject)
        v.addWidget(boutons)

    def _autre(self):
        chemin, _ = QFileDialog.getOpenFileName(self, "Projet FLEx", "", "Projet FLEx (*.fwdata)")
        if chemin:
            self.chemin = chemin
            self._fermer()

    def _accepter(self):
        item = self.liste.currentItem()
        if item and item.data(Qt.UserRole):
            self.chemin = item.data(Qt.UserRole)
            self._fermer()

    def _fermer(self):
        self.statut_choisi = self.statut.currentText()
        self.textes_choisis = self.avec_textes.isChecked()
        self.accept()


class DialogueProjets(QDialog):
    """Choix du projet à ouvrir. Après exec(), `action` vaut ('ouvrir', chemin),
    ('creer', réglages), ('importer_v01', chemin_ancienne_base) ou
    ('importer_flex', (chemin .fwdata, statut, avec_textes))."""

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
                                         ("Importer un projet FLEx…", self._flex, False),
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

    def _flex(self):
        d = DialogueFlex(self)
        if d.exec() and d.chemin:
            self.action = ("importer_flex", (d.chemin, d.statut_choisi, d.textes_choisis))
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

        ecriture = QWidget()
        f = QFormLayout(ecriture)
        aide_alpha = QLabel(
            "Ordre alphabétique de la langue documentée : les graphèmes dans l'ordre, séparés par des espaces, "
            "multigraphes compris (ex. : a b ɓ d ɗ e ə g i k m n ŋ ŋg o ɔ …). Le lexique et les dictionnaires "
            "suivent cet ordre ; les tons et autres marques départagent ensuite les mots identiques. "
            "Laisser vide pour l'ordre alphabétique habituel.")
        aide_alpha.setWordWrap(True)
        aide_alpha.setObjectName("sousTitre")
        f.addRow(aide_alpha)
        self.alphabet = QPlainTextEdit(r["alphabet_vern"])
        self.alphabet.setFixedHeight(70)
        self.police = QFontComboBox()
        self.avec_police = QCheckBox("Utiliser une police particulière pour la langue documentée")
        self.avec_police.setChecked(bool(r["police_vern"]))
        if r["police_vern"]:
            self.police.setCurrentFont(QFont(r["police_vern"]))
        self.police.setEnabled(self.avec_police.isChecked())
        self.avec_police.toggled.connect(self.police.setEnabled)
        f.addRow("Alphabet :", self.alphabet)
        aide_classes = QLabel("Classes de sons pour les environnements d'allomorphes, une par ligne : "
                              "« V = a e i o u ə ɛ ɔ », « N = m n ŋ ». Un allomorphe noté « / N _ » ne sera alors "
                              "proposé qu'après une de ces lettres.")
        aide_classes.setWordWrap(True)
        aide_classes.setObjectName("sousTitre")
        self.classes = QPlainTextEdit(r["classes_phonologiques"].replace(" ; ", "\n"))
        self.classes.setFixedHeight(70)
        f.addRow(aide_classes)
        f.addRow("Classes :", self.classes)
        f.addRow(self.avec_police)
        f.addRow("Police :", self.police)
        onglets.addTab(ecriture, "Écriture")

        cats = QWidget()
        cv = QVBoxLayout(cats)
        aide = QLabel("Catégories grammaticales propres à la langue documentée. Une catégorie peut en contenir "
                      "d'autres (ex. : nom → nom comptable, nom de masse).")
        aide.setObjectName("sousTitre")
        cv.addWidget(aide)
        self.categories = QListWidget()
        cv.addWidget(self.categories)
        cl = QHBoxLayout()
        for texte, action in [("Ajouter…", self._ajouter_cat), ("Ajouter une sous-catégorie…", self._ajouter_sous_cat),
                              ("Renommer…", self._renommer_cat), ("Déplacer…", self._deplacer_cat),
                              ("Supprimer", self._supprimer_cat)]:
            b = QPushButton(texte)
            b.clicked.connect(action)
            cl.addWidget(b)
        cl.addStretch()
        cv.addLayout(cl)
        onglets.addTab(cats, "Catégories")

        onglet_traits = QWidget()
        tv = QVBoxLayout(onglet_traits)
        aide_traits = QLabel("Traits grammaticaux de la langue (classe nominale, ton, transitivité…) et leurs "
                             "valeurs permises. Dans la fiche d'une entrée, ils sont proposés en listes, et une "
                             "valeur non déclarée est refusée. Les propriétés non déclarées restent libres.")
        aide_traits.setWordWrap(True)
        aide_traits.setObjectName("sousTitre")
        tv.addWidget(aide_traits)
        self.traits = traits.lire(projet)
        self.liste_traits = QListWidget()
        tv.addWidget(self.liste_traits)
        tl = QHBoxLayout()
        for texte, action in [("Ajouter…", self._ajouter_trait), ("Modifier…", self._modifier_trait),
                              ("Supprimer", self._supprimer_trait)]:
            b = QPushButton(texte)
            b.clicked.connect(action)
            tl.addWidget(b)
        tl.addStretch()
        tv.addLayout(tl)
        onglets.addTab(onglet_traits, "Traits")
        self._remplir_traits()
        self._remplir_categories()

        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        boutons.accepted.connect(self._accepter)
        boutons.rejected.connect(self.reject)
        v.addWidget(boutons)

    def _remplir_traits(self):
        self.liste_traits.clear()
        for nom, valeurs in self.traits.items():
            item = QListWidgetItem(f"{nom} : {', '.join(valeurs) if valeurs else '(valeurs libres)'}")
            item.setData(Qt.UserRole, nom)
            self.liste_traits.addItem(item)

    def _demander_trait(self, nom="", valeurs=()):
        nom, ok = QInputDialog.getText(self, "Trait grammatical", "Nom du trait (ex. : classe nominale) :", text=nom)
        if not ok or not nom.strip():
            return None
        texte, ok = QInputDialog.getText(self, "Trait grammatical",
                                         "Valeurs permises, séparées par des virgules (ex. : 1, 2, 3) :",
                                         text=", ".join(valeurs))
        if not ok:
            return None
        return nom.strip(), [v.strip() for v in texte.split(",") if v.strip()]

    def _ajouter_trait(self):
        r = self._demander_trait()
        if r:
            self.traits[r[0]] = r[1]
            self._remplir_traits()

    def _modifier_trait(self):
        item = self.liste_traits.currentItem()
        if not item:
            return
        ancien = item.data(Qt.UserRole)
        r = self._demander_trait(ancien, self.traits[ancien])
        if r:
            utilisees = set(traits.utilisations(self.projet.conn, ancien)) - set(r[1])
            if utilisees and r[1] and not confirmer(
                    self, "Trait grammatical", f"Des entrées utilisent encore : {', '.join(sorted(utilisees))}.\n"
                                               "Ces valeurs ne seront plus permises. Continuer ?"):
                return
            self.traits = {(r[0] if k == ancien else k): (r[1] if k == ancien else v) for k, v in self.traits.items()}
            if r[0] != ancien:
                with self.projet.conn:
                    self.projet.conn.execute("UPDATE proprietes SET nom=? WHERE nom=?", (r[0], ancien))
            self._remplir_traits()

    def _supprimer_trait(self):
        item = self.liste_traits.currentItem()
        if item:
            nom = item.data(Qt.UserRole)
            n = sum(traits.utilisations(self.projet.conn, nom).values())
            if confirmer(self, "Supprimer", f"Ne plus déclarer le trait « {nom} » ?"
                                            + (f"\nLes {n} entrée(s) qui l'utilisent le gardent comme propriété libre."
                                               if n else "")):
                del self.traits[nom]
                self._remplir_traits()

    def _remplir_categories(self):
        self.categories.clear()
        for cid, nom, abrev, profondeur in lexique.categories_arbre(self.projet.conn):
            item = QListWidgetItem("      " * profondeur + nom + (f"  ({abrev})" if abrev else ""))
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

    def _ajouter_sous_cat(self):
        item = self.categories.currentItem()
        if not item:
            erreur(self, "Catégorie", "Sélectionne d'abord la catégorie parente.")
            return
        valeurs = self._demander_cat()
        if valeurs:
            try:
                lexique.ajouter_categorie(self.projet.conn, *valeurs, parent_id=item.data(Qt.UserRole)[0])
            except Exception as e:
                erreur(self, "Catégorie", "Cette catégorie n'a pas pu être ajoutée (nom déjà utilisé ?).", e)
            self._remplir_categories()

    def _deplacer_cat(self):
        item = self.categories.currentItem()
        if not item:
            return
        cid, nom, _ = item.data(Qt.UserRole)
        autres = [(c, n) for c, n, _, _ in lexique.categories(self.projet.conn) if c != cid]
        choix, ok = QInputDialog.getItem(self, "Déplacer", f"Placer « {nom} » sous :",
                                         ["(aucune : catégorie principale)"] + [n for _, n in autres], 0, False)
        if not ok:
            return
        parent = None if choix.startswith("(") else next(c for c, n in autres if n == choix)
        try:
            lexique.deplacer_categorie(self.projet.conn, cid, parent)
        except ValueError as e:
            erreur(self, "Déplacer", str(e))
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
            "alphabet_vern": " ".join(self.alphabet.toPlainText().split()),
            "classes_phonologiques": " ; ".join(l.strip() for l in self.classes.toPlainText().splitlines()
                                                if "=" in l),
            "police_vern": self.police.currentFont().family() if self.avec_police.isChecked() else "",
        }
        avant = self.projet.reglages
        self.decoupage_modifie = any(avant.get(k) != valeurs[k] for k in self.CLES_DECOUPAGE)
        self.projet.definir_reglages(valeurs)
        traits.enregistrer(self.projet, self.traits)
        self.accept()

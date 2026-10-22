"""Fenêtre principale : navigation à gauche, pages à droite."""

import os

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QStackedWidget,
                               QWidget)

from .. import APP_NAME, __version__, alignement
from ..chemins import dossier_sauvegardes
from ..projet import EXTENSION
from .commun import CurseurAttente, confirmer, erreur, info
from .dialogues import DialogueReglages
from .pages_analyse import PageConcordance, PageFormes, PageTextes
from .paratext_ui import importer_paratext
from .syllabaire_ui import PageSyllabaire
from .collecte_ui import PageCollecte
from .pages import (PageCorpus, PageDomaines, PageExports, PageImports, PageIndexInverse, PageLexique, PageTableauDeBord,
                    PageValidation)


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

        lexique_p, domaines_p, textes_p, corpus_p = (PageLexique(projet), PageDomaines(projet), PageTextes(projet),
                                                     PageCorpus(projet))
        imports = PageImports(projet, [
            ("Projet FLEx", "Reprendre un projet FLEx de cet ordinateur (lexique, textes et analyses "
                            "interlinéaires). Le projet FLEx est seulement lu.", lexique_p._importer_flex),
            ("Projet Paratext", "Livres traduits (corpus, langue du projet ou traduction pour un corpus parallèle), "
                                "glossaire interlinéaire et rendus des termes bibliques. Seulement lu.",
             self._importer_paratext),
            ("Fichier LIFT (FLEx, WeSay)", "Lexique exporté par FLEx, WeSay ou un autre outil SIL.",
             lexique_p._importer_lift),
            ("Dictionnaire imprimé (Word ou texte)", "Dictionnaire converti en .docx ou .txt, présenté comme ceux "
                                                     "du Projet Sara-Baguirmi (vedette [prononciation], puis « N glose. "
                                                     "Exemple. Traduction. »). Complète les entrées existantes "
                                                     "(exemples, prononciations, synonymes, expressions), répare les "
                                                     "gloses coupées ; une simulation est montrée avant.",
             self._importer_dictionnaire),
            ("Texte de terrain (.txt)", "Conte, récit, conversation… avec sa traduction et ses informations "
                                        "(genre, locuteur, lieu, date).", textes_p._importer),
            ("Bible complète (dossier ou archive .zip)", "Tous les livres d'un coup, en USFM ou en USX : par exemple "
                                                         "un paquet de la Digital Bible Library ou les fichiers "
                                                         "fournis par une Société biblique (PDV, français courant…).",
             self._importer_bible),
            ("Livre biblique (USFM / SFM)", "Fichier Paratext ou autre, dans la langue du projet ou dans la "
                                            "langue d'analyse.", corpus_p._importer_usfm),
            ("Document Word ou PDF", "Lecture du texte pour en copier des phrases.", corpus_p._lire_document),
            ("Enregistrement audio", "Fichier conservé dans le dossier du projet.", corpus_p._importer_audio),
            ("Liste de domaines sémantiques", "Fichier SemDom.xml ou LocalizedLists de FLEx.", domaines_p._importer),
            ("Travail d'un autre poste (fusion)", "Réunir un projet copié depuis un autre ordinateur (collecte sur "
                                                 "le terrain…) : entrées nouvelles ajoutées ; pour une entrée modifiée "
                                                 "des deux côtés, la version la plus récente l'emporte.",
             self._fusionner),
        ])
        self.pages = [
            ("Tableau de bord", PageTableauDeBord(projet)),
            ("Lexique", lexique_p),
            ("Domaines", domaines_p),
            ("Index inverse", PageIndexInverse(projet)),
            ("Textes", textes_p),
            ("Formes de mots", PageFormes(projet)),
            ("Concordance", PageConcordance(projet)),
            ("Collecte", PageCollecte(projet)),
            ("Syllabaire", PageSyllabaire(projet)),
            ("Validation", PageValidation(projet)),
            ("Corpus", corpus_p),
            ("Imports", imports),
            ("Exports", PageExports(projet)),
        ]
        for nom, page in self.pages:
            item = QListWidgetItem(nom)
            # hauteur fixée ici plutôt que par une marge du style : avec le zoom d'affichage de Windows,
            # la marge du style agrandit le fond du survol sans agrandir la ligne, qui déborde alors
            item.setSizeHint(QSize(0, self.navigation.fontMetrics().height() + 18))
            self.navigation.addItem(item)
            self.pile.addWidget(page)
            page.donnees_modifiees.connect(self.rafraichir_tout)
        for _, page in self.pages:
            if hasattr(page, "ouvrir_entree") and not isinstance(page, PageLexique):
                page.ouvrir_entree.connect(self.ouvrir_entree)
        dict(self.pages)["Formes de mots"].voir_concordance.connect(self.voir_concordance)
        dict(self.pages)["Concordance"].ouvrir_phrase.connect(self.ouvrir_phrase)
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
            ("Importer un projet FLEx…", None, dict(self.pages)["Lexique"]._importer_flex),
            ("Importer un projet Paratext…", None, self._importer_paratext),
            ("Importer un fichier LIFT…", None, dict(self.pages)["Lexique"]._importer_lift),
            ("Tous les imports…", None, lambda: self._aller("Imports")),
            (None, None, None),
            ("Réglages du projet…", "Ctrl+,", self._reglages),
            ("Langue de l'interface (Interface language)…", None, self._langue_interface),
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
        guide = QAction("Guide d'utilisation", self)
        guide.setShortcut(QKeySequence.HelpContents)
        guide.triggered.connect(self._guide)
        aide.addAction(guide)
        a = QAction("Inscription…", self)
        a.triggered.connect(self._inscription)
        aide.addAction(a)
        a = QAction("À propos", self)
        a.triggered.connect(self._a_propos)
        aide.addAction(a)

    def _inscription(self):
        from .. import inscription
        from .inscription_ui import DialogueInscription
        email = inscription.inscrit()
        if email:
            info(self, "Inscription", f"{APP_NAME} est inscrit au nom de {email}.")
        else:
            DialogueInscription(self).exec()

    def _a_propos(self):
        from .. import inscription
        from .traduction import tr
        email = inscription.inscrit()
        statut = tr(f"Inscrit au nom de : {email}") if email else tr("Non inscrit (menu Aide → Inscription…)")
        QMessageBox.about(
            self, APP_NAME, f"<b>{APP_NAME}</b> {__version__}<br>Lexicographie et documentation des langues.<br>"
                            f"Projet : {self.projet.chemin}<br>{statut}<br><br>"
                            "Domaines sémantiques : SIL Global, <a href='https://semdom.org'>semdom.org</a>, "
                            "licence <a href='https://creativecommons.org/licenses/by-sa/4.0/deed.fr'>CC BY-SA 4.0</a>.")

    def _guide(self):
        from ..chemins import ressource
        from . import traduction
        try:
            chemin = ressource("aide", f"guide-{traduction.langue()}.html")
        except FileNotFoundError:
            chemin = ressource("aide", "guide-fr.html")
        QDesktopServices.openUrl(QUrl.fromLocalFile(chemin))

    def _langue_interface(self):
        from PySide6.QtWidgets import QInputDialog
        from . import traduction
        noms = list(traduction.LANGUES.values())
        actuelle = list(traduction.LANGUES).index(traduction.langue_enregistree())
        choix, ok = QInputDialog.getItem(self, "Langue de l'interface (Interface language)",
                                         "Langue / Language :", noms, actuelle, False)
        if not ok:
            return
        code = list(traduction.LANGUES)[noms.index(choix)]
        traduction.enregistrer_langue(code)
        info(self, "Langue de l'interface (Interface language)",
             "La nouvelle langue sera utilisée au prochain démarrage du logiciel.\n"
             "The new language will be used the next time the program starts.")

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
        page = self.pages[index][1]
        # une page n'est recalculée que si les données ont changé depuis son dernier affichage
        if getattr(page, "perime", True):
            page.rafraichir()
            page.perime = False

    def _importer_bible(self):
        from PySide6.QtWidgets import QFileDialog, QInputDialog
        from .. import usfm
        forme, ok = QInputDialog.getItem(self, "Bible complète", "La Bible est fournie sous forme de :",
                                         ["archive .zip", "dossier"], 0, False)
        if not ok:
            return
        if forme == "dossier":
            chemin = QFileDialog.getExistingDirectory(self, "Dossier de la Bible (USFM ou USX)")
        else:
            chemin, _ = QFileDialog.getOpenFileName(self, "Archive de la Bible", "", "Archive (*.zip)")
        if not chemin:
            return
        langues = [f"{self.projet.reglage('langue_vern_nom') or 'langue documentée'} (langue du projet)",
                   f"{self.projet.reglage('langue_analyse_nom') or 'langue d’analyse'} (traduction)"]
        cote, ok = QInputDialog.getItem(self, "Bible complète", "Cette Bible est en :", langues, 1, False)
        if not ok:
            return
        try:
            self.projet.sauvegarde_automatique()
            with CurseurAttente():
                livres = usfm.lire_bible(chemin)
                if not livres:
                    raise ValueError("Aucun livre USFM (.usfm, .sfm) ni USX (.usx) trouvé à cet endroit.")
                nouveaux = completes = 0
                with self.projet.en_lot():
                    for code, versets in livres.items():
                        n, c = usfm.importer(self.projet, versets, "vernaculaire" if cote == langues[0] else "analyse",
                                             os.path.basename(chemin.rstrip("/\\")))
                        nouveaux, completes = nouveaux + n, completes + c
                alignement.recalculer(self.projet)
        except Exception as e:
            erreur(self, "Bible complète", "L'import n'a pas abouti. Le projet a été sauvegardé juste avant.", e)
            return
        self.rafraichir_tout()
        paires = self.projet.conn.execute("SELECT COUNT(*) FROM phrases WHERE vernaculaire IS NOT NULL "
                                          "AND analyse IS NOT NULL").fetchone()[0]
        info(self, "Bible complète", f"{len(livres)} livre(s), {nouveaux + completes} versets "
                                     f"({nouveaux} nouveaux, {completes} complétés).\n"
                                     f"Le corpus compte {paires} phrase(s) dans les deux langues.")

    def _importer_dictionnaire(self):
        from PySide6.QtWidgets import QInputDialog
        from .. import dico_imprime
        chemin, _ = QFileDialog.getOpenFileName(self, "Dictionnaire imprimé", "",
                                                "Word ou texte (*.docx *.txt);;Tous les fichiers (*)")
        if not chemin:
            return
        source, ok = QInputDialog.getText(
            self, "Dictionnaire imprimé", "Auteurs, titre et année (notés sur chaque exemple et entrée créée) :",
            text=os.path.splitext(os.path.basename(chemin))[0])
        if not ok or not source.strip():
            return
        try:
            with CurseurAttente():
                lecture = dico_imprime.lire(chemin)
                if not lecture.articles:
                    raise ValueError("Aucun article reconnu : une ligne de vedette suivie d'une ligne qui commence "
                                     "par une catégorie (N, V, VT, AV…).")
                simulation = dico_imprime.fusionner(self.projet, lecture, source.strip(), simulation=True)
        except Exception as e:
            erreur(self, "Dictionnaire imprimé", "Le fichier n'a pas pu être lu.", e)
            return
        n = lecture.compter()
        texte = (f"Lu : {n['articles']} articles, {n['sens']} sens, {n['exemples']} exemples, "
                 f"{n['expressions']} expressions ; {len(lecture.avertissements)} passage(s) non reconnu(s) "
                 f"(gardés en note ou ignorés).\n\n{simulation.resume()}\n\n"
                 "Rien n'est supprimé, et le projet est sauvegardé avant. Importer ?")
        if not confirmer(self, "Dictionnaire imprimé", texte):
            return
        try:
            sauvegarde = self.projet.sauvegarde_automatique()
            with CurseurAttente():
                rapport = dico_imprime.fusionner(self.projet, lecture, source.strip())
        except Exception as e:
            erreur(self, "Dictionnaire imprimé", "L'import n'a pas abouti. Le projet a été sauvegardé juste avant.", e)
            return
        self.rafraichir_tout()
        info(self, "Dictionnaire imprimé", f"{rapport.resume()}\n\nSauvegarde d'avant l'import :\n{sauvegarde}")

    def _fusionner(self):
        from PySide6.QtWidgets import QFileDialog
        from .. import fusion
        from ..projet import EXTENSION
        chemin, _ = QFileDialog.getOpenFileName(self, "Projet d'un autre poste", "", f"Projet (*{EXTENSION})")
        if not chemin:
            return
        try:
            self.projet.sauvegarde_automatique()
            with CurseurAttente():
                rapport = fusion.fusionner(self.projet, chemin)
        except Exception as e:
            erreur(self, "Fusion", "La fusion n'a pas abouti. Le projet a été sauvegardé juste avant.", e)
            return
        self.rafraichir_tout()
        info(self, "Fusion", rapport.resume())

    def _importer_paratext(self):
        if importer_paratext(self, self.projet):
            self.rafraichir_tout()

    def ouvrir_entree(self, entree_id):
        """Affiche une entrée dans la page Lexique."""
        lexique_page = dict(self.pages)["Lexique"]
        self.navigation.setCurrentRow([nom for nom, _ in self.pages].index("Lexique"))
        if self.pile.currentWidget() is lexique_page:
            lexique_page.ouvrir_entree(entree_id)

    def _aller(self, nom):
        self.navigation.setCurrentRow([n for n, _ in self.pages].index(nom))
        page = dict(self.pages)[nom]
        return page if self.pile.currentWidget() is page else None

    def voir_concordance(self, forme):
        page = self._aller("Concordance")
        if page:
            page.chercher_forme(forme)

    def ouvrir_phrase(self, ref):
        page = self._aller("Textes")
        if page:
            page.ouvrir_phrase(ref)

    def rafraichir_tout(self):
        # seule la page visible est recalculée ; les autres sont marquées périmées et le seront
        # quand on les affichera (_changer_page)
        for _, page in self.pages:
            page.perime = True
        courante = self.pile.currentWidget()
        courante.rafraichir()
        courante.perime = False

    def _reglages(self):
        d = DialogueReglages(self.projet, self)
        if d.exec():
            if d.decoupage_modifie:
                with CurseurAttente():
                    alignement.recalculer(self.projet)
            for _, page in self.pages:
                if hasattr(page, "editeur"):
                    page.editeur.appliquer_police()
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

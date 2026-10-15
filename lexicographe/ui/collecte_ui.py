"""Collecte communautaire (inspiré de WeSay) : collecte par domaine, tâches de complément,
enregistrement audio, mode locuteur en plein écran."""

import os
from datetime import datetime

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QInputDialog,
                               QLabel, QLineEdit, QListWidget, QPushButton, QScrollArea, QStackedWidget, QVBoxLayout,
                               QWidget)

from .. import collecte, domaines, lexique
from .commun import carte, confirmer, erreur, info
from .domaines_ui import DialogueDomaine
from .pages import Page


class Enregistreur(QWidget):
    """Enregistre un son (WAV) avec le micro de l'ordinateur et le lie à une entrée.
    Signal `enregistre(chemin)` quand un fichier est prêt."""
    enregistre = Signal(str)

    def __init__(self, projet, parent=None):
        super().__init__(parent)
        self.projet = projet
        self.entree_id = None
        self._session = self._recorder = self._lecteur = None
        self.dernier = None
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        self.btn = QPushButton("● Enregistrer")
        self.btn.clicked.connect(self._basculer)
        self.btn_ecouter = QPushButton("▶ Écouter")
        self.btn_ecouter.clicked.connect(self._ecouter)
        self.btn_ecouter.setEnabled(False)
        self.etat = QLabel("")
        self.etat.setObjectName("sousTitre")
        h.addWidget(self.btn)
        h.addWidget(self.btn_ecouter)
        h.addWidget(self.etat, 1)

    def pour_entree(self, entree_id):
        self.arreter()
        self.entree_id = entree_id
        medias = [m for m in lexique.medias_de(self.projet.conn, entree_id) if m[2] == "prononciation"] \
            if entree_id else []
        self.dernier = medias[-1][5] if medias else None
        self.btn_ecouter.setEnabled(bool(self.dernier and os.path.isfile(self.dernier)))
        self.etat.setText(f"{len(medias)} enregistrement(s)" if medias else "pas encore d'enregistrement")

    def _initialiser(self):
        from PySide6.QtMultimedia import (QAudioInput, QMediaCaptureSession, QMediaDevices, QMediaFormat,
                                          QMediaRecorder)
        if not QMediaDevices.audioInputs():
            raise RuntimeError("Aucun micro n'est branché ou autorisé sur cet ordinateur.")
        self._session = QMediaCaptureSession(self)
        self._session.setAudioInput(QAudioInput(self))
        self._recorder = QMediaRecorder(self)
        self._session.setRecorder(self._recorder)
        fmt = QMediaFormat()
        fmt.setFileFormat(QMediaFormat.Wave)
        self._recorder.setMediaFormat(fmt)
        self._recorder.recorderStateChanged.connect(self._etat_change)
        self._recorder.errorOccurred.connect(lambda _e, texte: erreur(self, "Enregistrement", texte))

    def _basculer(self):
        if self._recorder is not None and self._recorder.recorderState() == self._recorder.RecordingState:
            self.arreter()
            return
        if not self.entree_id:
            erreur(self, "Enregistrement", "Enregistre d'abord le mot, puis sa prononciation.")
            return
        try:
            if self._recorder is None:
                self._initialiser()
        except Exception as e:
            erreur(self, "Enregistrement", "L'enregistrement n'est pas possible sur cet ordinateur.", e)
            return
        os.makedirs(self.projet.dossier_medias, exist_ok=True)
        forme = lexique.lire_entree(self.projet.conn, self.entree_id).forme
        nom = "".join(c for c in forme if c.isalnum() or c in "-_") or "mot"
        self._fichier = os.path.join(self.projet.dossier_medias,
                                     f"{nom}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.wav")
        self._recorder.setOutputLocation(QUrl.fromLocalFile(self._fichier))
        self._recorder.record()
        self.btn.setText("■ Arrêter")
        self.etat.setText("enregistrement en cours… parle maintenant")

    def arreter(self):
        if self._recorder is not None and self._recorder.recorderState() == self._recorder.RecordingState:
            self._recorder.stop()

    def _etat_change(self, etat):
        if etat == self._recorder.StoppedState:
            self.btn.setText("● Enregistrer")
            chemin = self._recorder.actualLocation().toLocalFile() or self._fichier
            if chemin and os.path.isfile(chemin) and self.entree_id:
                lexique.lier_media(self.projet.conn, self.entree_id, chemin, "prononciation", "enregistré dans la collecte")
                self.dernier = chemin
                self.btn_ecouter.setEnabled(True)
                self.etat.setText("enregistré ✓")
                self.enregistre.emit(chemin)

    def _ecouter(self):
        if not self.dernier:
            return
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        if self._lecteur is None:
            self._sortie = QAudioOutput(self)
            self._lecteur = QMediaPlayer(self)
            self._lecteur.setAudioOutput(self._sortie)
        self._lecteur.setSource(QUrl.fromLocalFile(self.dernier))
        self._lecteur.play()


class _Grand(QLabel):
    def __init__(self, texte="", facteur=1.6, gras=True):
        super().__init__(texte)
        police = QFont(self.font())
        police.setPointSizeF(police.pointSizeF() * facteur)
        police.setBold(gras)
        self.setFont(police)
        self.setWordWrap(True)


class CollecteDomaine(QWidget):
    """Une question d'un domaine à la fois ; chaque mot tapé devient une entrée classée."""
    retour = Signal()
    modifie = Signal()

    def __init__(self, projet, parent=None):
        super().__init__(parent)
        self.projet = projet
        self.questions = []
        self.index = 0
        v = QVBoxLayout(self)
        haut = QHBoxLayout()
        retour = QPushButton("← Tâches")
        retour.clicked.connect(self.retour)
        aller = QPushButton("Aller à un domaine…")
        aller.clicked.connect(self._aller)
        self.position = QLabel("")
        self.position.setObjectName("sousTitre")
        haut.addWidget(retour)
        haut.addWidget(aller)
        haut.addStretch()
        haut.addWidget(self.position)
        v.addLayout(haut)
        self.domaine = _Grand("", 1.3)
        self.description = QLabel("")
        self.description.setWordWrap(True)
        self.description.setObjectName("sousTitre")
        self.question = _Grand("", 1.6)
        self.exemples = QLabel("")
        self.exemples.setWordWrap(True)
        for w in (self.domaine, self.description, self.question, self.exemples):
            v.addWidget(w)
        saisie = QGridLayout()
        self.mot = QLineEdit()
        self.mot.setPlaceholderText("mot dans la langue")
        self.glose = QLineEdit()
        self.glose.setPlaceholderText("sens en français (facultatif)")
        for champ in (self.mot, self.glose):
            police = QFont(champ.font())
            police.setPointSizeF(police.pointSizeF() * 1.5)
            champ.setFont(police)
            champ.returnPressed.connect(self._ajouter)
        ajouter = QPushButton("Ajouter")
        ajouter.setObjectName("principal")
        ajouter.clicked.connect(self._ajouter)
        saisie.addWidget(self.mot, 0, 0)
        saisie.addWidget(self.glose, 0, 1)
        saisie.addWidget(ajouter, 0, 2)
        v.addLayout(saisie)
        self.enregistreur = Enregistreur(projet)
        v.addWidget(self.enregistreur)
        v.addWidget(QLabel("<b>Mots déjà donnés pour ce domaine</b>"))
        self.liste = QListWidget()
        police = QFont(self.liste.font())
        police.setPointSizeF(police.pointSizeF() * 1.3)
        self.liste.setFont(police)
        v.addWidget(self.liste, 1)
        nav = QHBoxLayout()
        for texte, pas in (("◀ Question précédente", -1), ("Question suivante ▶", 1)):
            b = QPushButton(texte)
            b.clicked.connect(lambda _=False, p=pas: self._aller_a(self.index + p))
            nav.addWidget(b)
        v.addLayout(nav)

    def demarrer(self):
        langue = self.projet.reglage("langue_analyse_code") or "fr"
        self.questions = collecte.questions(self.projet.conn, langue)
        if not self.questions:
            erreur(self, "Collecte", "Aucune liste de domaines sémantiques dans ce projet : importe-la d'abord "
                                     "(page Imports > Liste de domaines sémantiques).")
            self.retour.emit()
            return
        pos = collecte.position_enregistree(self.projet)
        self.index = next((i for i, q in enumerate(self.questions)
                           if q.guid == pos.get("guid") and q.numero == pos.get("numero")), 0)
        self._afficher()

    def _aller_a(self, index):
        if self.questions:
            self.index = max(0, min(index, len(self.questions) - 1))
            self._afficher()

    def _aller(self):
        d = DialogueDomaine(self.projet, self)
        if d.exec() and d.guid:
            self._aller_a(next((i for i, q in enumerate(self.questions) if q.guid == d.guid), self.index))

    def _afficher(self):
        q = self.questions[self.index]
        collecte.enregistrer_position(self.projet, q.guid, q.numero)
        self.position.setText(f"question {self.index + 1} sur {len(self.questions)}")
        self.domaine.setText(f"{q.code}  {q.nom}")
        self.description.setText(q.description)
        texte = q.texte if q.total <= 1 else q.texte
        self.question.setText(texte)
        self.exemples.setText(f"Exemples en français : {q.mots_exemples}" if q.mots_exemples else "")
        self._mots()
        self.enregistreur.pour_entree(None)
        self.mot.setFocus()

    def _mots(self):
        self.liste.clear()
        for _, forme, glose in collecte.mots_du_domaine(self.projet.conn, self.questions[self.index].guid):
            self.liste.addItem(f"{forme}" + (f"  —  {glose}" if glose else ""))

    def _ajouter(self):
        if not self.mot.text().strip():
            return
        try:
            eid, _ = collecte.ajouter_mot(self.projet.conn, self.questions[self.index].guid, self.mot.text(),
                                          self.glose.text())
        except ValueError as e:
            erreur(self, "Collecte", str(e))
            return
        self.mot.clear()
        self.glose.clear()
        self._mots()
        self.enregistreur.pour_entree(eid)
        self.mot.setFocus()
        self.modifie.emit()


class TacheFiche(QWidget):
    """Une entrée à la fois, avec seulement le champ que la tâche demande de remplir."""
    retour = Signal()
    modifie = Signal()

    def __init__(self, projet, parent=None):
        super().__init__(parent)
        self.projet = projet
        self.tache = None
        self.ids = []
        self.index = 0
        v = QVBoxLayout(self)
        haut = QHBoxLayout()
        retour = QPushButton("← Tâches")
        retour.clicked.connect(self.retour)
        self.titre = QLabel("")
        self.titre.setStyleSheet("font-weight: 600;")
        self.position = QLabel("")
        self.position.setObjectName("sousTitre")
        haut.addWidget(retour)
        haut.addWidget(self.titre)
        haut.addStretch()
        haut.addWidget(self.position)
        v.addLayout(haut)
        self.forme = _Grand("", 2.4)
        self.contexte = QLabel("")
        self.contexte.setWordWrap(True)
        v.addWidget(self.forme)
        v.addWidget(self.contexte)
        self.consigne = _Grand("", 1.3, gras=False)
        v.addWidget(self.consigne)
        self.champ = QLineEdit()
        self.champ2 = QLineEdit()
        for champ in (self.champ, self.champ2):
            police = QFont(champ.font())
            police.setPointSizeF(police.pointSizeF() * 1.5)
            champ.setFont(police)
            champ.returnPressed.connect(self._valider)
            v.addWidget(champ)
        self.btn_domaine = QPushButton("Choisir le domaine…")
        self.btn_domaine.clicked.connect(self._choisir_domaine)
        v.addWidget(self.btn_domaine, 0, Qt.AlignLeft)
        self.enregistreur = Enregistreur(projet)
        self.enregistreur.enregistre.connect(lambda _: self._suivant(apres_enregistrement=True))
        v.addWidget(self.enregistreur)
        v.addStretch()
        nav = QHBoxLayout()
        passer = QPushButton("Passer →")
        passer.clicked.connect(self._passer)
        self.btn_valider = QPushButton("Enregistrer et continuer")
        self.btn_valider.setObjectName("principal")
        self.btn_valider.clicked.connect(self._valider)
        nav.addWidget(passer)
        nav.addStretch()
        nav.addWidget(self.btn_valider)
        v.addLayout(nav)

    def demarrer(self, tache):
        self.tache = tache
        self.ids = collecte.a_faire(self.projet.conn, tache)
        self.index = 0
        self.titre.setText(collecte.TACHES[tache][0])
        self._afficher()

    def _afficher(self):
        t = self.tache
        for w in (self.champ, self.champ2, self.btn_domaine, self.enregistreur, self.btn_valider):
            w.setVisible(False)
        if self.index >= len(self.ids):
            self.forme.setText("Terminé ✓")
            self.contexte.setText("Il n'y a plus rien à faire pour cette tâche.")
            self.consigne.setText("")
            self.position.setText("")
            return
        e = lexique.lire_entree(self.projet.conn, self.ids[self.index])
        self.position.setText(f"{self.index + 1} sur {len(self.ids)}")
        self.forme.setText(e.tete)
        sens = collecte.sens_concerne(e, t)
        details = []
        if sens and sens.glose:
            details.append(f"sens : {sens.glose}")
        if sens and sens.exemples:
            details.append(f"exemple : {sens.exemples[0].vernaculaire}")
        self.contexte.setText("   ·   ".join(details))
        if t == "glose":
            self.consigne.setText("Que veut dire ce mot en français ?")
            self.champ.setPlaceholderText("sens en français")
            self.champ.setVisible(True)
        elif t == "exemple":
            self.consigne.setText("Donne une phrase avec ce mot, puis sa traduction.")
            self.champ.setPlaceholderText("phrase dans la langue")
            self.champ2.setPlaceholderText("traduction en français")
            self.champ.setVisible(True)
            self.champ2.setVisible(True)
        elif t == "domaine":
            self.consigne.setText("Dans quel domaine ranger ce mot ?")
            self.btn_domaine.setVisible(True)
        else:
            self.consigne.setText("Enregistre la prononciation de ce mot.")
            self.enregistreur.setVisible(True)
            self.enregistreur.pour_entree(e.id)
        self.btn_valider.setVisible(t in ("glose", "exemple"))
        for champ in (self.champ, self.champ2):
            champ.clear()
        self.champ.setFocus()

    def _valider(self):
        if self.index >= len(self.ids):
            return
        valeur = self.champ.text() if self.tache == "glose" else (self.champ.text(), self.champ2.text())
        if collecte.completer(self.projet.conn, self.ids[self.index], self.tache, valeur):
            self.modifie.emit()
            self._suivant()

    def _choisir_domaine(self):
        d = DialogueDomaine(self.projet, self)
        if d.exec() and d.guid and collecte.completer(self.projet.conn, self.ids[self.index], "domaine", d.guid):
            self.modifie.emit()
            self._suivant()

    def _suivant(self, apres_enregistrement=False):
        if apres_enregistrement:
            self.modifie.emit()
        self.index += 1
        self._afficher()

    def _passer(self):
        self.enregistreur.arreter()
        self.index += 1
        self._afficher()


class CollecteListe(QWidget):
    """Un mot de la liste à la fois (langue d'analyse) ; le mot donné dans la langue devient une entrée."""
    retour = Signal()
    modifie = Signal()

    def __init__(self, projet, parent=None):
        super().__init__(parent)
        self.projet = projet
        self.elements = []
        self.index = 0
        self.index_gloses = {}
        v = QVBoxLayout(self)
        haut = QHBoxLayout()
        retour = QPushButton("← Tâches")
        retour.clicked.connect(self.retour)
        self.choix = QComboBox()
        self.choix.setMinimumWidth(220)
        self.choix.currentTextChanged.connect(self._changer_liste)
        importer = QPushButton("Importer une liste…")
        importer.clicked.connect(self._importer)
        self.retirer = QPushButton("Retirer la liste")
        self.retirer.clicked.connect(self._retirer)
        self.position = QLabel("")
        self.position.setObjectName("sousTitre")
        for w in (retour, QLabel("Liste :"), self.choix, importer, self.retirer):
            haut.addWidget(w)
        haut.addStretch()
        haut.addWidget(self.position)
        v.addLayout(haut)
        self.groupe = QLabel("")
        self.groupe.setObjectName("sousTitre")
        self.mot_liste = _Grand("", 2.4)
        self.connus = QLabel("")
        self.connus.setWordWrap(True)
        self.consigne = _Grand("", 1.3, gras=False)
        for w in (self.groupe, self.mot_liste, self.connus, self.consigne):
            v.addWidget(w)
        saisie = QHBoxLayout()
        self.mot = QLineEdit()
        self.mot.setPlaceholderText("mot dans la langue")
        police = QFont(self.mot.font())
        police.setPointSizeF(police.pointSizeF() * 1.5)
        self.mot.setFont(police)
        self.mot.returnPressed.connect(self._ajouter)
        self.btn_ajouter = QPushButton("Ajouter")
        self.btn_ajouter.setObjectName("principal")
        self.btn_ajouter.clicked.connect(self._ajouter)
        saisie.addWidget(self.mot, 1)
        saisie.addWidget(self.btn_ajouter)
        v.addLayout(saisie)
        self.enregistreur = Enregistreur(projet)
        v.addWidget(self.enregistreur)
        v.addStretch()
        nav = QHBoxLayout()
        for texte, action in (("◀ Mot précédent", lambda: self._aller_a(self.index - 1)),
                              ("Mot suivant ▶", lambda: self._aller_a(self.index + 1)),
                              ("Prochain mot non trouvé ▶▶", self._prochain_manquant)):
            b = QPushButton(texte)
            b.clicked.connect(action)
            nav.addWidget(b)
        v.addLayout(nav)

    def demarrer(self, nom=None):
        noms = list(collecte.listes(self.projet))
        self.choix.blockSignals(True)
        self.choix.clear()
        self.choix.addItems(noms)
        self.choix.blockSignals(False)
        if nom in noms:
            self.choix.setCurrentText(nom)
        self._changer_liste(self.choix.currentText())

    def _changer_liste(self, nom):
        self.elements = collecte.listes(self.projet).get(nom, [])
        self.index_gloses = collecte.index_des_gloses(self.projet.conn)
        self.index = min(collecte.position_liste(self.projet, nom), max(0, len(self.elements) - 1))
        self.retirer.setEnabled(bool(nom))
        self._afficher()

    def _afficher(self):
        nom = self.choix.currentText()
        actifs = bool(self.elements)
        for w in (self.mot, self.btn_ajouter):
            w.setEnabled(actifs)
        if not actifs:
            self.mot_liste.setText("Aucune liste")
            self.groupe.setText("")
            self.connus.setText("Importe une liste de mots (Word ou texte) : une ligne ou une rangée de tableau "
                                "par mot, par exemple « 1 ⇥ eau ».")
            self.consigne.setText("")
            self.position.setText("")
            self.enregistreur.pour_entree(None)
            return
        e = self.elements[self.index]
        collecte.enregistrer_position_liste(self.projet, nom, self.index)
        trouves = sum(1 for x in self.elements if collecte.trouves(self.projet.conn, x.mot, self.index_gloses))
        self.position.setText(f"mot {self.index + 1} sur {len(self.elements)} · {trouves} trouvé(s)")
        self.groupe.setText(e.groupe)
        self.mot_liste.setText(e.mot)
        deja = collecte.trouves(self.projet.conn, e.mot, self.index_gloses)
        self.connus.setText("Déjà dans le lexique : " + ", ".join(f for _, f in deja) if deja
                            else "Pas encore dans le lexique.")
        langue = self.projet.reglage("langue_vern_nom") or "la langue"
        self.consigne.setText(f"Comment dit-on « {e.mot} » en {langue} ?")
        self.enregistreur.pour_entree(deja[0][0] if deja else None)
        self.mot.clear()
        self.mot.setFocus()

    def _aller_a(self, index):
        if self.elements:
            self.enregistreur.arreter()
            self.index = max(0, min(index, len(self.elements) - 1))
            self._afficher()

    def _prochain_manquant(self):
        for i in list(range(self.index + 1, len(self.elements))) + list(range(0, self.index + 1)):
            if not collecte.trouves(self.projet.conn, self.elements[i].mot, self.index_gloses):
                self._aller_a(i)
                return
        info(self, "Liste de mots", "Tous les mots de cette liste sont trouvés ✓")

    def _ajouter(self):
        if not self.elements or not self.mot.text().strip():
            return
        try:
            eid, _ = collecte.repondre_liste(self.projet.conn, self.elements[self.index], self.mot.text(),
                                             self.choix.currentText())
        except ValueError as e:
            erreur(self, "Liste de mots", str(e))
            return
        self.index_gloses = collecte.index_des_gloses(self.projet.conn)
        self.modifie.emit()
        self._afficher()
        self.enregistreur.pour_entree(eid)

    def _importer(self):
        chemin, _ = QFileDialog.getOpenFileName(self, "Liste de mots", "",
                                                "Word ou texte (*.docx *.txt *.csv);;Tous les fichiers (*)")
        if not chemin:
            return
        try:
            elements = collecte.lire_liste(chemin)
        except Exception as e:
            erreur(self, "Liste de mots", "La liste n'a pas pu être lue.", e)
            return
        if not elements:
            erreur(self, "Liste de mots", "Aucun mot trouvé dans ce fichier.")
            return
        nom, ok = QInputDialog.getText(self, "Liste de mots", f"{len(elements)} mot(s). Nom de la liste :",
                                       text=os.path.splitext(os.path.basename(chemin))[0].strip())
        if not ok or not nom.strip():
            return
        collecte.enregistrer_liste(self.projet, nom.strip(), elements)
        self.demarrer(nom.strip())

    def _retirer(self):
        nom = self.choix.currentText()
        if nom and confirmer(self, "Liste de mots", f"Retirer la liste « {nom} » ? Les mots déjà collectés "
                                                    "restent dans le lexique."):
            collecte.supprimer_liste(self.projet, nom)
            self.demarrer()


class Collecte(QWidget):
    """Accueil des tâches + écrans de collecte (réutilisé par le mode locuteur)."""
    modifie = Signal()

    def __init__(self, projet, parent=None):
        super().__init__(parent)
        self.projet = projet
        racine = QVBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        self.pile = QStackedWidget()
        racine.addWidget(self.pile)

        accueil = QWidget()
        grille = QGridLayout(accueil)
        self.cartes = {}
        taches = [("domaine_collecte", "Collecter des mots par domaine",
                   "Une question à la fois (« Quels mots désignent les parties du corps ? ») ; chaque mot donné "
                   "devient une entrée classée dans ce domaine."),
                  ("liste_collecte", "Collecter à partir d'une liste de mots",
                   "Un mot français à la fois (« eau », « feu », « lion »…) : le locuteur donne le mot dans sa "
                   "langue. Les mots déjà présents dans le lexique sont montrés.")] + \
                 [(t, nom, aide) for t, (nom, aide) in collecte.TACHES.items()]
        for i, (cle, nom, aide) in enumerate(taches):
            c = carte()
            cv = QVBoxLayout(c)
            cv.addWidget(_Grand(nom, 1.2))
            a = QLabel(aide)
            a.setWordWrap(True)
            a.setObjectName("sousTitre")
            cv.addWidget(a)
            compte = QLabel("")
            cv.addWidget(compte)
            b = QPushButton("Commencer")
            b.setObjectName("principal")
            b.clicked.connect(lambda _=False, k=cle: self.commencer(k))
            cv.addWidget(b, 0, Qt.AlignLeft)
            grille.addWidget(c, i // 2, i % 2)
            self.cartes[cle] = compte
        grille.setRowStretch(grille.rowCount(), 1)
        # l'accueil défile quand la fenêtre est basse : les cartes ne sont jamais écrasées
        defilement = QScrollArea()
        defilement.setWidgetResizable(True)
        defilement.setFrameShape(QFrame.NoFrame)
        defilement.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        accueil.setObjectName("accueilCollecte")
        defilement.setStyleSheet("QScrollArea, #accueilCollecte { background: transparent; }")
        defilement.setWidget(accueil)
        self.pile.addWidget(defilement)
        self.par_domaine = CollecteDomaine(projet)
        self.fiche = TacheFiche(projet)
        self.par_liste = CollecteListe(projet)
        for ecran in (self.par_domaine, self.fiche, self.par_liste):
            ecran.retour.connect(self.accueil)
            ecran.modifie.connect(self.modifie)
            self.pile.addWidget(ecran)

    def accueil(self):
        for ecran in (self.par_domaine, self.fiche, self.par_liste):
            ecran.enregistreur.arreter()
        comptes = collecte.compter(self.projet.conn)
        nb_dom = domaines.nombre(self.projet.conn)
        self.cartes["domaine_collecte"].setText(f"{nb_dom} domaines" if nb_dom else
                                                "aucune liste de domaines dans ce projet")
        les_listes = collecte.listes(self.projet)
        if les_listes:
            total = sum(len(els) for els in les_listes.values())
            trouves = sum(collecte.avancement(self.projet.conn, els) for els in les_listes.values())
            self.cartes["liste_collecte"].setText(f"{len(les_listes)} liste(s) : {trouves} mot(s) trouvé(s) "
                                                  f"sur {total}")
        else:
            self.cartes["liste_collecte"].setText("aucune liste : importe-la depuis cet écran")
        for t, n in comptes.items():
            self.cartes[t].setText(f"{n} à faire" if n else "rien à faire ✓")
        self.pile.setCurrentIndex(0)

    def commencer(self, cle):
        if cle == "domaine_collecte":
            self.pile.setCurrentWidget(self.par_domaine)
            self.par_domaine.demarrer()
        elif cle == "liste_collecte":
            self.pile.setCurrentWidget(self.par_liste)
            self.par_liste.demarrer()
        else:
            self.pile.setCurrentWidget(self.fiche)
            self.fiche.demarrer(cle)


class ModeLocuteur(QDialog):
    """Collecte en plein écran, gros caractères, sans les menus du logiciel."""

    def __init__(self, projet, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Collecte — mode locuteur")
        police = QFont(self.font())
        police.setPointSizeF(police.pointSizeF() * 1.25)
        self.setFont(police)
        v = QVBoxLayout(self)
        haut = QHBoxLayout()
        titre = _Grand(f"Collecte de mots — {projet.reglage('langue_vern_nom') or projet.nom}", 1.3)
        quitter = QPushButton("Quitter le mode locuteur")
        quitter.clicked.connect(self.accept)
        haut.addWidget(titre, 1)
        haut.addWidget(quitter)
        v.addLayout(haut)
        ligne = QFrame()
        ligne.setFrameShape(QFrame.HLine)
        v.addWidget(ligne)
        self.collecte = Collecte(projet)
        v.addWidget(self.collecte, 1)
        self.collecte.accueil()

    def done(self, code):
        self.collecte.accueil()   # arrête un enregistrement en cours
        super().done(code)


class PageCollecte(Page):
    def __init__(self, projet):
        super().__init__(projet, "Collecte",
                         "Pour travailler avec des locuteurs : collecte guidée par les questions des domaines "
                         "sémantiques, et tâches pour compléter le lexique un mot à la fois. Les mots collectés "
                         "sont des brouillons, à vérifier dans le Lexique.")
        ligne = QHBoxLayout()
        locuteur = QPushButton("Ouvrir en mode locuteur (plein écran)")
        locuteur.clicked.connect(self._mode_locuteur)
        ligne.addStretch()
        ligne.addWidget(locuteur)
        self.racine.addLayout(ligne)
        self.collecte = Collecte(projet)
        self.collecte.modifie.connect(self._modifie)
        self.racine.addWidget(self.collecte, 1)

    def _modifie(self):
        # les autres pages seront recalculées ; celle-ci garde l'écran en cours
        self._sans_rafraichir = True
        self.donnees_modifiees.emit()
        self._sans_rafraichir = False

    def rafraichir(self):
        if getattr(self, "_sans_rafraichir", False):
            return
        if self.collecte.pile.currentIndex() == 0:
            self.collecte.accueil()

    def _mode_locuteur(self):
        d = ModeLocuteur(self.projet, self)
        d.showFullScreen()
        d.exec()
        self.donnees_modifiees.emit()
        self.collecte.accueil()

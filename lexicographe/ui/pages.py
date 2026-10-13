"""Pages de la fenêtre principale. Chaque page a une méthode `rafraichir()` et
émet `donnees_modifiees` quand elle change le projet."""

import json
import os
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QGridLayout, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
                               QTextBrowser, QVBoxLayout, QWidget, QDialog, QDialogButtonBox)

from .. import alignement, exports, lexique, usfm
from ..lexique import Entree, Exemple, Sens
from ..projet import copier_medias
from .commun import CurseurAttente, carte, confirmer, erreur, info, surligner, titre
from .editeur_entree import EditeurEntree


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
            grille.addWidget(c, 0, i)
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
        self.editeur.charger_entree(Entree(forme=forme, sens=[sens]))

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
class PageLexique(Page):
    def __init__(self, projet):
        super().__init__(projet, "Lexique")
        separateur = QSplitter(Qt.Horizontal)

        gauche = QWidget()
        gl = QVBoxLayout(gauche)
        gl.setContentsMargins(0, 0, 0, 0)
        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Rechercher une forme ou une glose…")
        self.recherche.setClearButtonEnabled(True)
        self.recherche.textChanged.connect(self.rafraichir)
        gl.addWidget(self.recherche)
        self.liste = _table(["Forme", "Glose(s)", "Catégorie"], etirer=(1,))
        self.liste.itemSelectionChanged.connect(self._selection)
        gl.addWidget(self.liste)
        bas = QHBoxLayout()
        nouvelle = QPushButton("+ Nouvelle entrée")
        nouvelle.clicked.connect(self._nouvelle)
        self.compte = QLabel("")
        self.compte.setObjectName("sousTitre")
        bas.addWidget(nouvelle)
        bas.addStretch()
        bas.addWidget(self.compte)
        gl.addLayout(bas)
        separateur.addWidget(gauche)

        self.editeur = EditeurEntree(projet)
        self.editeur.enregistree.connect(self._enregistree)
        self.editeur.supprimee.connect(self.donnees_modifiees)
        separateur.addWidget(self.editeur)
        separateur.setSizes([340, 640])
        self.racine.addWidget(separateur, 1)
        self._selection_en_cours = False

    def rafraichir(self):
        courant = self.editeur.entree.id
        lignes = lexique.lister_entrees(self.projet.conn, self.recherche.text())
        self._selection_en_cours = True
        self.liste.setRowCount(len(lignes))
        for r, (eid, forme, gloses, cats, _) in enumerate(lignes):
            self.liste.setItem(r, 0, _item(forme, eid))
            self.liste.setItem(r, 1, _item(gloses))
            self.liste.setItem(r, 2, _item(cats))
            if eid == courant:
                self.liste.selectRow(r)
        self._selection_en_cours = False
        total = self.projet.conn.execute("SELECT COUNT(*) FROM entrees").fetchone()[0]
        self.compte.setText(f"{len(lignes)} / {total} entrées")
        if courant and not self.editeur.modifiee:
            self.editeur.charger(courant) if lexique.lire_entree(self.projet.conn, courant) else \
                self.editeur.charger_entree(None)

    def _selection(self):
        if self._selection_en_cours:
            return
        lignes = self.liste.selectionModel().selectedRows()
        if not lignes:
            return
        eid = self.liste.item(lignes[0].row(), 0).data(Qt.UserRole)
        if eid == self.editeur.entree.id:
            return
        if not self.editeur.demander_si_modifiee():
            return
        self.editeur.charger(eid)

    def _nouvelle(self):
        if not self.editeur.demander_si_modifiee():
            return
        self.liste.clearSelection()
        self.editeur.charger_entree(Entree(sens=[Sens()]))
        self.editeur.forme.setFocus()

    def _enregistree(self, _eid):
        self.donnees_modifiees.emit()

    def ouvrir_entree(self, eid):
        if self.editeur.demander_si_modifiee():
            self.recherche.clear()
            self.editeur.charger(eid)
            self.rafraichir()

    def peut_quitter(self):
        return self.editeur.demander_si_modifiee()


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

"""Fenêtre des doublons du lexique : groupes repérés par règle, choix de l'entrée à garder, fusion."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from .. import doublons, lexique
from .commun import CurseurAttente, confirmer, info


def _resume(conn, eid):
    e = lexique.lire_entree(conn, eid)
    gloses = " ; ".join(s.glose for s in e.sens if s.glose) or "—"
    exemples = sum(len(s.exemples) for s in e.sens)
    source = (e.notes.splitlines() or [""])[0][:40]
    return f"{e.tete} — {gloses} ({exemples} ex., {e.statut})" + (f" · {source}" if source else "")


class DialogueDoublons(QDialog):
    def __init__(self, projet, parent=None):
        super().__init__(parent)
        self.projet = projet
        self.modifie = False
        self._sauvegarde_faite = False
        self.setWindowTitle("Doublons du lexique")
        self.resize(980, 600)
        v = QVBoxLayout(self)
        aide = QLabel("Entrées de même forme (majuscules ignorées), de même type et avec au moins une glose "
                      "commune. Fusionner reporte tout sur l'entrée gardée (sens, exemples, photos, relations, "
                      "analyses) : rien n'est perdu. Même forme sans glose commune : homographes, non proposés.")
        aide.setWordWrap(True)
        aide.setObjectName("sousTitre")
        v.addWidget(aide)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Forme", "Entrées", "Garder"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self.table.setColumnWidth(2, 320)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        v.addWidget(self.table, 1)
        bas = QHBoxLayout()
        self.compte = QLabel("")
        un = QPushButton("Fusionner le groupe sélectionné")
        un.clicked.connect(self._fusionner_un)
        tous = QPushButton("Fusionner tous les groupes")
        tous.setObjectName("principal")
        tous.clicked.connect(self._fusionner_tous)
        fermer = QPushButton("Fermer")
        fermer.clicked.connect(self.accept)
        bas.addWidget(self.compte)
        bas.addStretch()
        for b in (un, tous, fermer):
            bas.addWidget(b)
        v.addLayout(bas)
        self._remplir()

    def _remplir(self):
        conn = self.projet.conn
        with CurseurAttente():
            self.groupes = doublons.candidats(conn)
        self.table.setRowCount(len(self.groupes))
        for i, g in enumerate(self.groupes):
            forme = QTableWidgetItem(g.forme)
            forme.setFlags(forme.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 0, forme)
            resumes = {eid: _resume(conn, eid) for eid in g.entrees}
            detail = QTableWidgetItem("\n".join(resumes.values()))
            detail.setFlags(detail.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 1, detail)
            choix = QComboBox()
            for eid, texte in resumes.items():
                choix.addItem(texte.split(" (")[0], eid)
            choix.setCurrentIndex(g.entrees.index(doublons.plus_complete(conn, g.entrees)))
            self.table.setCellWidget(i, 2, choix)
        self.table.resizeRowsToContents()
        self.compte.setText(f"{len(self.groupes)} groupe(s), "
                            f"{sum(len(g.entrees) - 1 for g in self.groupes)} entrée(s) en trop")

    def _sauvegarder(self):
        if not self._sauvegarde_faite:
            self.projet.sauvegarde_automatique()
            self._sauvegarde_faite = True

    def _fusionner_un(self):
        ligne = self.table.currentRow()
        if ligne < 0:
            return
        self._sauvegarder()
        garder = self.table.cellWidget(ligne, 2).currentData()
        doublons.fusionner_groupe(self.projet.conn, self.groupes[ligne], garder)
        self.modifie = True
        self._remplir()

    def _fusionner_tous(self):
        if not self.groupes or not confirmer(
                self, "Doublons", f"Fusionner les {len(self.groupes)} groupes, en gardant dans chacun l'entrée "
                                  "choisie dans la colonne « Garder » ? Le projet est sauvegardé avant."):
            return
        self._sauvegarder()
        choix = [self.table.cellWidget(i, 2).currentData() for i in range(len(self.groupes))]
        with CurseurAttente(), self.projet.en_lot():
            for g, garder in zip(self.groupes, choix):
                doublons.fusionner_groupe(self.projet.conn, g, garder)
        n = len(self.groupes)
        self.modifie = True
        self._remplir()
        info(self, "Doublons", f"{n} groupe(s) fusionné(s).")

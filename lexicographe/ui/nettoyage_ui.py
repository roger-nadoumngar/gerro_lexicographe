"""Retirer un signe (ton, accent) dans le lexique : choix du signe et des zones, aperçu, sauvegarde,
puis proposition de fusionner les mots devenus identiques."""

import unicodedata

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QPlainTextEdit,
                               QVBoxLayout)

from .. import clavier, controles, doublons
from .commun import CurseurAttente, confirmer, info

ZONES = [("mots", "Mots et variantes", True), ("exemples", "Phrases d'exemple", True),
         ("prononciations", "Prononciations", False),
         ("textes", "Textes en langue d'analyse qui citent des mots (gloses, définitions, traductions, notes)", False),
         ("corpus", "Phrases du corpus (versets, textes)", False)]


def nom_signe(signe):
    if signe in clavier.SIGNES:
        return clavier.SIGNES[signe][1]
    return unicodedata.name(signe, hex(ord(signe))).lower().replace("combining ", "")


class DialogueRetirerSigne(QDialog):
    def __init__(self, projet, parent=None):
        super().__init__(parent)
        self.projet = projet
        self.modifie = False
        self.setWindowTitle("Retirer un signe")
        self.setMinimumWidth(640)
        v = QVBoxLayout(self)
        aide = QLabel("Retire un signe (ton, accent…) sur toutes les lettres, par exemple quand l'orthographe "
                      "n'écrit plus le ton moyen : ā → a, l̄ → l. Les autres signes restent. Le projet est "
                      "sauvegardé avant.")
        aide.setWordWrap(True)
        aide.setObjectName("sousTitre")
        v.addWidget(aide)
        f = QFormLayout()
        self.signe = QComboBox()
        with CurseurAttente():
            presents = controles.signes_presents(projet.conn)
        self.signe.addItem("— choisir un signe —", None)   # rien n'est choisi d'office
        for signe, n in presents.most_common():
            self.signe.addItem(f"a{signe}  —  {nom_signe(signe)}  ({n})", signe)
        f.addRow("Signe :", self.signe)
        self.zones = {}
        for i, (cle, libelle, coche) in enumerate(ZONES):
            case = QCheckBox(libelle)
            case.setChecked(coche)
            case.toggled.connect(self._apercu)
            self.zones[cle] = case
            f.addRow("Où :" if i == 0 else "", case)
        v.addLayout(f)
        self.resume = QLabel("")
        v.addWidget(self.resume)
        self.exemples = QPlainTextEdit()
        self.exemples.setReadOnly(True)
        self.exemples.setFixedHeight(150)
        v.addWidget(self.exemples)
        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok = boutons.button(QDialogButtonBox.Ok)
        self.ok.setText("Retirer")
        boutons.accepted.connect(self._appliquer)
        boutons.rejected.connect(self.reject)
        v.addWidget(boutons)
        self.signe.currentIndexChanged.connect(self._apercu)
        self._apercu()

    def _champs(self):
        return [c for cle, case in self.zones.items() if case.isChecked() for c in controles.ZONES[cle]]

    def _apercu(self):
        signe = self.signe.currentData()
        self.occurrences = controles.retirer_signe(self.projet.conn, signe, self._champs()) if signe else []
        self.resume.setText(f"{len(self.occurrences)} texte(s) à corriger.")
        self.exemples.setPlainText("\n".join(f"{o.avant[:60]}  →  {o.apres[:60]}" for o in self.occurrences[:40]))
        self.ok.setEnabled(bool(self.occurrences))

    def _appliquer(self):
        if not self.occurrences or not confirmer(self, "Retirer un signe",
                                                  f"Corriger {len(self.occurrences)} texte(s) ? Le projet est "
                                                  "sauvegardé avant."):
            return
        self.projet.sauvegarde_automatique()
        with CurseurAttente():
            n = controles.corriger(self.projet.conn, self.occurrences)
            groupes = doublons.candidats(self.projet.conn)
        self.modifie = True
        message = f"{n} correction(s) faite(s)."
        if groupes:
            message += (f"\n\n{len(groupes)} groupe(s) de mots sont devenus identiques avec une glose commune : "
                        "Lexique > Doublons… permet de les fusionner.")
        info(self, "Retirer un signe", message)
        self.accept()

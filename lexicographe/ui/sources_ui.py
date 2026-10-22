"""Retirer le contenu venu d'une source : choix de la source, aperçu calculé, sauvegarde, application."""

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout

from .. import sources
from .commun import CurseurAttente, confirmer, info


class DialogueRetirerSource(QDialog):
    def __init__(self, projet, parent=None):
        super().__init__(parent)
        self.projet = projet
        self.modifie = False
        self.plan = None
        self.setWindowTitle("Retirer une source")
        self.setMinimumWidth(640)
        v = QVBoxLayout(self)
        aide = QLabel("Retire ce qu'un import a ajouté depuis une source (un dictionnaire imprimé, par exemple) : "
                      "ses exemples, et les entrées qui ne viennent que d'elle. Une entrée qui a aussi une autre "
                      "origine (Paratext, collecte, image, son, analyse de texte) est gardée. Ce qui n'est pas "
                      "marqué n'est jamais touché. Le projet est sauvegardé avant.")
        aide.setWordWrap(True)
        aide.setObjectName("sousTitre")
        v.addWidget(aide)
        f = QFormLayout()
        self.source = QComboBox()
        self.source.addItem("— choisir une source —", None)   # rien n'est choisi d'office
        with CurseurAttente():
            for nom, (entrees, exemples) in sources.lister(projet.conn).items():
                self.source.addItem(f"{nom}  ({entrees} entrée(s), {exemples} exemple(s))", nom)
        f.addRow("Source :", self.source)
        v.addLayout(f)
        self.resume = QLabel("")
        self.resume.setWordWrap(True)
        v.addWidget(self.resume)
        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok = boutons.button(QDialogButtonBox.Ok)
        self.ok.setText("Retirer")
        boutons.accepted.connect(self._appliquer)
        boutons.rejected.connect(self.reject)
        v.addWidget(boutons)
        self.source.currentIndexChanged.connect(self._apercu)
        self._apercu()

    def _apercu(self):
        nom = self.source.currentData()
        if not nom:
            self.plan = None
            self.resume.setText("")
            self.ok.setEnabled(False)
            return
        with CurseurAttente():
            self.plan = sources.plan(self.projet.conn, nom)
        self.resume.setText(self.plan.resume(self.projet.conn))
        self.ok.setEnabled(bool(self.plan.exemples or self.plan.entrees_supprimees or self.plan.entrees_gardees))

    def _appliquer(self):
        if not self.plan or not confirmer(self, "Retirer une source",
                                          f"{self.plan.resume(self.projet.conn)}\n\nContinuer ? Le projet est "
                                          "sauvegardé avant."):
            return
        self.projet.sauvegarde_automatique()
        with CurseurAttente(), self.projet.en_lot():
            sources.appliquer(self.projet.conn, self.plan)
        self.modifie = True
        info(self, "Retirer une source", "Contenu de la source retiré. La sauvegarde d'avant se trouve dans "
                                         "le dossier des sauvegardes (menu Fichier).")
        self.accept()

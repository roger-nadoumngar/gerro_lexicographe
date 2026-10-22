"""Fenêtre d'inscription : adresse e-mail et code reçu. Jamais bloquante (« Plus tard »)."""

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from .. import APP_NAME, inscription
from .commun import erreur, info


class DialogueInscription(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Inscription")
        self.setMinimumWidth(560)
        v = QVBoxLayout(self)
        aide = QLabel("Inscrivez-vous pour être tenu informé des mises à jour de Gerro Lexicographe. "
                      "Demandez un code en donnant votre adresse e-mail, puis saisissez-le ici. "
                      "Le logiciel fonctionne aussi sans inscription.")
        aide.setWordWrap(True)
        v.addWidget(aide)
        if inscription.CONTACT:
            contact = QLabel(f"Pour demander un code : {inscription.CONTACT}")
            contact.setWordWrap(True)
            contact.setTextInteractionFlags(Qt.TextSelectableByMouse)
            v.addWidget(contact)
        f = QFormLayout()
        d = inscription.lire()
        self.nom = QLineEdit(d.get("nom", ""))
        self.email = QLineEdit(d.get("email", ""))
        self.email.setPlaceholderText("personne@exemple.org")
        self.code = QLineEdit()
        self.code.setPlaceholderText("GL1-…")
        f.addRow("Nom :", self.nom)
        f.addRow("Adresse e-mail :", self.email)
        f.addRow("Code d'inscription :", self.code)
        v.addLayout(f)
        discret = QLabel("Votre adresse reste sur cet ordinateur : le logiciel n'envoie rien par internet.")
        discret.setWordWrap(True)
        discret.setObjectName("sousTitre")
        v.addWidget(discret)
        boutons = QDialogButtonBox()
        self.valider = boutons.addButton("Valider", QDialogButtonBox.AcceptRole)
        boutons.addButton("Plus tard", QDialogButtonBox.RejectRole)
        if "@" in inscription.CONTACT:
            demander = QPushButton("Demander un code…")
            demander.clicked.connect(self._demander)
            boutons.addButton(demander, QDialogButtonBox.ActionRole)
        boutons.accepted.connect(self._valider)
        boutons.rejected.connect(self._plus_tard)
        v.addWidget(boutons)

    def _demander(self):
        sujet = QUrl.toPercentEncoding("Code d'inscription Gerro Lexicographe").data().decode()
        QDesktopServices.openUrl(QUrl(f"mailto:{inscription.CONTACT}?subject={sujet}"))

    def _valider(self):
        email, code = self.email.text().strip(), self.code.text().strip()
        if not inscription.code_valide(email, code):
            erreur(self, "Inscription", "Ce code ne correspond pas à cette adresse e-mail. "
                                        "Vérifiez l'adresse et le code reçu.")
            return
        try:
            inscription.enregistrer(email, code, self.nom.text())
        except OSError as e:
            erreur(self, "Inscription", "L'inscription n'a pas pu être enregistrée.", e)
            return
        info(self, "Inscription", f"Merci ! {APP_NAME} est inscrit au nom de {inscription.normaliser_email(email)}.")
        self.accept()

    def _plus_tard(self):
        try:
            inscription.plus_tard()
        except OSError:
            pass
        self.reject()


def proposer_au_demarrage():
    try:
        if inscription.a_demander():
            DialogueInscription().exec()
    except Exception:
        pass   # l'inscription ne doit jamais empêcher le logiciel de démarrer

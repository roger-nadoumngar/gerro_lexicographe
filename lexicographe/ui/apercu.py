"""Aperçu avant impression d'un PDF produit par le logiciel : pages affichées comme des
feuilles (A4 ou A5), puis impression ou enregistrement."""

import os
import shutil
import tempfile

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QPainter
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout

from .commun import CurseurAttente, erreur, info


def fichier_temporaire(extension=".pdf"):
    descripteur, chemin = tempfile.mkstemp(prefix="apercu-", suffix=extension)
    os.close(descripteur)
    return chemin


class ApercuPDF(QDialog):
    """Affiche le PDF ; « Imprimer… » ouvre la boîte d'impression de Windows,
    « Enregistrer le PDF… » en garde une copie."""

    def __init__(self, chemin_pdf, nom_propose, parent=None, titre="Aperçu avant impression"):
        super().__init__(parent)
        self.setWindowTitle(titre)
        self.resize(1000, 900)
        self.chemin = chemin_pdf
        self.nom_propose = nom_propose
        self.document = QPdfDocument(self)
        self.document.load(chemin_pdf)

        v = QVBoxLayout(self)
        barre = QHBoxLayout()
        self.infos = QLabel(f"{self.document.pageCount()} page(s)")
        self.infos.setObjectName("sousTitre")
        barre.addWidget(self.infos)
        barre.addStretch()
        barre.addWidget(QLabel("Zoom :"))
        self.zoom = QSlider(Qt.Horizontal)
        self.zoom.setRange(30, 200)
        self.zoom.setValue(100)
        self.zoom.setFixedWidth(160)
        self.zoom.valueChanged.connect(self._zoomer)
        barre.addWidget(self.zoom)
        largeur = QPushButton("Pleine largeur")
        largeur.clicked.connect(lambda: self.vue.setZoomMode(QPdfView.ZoomMode.FitToWidth))
        page = QPushButton("Page entière")
        page.clicked.connect(lambda: self.vue.setZoomMode(QPdfView.ZoomMode.FitInView))
        barre.addWidget(largeur)
        barre.addWidget(page)
        v.addLayout(barre)

        self.vue = QPdfView(self)
        self.vue.setDocument(self.document)
        self.vue.setPageMode(QPdfView.PageMode.MultiPage)
        self.vue.setPageSpacing(18)
        self.vue.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.vue.setStyleSheet("QPdfView { background: #8A8778; }")   # fond gris : les pages ressortent
        v.addWidget(self.vue, 1)

        boutons = QHBoxLayout()
        boutons.addStretch()
        enregistrer = QPushButton("Enregistrer le PDF…")
        enregistrer.clicked.connect(self._enregistrer)
        imprimer = QPushButton("Imprimer…")
        imprimer.setObjectName("principal")
        imprimer.clicked.connect(self._imprimer)
        fermer = QPushButton("Fermer")
        fermer.clicked.connect(self.reject)
        for b in (enregistrer, imprimer, fermer):
            boutons.addWidget(b)
        v.addLayout(boutons)

    def _zoomer(self, valeur):
        self.vue.setZoomMode(QPdfView.ZoomMode.Custom)
        self.vue.setZoomFactor(valeur / 100)

    def _enregistrer(self):
        chemin, _ = QFileDialog.getSaveFileName(self, "Enregistrer le PDF", self.nom_propose, "PDF (*.pdf)")
        if not chemin:
            return
        try:
            shutil.copyfile(self.chemin, chemin)
        except OSError as e:
            erreur(self, "Enregistrer", "Le fichier n'a pas pu être enregistré.", e)
            return
        info(self, "Enregistrer", f"PDF enregistré :\n{chemin}")

    def _imprimer(self):
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        imprimante = QPrinter(QPrinter.HighResolution)
        imprimante.setDocName(os.path.basename(self.nom_propose))
        dialogue = QPrintDialog(imprimante, self)
        dialogue.setMinMax(1, max(1, self.document.pageCount()))
        if dialogue.exec() != QDialog.Accepted:
            return
        imprimer_pdf(self.document, imprimante)


def imprimer_pdf(document, imprimante):
    """Envoie les pages du PDF à l'imprimante (plage de pages choisie respectée)."""
    debut, fin = imprimante.fromPage(), imprimante.toPage()
    if debut == 0:
        debut, fin = 1, document.pageCount()
    peintre = QPainter()
    if not peintre.begin(imprimante):
        raise RuntimeError("L'imprimante n'a pas pu être ouverte.")
    try:
        with CurseurAttente():
            for numero in range(debut - 1, min(fin, document.pageCount())):
                if numero > debut - 1:
                    imprimante.newPage()
                zone = imprimante.pageLayout().paintRectPixels(imprimante.resolution())
                taille = document.pagePointSize(numero)
                echelle = min(zone.width() / taille.width(), zone.height() / taille.height())
                largeur, hauteur = int(taille.width() * echelle), int(taille.height() * echelle)
                image = document.render(numero, zone.size().scaled(largeur, hauteur, Qt.KeepAspectRatio))
                peintre.drawImage(QRect(0, 0, largeur, hauteur), image)
    finally:
        peintre.end()


def apercu(parent, generer, nom_propose, titre="Aperçu avant impression"):
    """Produit le PDF dans un fichier temporaire avec `generer(chemin)`, puis l'affiche."""
    chemin = fichier_temporaire()
    try:
        with CurseurAttente():
            resultat = generer(chemin)
    except Exception as e:
        erreur(parent, "Aperçu", "Le document n'a pas pu être préparé.", e)
        return None
    dialogue = ApercuPDF(chemin, nom_propose, parent, titre)
    dialogue.exec()
    dialogue.document.close()
    try:
        os.remove(chemin)
    except OSError:
        pass
    return resultat


"""Style, polices et petits utilitaires partagés par l'interface."""

import html

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QMessageBox

ENCRE = "#2B2A1F"
FOND = "#F4EFE4"
PANNEAU = "#FBF8F1"
BORDURE = "#D8CFBC"
SARCELLE = "#1F5B57"
SARCELLE_FONCE = "#174643"
DISCRET = "#6B6857"

FEUILLE_DE_STYLE = f"""
QWidget {{ color: {ENCRE}; }}
QMainWindow, QDialog {{ background: {FOND}; }}
QListWidget#navigation {{ background: {SARCELLE_FONCE}; color: #EAF2F1; border: none; padding-top: 8px;
                           outline: 0; }}
QListWidget#navigation::item {{ padding: 10px 14px; border-left: 3px solid transparent; color: #EAF2F1; }}
QListWidget#navigation::item:selected {{ background: {SARCELLE}; color: white; border-left: 3px solid #E8C872; }}
QListWidget#navigation::item:hover {{ color: white; }}
QListWidget#navigation::item:hover:!selected {{ background: #2A6A65; color: white; }}
QLabel#titrePage {{ font-size: 20px; font-weight: 600; }}
QLabel#sousTitre, QLabel.discret {{ color: {DISCRET}; }}
QLabel#grandeForme {{ font-size: 28px; font-weight: 600; }}
QFrame#carte {{ background: {PANNEAU}; border: 1px solid {BORDURE}; border-radius: 6px; }}
QLabel#chiffre {{ font-size: 26px; font-weight: 600; color: {SARCELLE}; }}
QPushButton {{ padding: 6px 12px; border: 1px solid {BORDURE}; border-radius: 4px; background: {PANNEAU}; }}
QPushButton:hover {{ border-color: {SARCELLE}; }}
QPushButton:disabled {{ color: #A8A390; }}
QPushButton#principal {{ background: {SARCELLE}; color: white; border-color: {SARCELLE}; font-weight: 600; }}
QPushButton#principal:hover {{ background: {SARCELLE_FONCE}; }}
QPushButton#candidat {{ padding: 3px 10px; border-radius: 10px; }}
QLineEdit, QPlainTextEdit, QTextEdit, QTextBrowser, QComboBox, QSpinBox, QDoubleSpinBox,
QTableWidget, QListWidget {{ background: white; border: 1px solid {BORDURE}; border-radius: 3px; }}
QLineEdit, QComboBox {{ padding: 4px; }}
QHeaderView::section {{ background: #EDE6D6; border: none; border-right: 1px solid {BORDURE}; padding: 4px; }}
QTabWidget::pane {{ border: 1px solid {BORDURE}; background: {PANNEAU}; }}
QTabBar::tab {{ padding: 6px 14px; background: #E9E2D2; border: 1px solid {BORDURE}; border-bottom: none; }}
QTabBar::tab:selected {{ background: {PANNEAU}; }}
QGroupBox {{ border: 1px solid {BORDURE}; border-radius: 4px; margin-top: 14px; padding-top: 6px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; font-weight: 600; }}
"""

# polices SIL couvrant les écritures africaines et les diacritiques empilés, si installées
POLICES_PREFEREES = ["Charis SIL", "Andika", "Gentium Plus", "Doulos SIL", "Segoe UI", "Noto Sans"]


def appliquer_style(app: QApplication):
    # boutons standard de Qt en français (Annuler, Oui, Non…), traduction fournie avec PySide6
    from PySide6.QtCore import QLibraryInfo, QTranslator
    traducteur = QTranslator(app)
    if traducteur.load("qtbase_fr", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(traducteur)
    app.setStyle("Fusion")
    app.setStyleSheet(FEUILLE_DE_STYLE)
    familles = set(QFontDatabase.families())
    for nom in POLICES_PREFEREES:
        if nom in familles:
            police = QFont(nom, 10)
            app.setFont(police)
            break


def titre(texte, sous_titre=None):
    """(QLabel titre, QLabel sous-titre ou None)"""
    t = QLabel(texte)
    t.setObjectName("titrePage")
    s = None
    if sous_titre:
        s = QLabel(sous_titre)
        s.setObjectName("sousTitre")
        s.setWordWrap(True)
    return t, s


def carte():
    f = QFrame()
    f.setObjectName("carte")
    return f


def erreur(parent, titre_fenetre, message, exc=None):
    texte = message + (f"\n\n{exc}" if exc else "")
    QMessageBox.critical(parent, titre_fenetre, texte)


def info(parent, titre_fenetre, message):
    QMessageBox.information(parent, titre_fenetre, message)


def confirmer(parent, titre_fenetre, question):
    return QMessageBox.question(parent, titre_fenetre, question,
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes


def surligner(tokeniseur, texte, mots):
    """HTML du texte avec les mots donnés en gras et en couleur."""
    morceaux = []
    for brut, mot in tokeniseur.decouper(texte):
        if mot and mot in mots:
            morceaux.append(f'<b style="color:{SARCELLE}">{html.escape(brut)}</b>')
        else:
            morceaux.append(html.escape(brut))
    return "".join(morceaux)


class CurseurAttente:
    """with CurseurAttente(): … — curseur d'attente pendant un calcul."""

    def __enter__(self):
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)

    def __exit__(self, *exc):
        QGuiApplication.restoreOverrideCursor()
        return False

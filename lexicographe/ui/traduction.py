"""Langue de l'interface (français ou anglais).

Le code est écrit en français ; en anglais, chaque texte affiché est remplacé par sa traduction
(ressources/interface/en.json). Règles :
- un texte est traduit s'il est exactement dans le fichier ; sinon s'il correspond à un gabarit
  (« {} entrée(s) exportée(s) vers :\\n{} » : les parties variables sont gardées) ; sinon ligne par ligne ;
  sinon il reste tel quel ;
- les données des projets (formes, gloses, exemples, noms de listes…) ne passent jamais par ici :
  seuls les textes de l'interface le font, au moment où ils sont posés sur un élément d'interface ;
- une liste déroulante garde en interne la valeur française d'origine (statut « validé »…) : le
  projet enregistre les mêmes valeurs quelle que soit la langue de l'interface.
Le choix est gardé dans le dossier des données du logiciel (interface.json)."""

import json
import os
import re

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (QAbstractButton, QComboBox, QFileDialog, QGroupBox, QInputDialog, QLabel, QLineEdit,
                               QMenu, QMessageBox, QPlainTextEdit, QProgressDialog, QTableWidget, QTabWidget,
                               QWidget)

LANGUES = {"fr": "Français", "en": "English"}
ROLE_ORIGINE = Qt.UserRole + 77
_actuelle = "fr"
_exacts, _gabarits = {}, []


def _fichier_choix():
    from ..chemins import dossier_donnees
    return os.path.join(dossier_donnees(), "interface.json")


def langue_enregistree():
    try:
        with open(_fichier_choix(), encoding="utf-8") as f:
            langue = json.load(f).get("langue", "fr")
        return langue if langue in LANGUES else "fr"
    except (OSError, ValueError):
        return "fr"


def enregistrer_langue(langue):
    os.makedirs(os.path.dirname(_fichier_choix()), exist_ok=True)
    with open(_fichier_choix(), "w", encoding="utf-8") as f:
        json.dump({"langue": langue}, f)


def langue():
    return _actuelle


def charger(langue_choisie):
    """Prépare la traduction ; pour le français, rien n'est fait."""
    global _actuelle, _exacts, _gabarits
    _actuelle = langue_choisie if langue_choisie in LANGUES else "fr"
    _exacts, _gabarits = {}, []
    if _actuelle == "fr":
        return
    from ..chemins import ressource
    with open(ressource("interface", f"{_actuelle}.json"), encoding="utf-8") as f:
        table = json.load(f)
    for fr, autre in table.items():
        if not autre or (autre == fr and "{}" not in fr):
            continue
        if "{}" in fr:   # même inchangé (« <b>{}</b> »), un gabarit sert à traduire ce qu'il contient
            morceaux = fr.split("{}")
            motif = re.compile("(.*?)".join(re.escape(m) for m in morceaux), re.S)
            _gabarits.append((morceaux[0], motif, autre))
        else:
            _exacts[fr] = autre
    # gabarits les plus longs d'abord : le plus précis l'emporte
    _gabarits.sort(key=lambda g: -len(g[1].pattern))


def tr(texte):
    """Texte traduit dans la langue de l'interface (identique en français ou s'il est inconnu)."""
    if _actuelle == "fr" or not isinstance(texte, str) or not texte.strip():
        return texte
    if texte in _exacts:
        return _exacts[texte]
    for debut, motif, autre in _gabarits:
        if texte.startswith(debut):
            m = motif.fullmatch(texte)
            if m:
                valeurs = [tr(v) for v in m.groups()]
                return _remplir(autre, valeurs)
    if "\n" in texte:
        lignes = texte.split("\n")
        traduites = [tr(l) for l in lignes]
        if traduites != lignes:
            return "\n".join(traduites)
    return texte


def _remplir(gabarit, valeurs):
    # « {} » dans l'ordre, ou « {0} », « {1} » quand l'anglais change l'ordre
    if re.search(r"\{\d+\}", gabarit):
        return re.sub(r"\{(\d+)\}", lambda m: valeurs[int(m.group(1))] if int(m.group(1)) < len(valeurs) else "",
                      gabarit)
    morceaux = gabarit.split("{}")
    resultat = morceaux[0]
    for i, morceau in enumerate(morceaux[1:]):
        resultat += (valeurs[i] if i < len(valeurs) else "") + morceau
    return resultat


# -- application aux éléments d'interface ------------------------------------------------------------

class _Traducteur(QObject):
    """Traduit les textes posés à la construction d'un élément, juste avant son premier affichage."""

    def eventFilter(self, objet, evenement):
        if evenement.type() == QEvent.Polish and isinstance(objet, QWidget) and not objet.property("_traduit"):
            objet.setProperty("_traduit", True)
            traduire_element(objet)
        return False


def traduire_element(w):
    if w.windowTitle():
        _original["setWindowTitle"](w, tr(w.windowTitle()))
    if w.toolTip():
        w.setToolTip(tr(w.toolTip()))
    if isinstance(w, (QLabel, QAbstractButton)) and w.text():
        _original["setText_" + ("label" if isinstance(w, QLabel) else "bouton")](w, tr(w.text()))
    if isinstance(w, QGroupBox) and w.title():
        w.setTitle(tr(w.title()))
    if isinstance(w, (QLineEdit, QPlainTextEdit)) and w.placeholderText():
        w.setPlaceholderText(tr(w.placeholderText()))
    if isinstance(w, QTabWidget):
        for i in range(w.count()):
            w.setTabText(i, tr(w.tabText(i)))
    if isinstance(w, QTableWidget):
        for i in range(w.columnCount()):
            item = w.horizontalHeaderItem(i)
            if item and item.text():
                item.setText(tr(item.text()))
    if isinstance(w, QMenu):
        for action in w.actions():
            if action.text():
                action.setText(tr(action.text()))
    for action in w.actions() if not isinstance(w, QMenu) else []:
        if action.text():
            action.setText(tr(action.text()))


_original = {}


def _envelopper(classe, nom, cle, fabrique):
    _original[cle] = getattr(classe, nom)
    setattr(classe, nom, fabrique(_original[cle]))


def installer(app):
    """À appeler une fois, après `charger`, si la langue n'est pas le français."""
    if _actuelle == "fr":
        return
    app._traducteur = _Traducteur()
    app.installEventFilter(app._traducteur)
    simple = lambda orig: lambda self, texte, *a: orig(self, tr(texte), *a)   # noqa: E731
    _envelopper(QLabel, "setText", "setText_label", simple)
    _envelopper(QAbstractButton, "setText", "setText_bouton", simple)
    _envelopper(QWidget, "setWindowTitle", "setWindowTitle", simple)
    _envelopper(QProgressDialog, "setLabelText", "setLabelText", simple)
    _envelopper(QLineEdit, "setPlaceholderText", "placeholder", simple)
    _envelopper(QTabWidget, "addTab", "addTab", lambda orig: lambda self, page, *a: orig(
        self, page, *[tr(x) if isinstance(x, str) else x for x in a]))
    _envelopper(QTableWidget, "setHorizontalHeaderLabels", "entetes",
                lambda orig: lambda self, libelles: orig(self, [tr(x) for x in libelles]))
    _envelopper(QMenu, "addAction", "addAction", lambda orig: lambda self, *a: orig(
        self, *[tr(x) if isinstance(x, str) else x for x in a]))
    _envelopper(QMenu, "addMenu", "addMenu", lambda orig: lambda self, *a: orig(
        self, *[tr(x) if isinstance(x, str) else x for x in a]))
    _listes_deroulantes()
    _elements_de_liste()
    _boites_standard()


def _elements_de_liste():
    """Éléments de QListWidget (menu de gauche, messages composés) : seuls les textes de l'interface
    connus sont traduits ; une donnée (mot, glose) n'est jamais dans la table, elle reste telle quelle."""
    from PySide6.QtWidgets import QListWidgetItem
    construire, poser = QListWidgetItem.__init__, QListWidgetItem.setText

    def __init__(self, *a, **k):
        a = [tr(x) if isinstance(x, str) else x for x in a]
        construire(self, *a, **k)

    QListWidgetItem.__init__ = __init__
    QListWidgetItem.setText = lambda self, texte: poser(self, tr(texte))


def _listes_deroulantes():
    """Affichage traduit, valeur d'origine gardée (rôle ROLE_ORIGINE) et rendue par currentText()."""
    ajouter = QComboBox.addItem

    def addItem(self, *a):
        a = list(a)
        i = 1 if a and not isinstance(a[0], str) else 0   # addItem(icône, texte, …) ou addItem(texte, …)
        if len(a) > i and isinstance(a[i], str):
            origine = a[i]
            a[i] = tr(origine)
            ajouter(self, *a)
            if a[i] != origine:
                self.setItemData(self.count() - 1, origine, ROLE_ORIGINE)
            return
        ajouter(self, *a)

    def addItems(self, textes):
        for t in textes:
            addItem(self, t)

    texte_courant, texte_element, chercher = QComboBox.currentText, QComboBox.itemText, QComboBox.findText
    choisir_texte = QComboBox.setCurrentText

    def itemText(self, i):
        origine = self.itemData(i, ROLE_ORIGINE)
        return origine if origine is not None else texte_element(self, i)

    def currentText(self):
        t = texte_courant(self)
        i = self.currentIndex()
        if i >= 0 and t == texte_element(self, i):
            origine = self.itemData(i, ROLE_ORIGINE)
            if origine is not None:
                return origine
        return t

    def findText(self, texte, *a):
        for i in range(self.count()):
            if self.itemData(i, ROLE_ORIGINE) == texte:
                return i
        return chercher(self, texte, *a)

    def setCurrentText(self, texte):
        i = findText(self, texte)
        if i >= 0:
            self.setCurrentIndex(i)
        else:
            choisir_texte(self, texte)

    inserer = QComboBox.insertItem

    def insertItem(self, index, *a):
        a = list(a)
        i = 1 if a and not isinstance(a[0], str) else 0
        if len(a) > i and isinstance(a[i], str):
            origine = a[i]
            a[i] = tr(origine)
            inserer(self, index, *a)
            if a[i] != origine:
                self.setItemData(index, origine, ROLE_ORIGINE)
            return
        inserer(self, index, *a)

    QComboBox.addItem, QComboBox.addItems, QComboBox.insertItem = addItem, addItems, insertItem
    QComboBox.itemText, QComboBox.currentText = itemText, currentText
    QComboBox.findText, QComboBox.setCurrentText = findText, setCurrentText


def _boites_standard():
    question, information, critique = QMessageBox.question, QMessageBox.information, QMessageBox.critical
    avertissement = QMessageBox.warning
    QMessageBox.question = staticmethod(lambda p, t, m, *a, **k: question(p, tr(t), tr(m), *a, **k))
    QMessageBox.information = staticmethod(lambda p, t, m, *a, **k: information(p, tr(t), tr(m), *a, **k))
    QMessageBox.critical = staticmethod(lambda p, t, m, *a, **k: critique(p, tr(t), tr(m), *a, **k))
    QMessageBox.warning = staticmethod(lambda p, t, m, *a, **k: avertissement(p, tr(t), tr(m), *a, **k))
    a_propos = QMessageBox.about
    QMessageBox.about = staticmethod(lambda p, t, m: a_propos(p, tr(t), tr(m)))

    get_text, get_item = QInputDialog.getText, QInputDialog.getItem

    def getText(parent, titre, libelle, *a, **k):
        return get_text(parent, tr(titre), tr(libelle), *a, **k)

    def getItem(parent, titre, libelle, elements, *a, **k):
        affiches = [tr(e) for e in elements]
        choix, ok = get_item(parent, tr(titre), tr(libelle), affiches, *a, **k)
        # la valeur rendue est celle d'origine : le code compare avec ses propres textes
        return (elements[affiches.index(choix)] if choix in affiches else choix), ok

    QInputDialog.getText, QInputDialog.getItem = staticmethod(getText), staticmethod(getItem)
    for nom in ("getOpenFileName", "getSaveFileName", "getExistingDirectory", "getOpenFileNames"):
        orig = getattr(QFileDialog, nom)

        def dialogue(*a, _orig=orig, **k):
            a = [tr(x) if isinstance(x, str) and i in (1, 3) else x for i, x in enumerate(a)]
            return _orig(*a, **k)
        setattr(QFileDialog, nom, staticmethod(dialogue))


def textes_affiches_inconnus(textes):
    """Pour les tests : textes qui n'ont ni traduction exacte ni gabarit."""
    return [t for t in textes if tr(t) == t]


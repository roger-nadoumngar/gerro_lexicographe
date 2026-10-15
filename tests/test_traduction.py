import json
import os
import subprocess
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RACINE, "outils"))

import extraire_textes  # noqa: E402

from lexicographe.ui import traduction  # noqa: E402


def test_chaque_texte_a_sa_traduction():
    """Un texte ajouté à l'interface sans traduction fait échouer ce test :
    lancer outils/extraire_textes.py puis outils/construire_traductions.py après l'avoir traduit."""
    en = json.load(open(os.path.join(RACINE, "lexicographe", "ressources", "interface", "en.json"), encoding="utf-8"))
    manquants = [t for t in extraire_textes.tous_les_textes() if t not in en]
    assert manquants == [], f"{len(manquants)} texte(s) sans traduction : {manquants[:10]}"


def test_traduire():
    traduction.charger("en")
    try:
        assert traduction.tr("Lexique") == "Lexicon"
        assert traduction.tr("12 entrée(s) exportée(s) vers :\nC:\\x.lift") == "12 entry(ies) exported to:\nC:\\x.lift"
        assert traduction.tr("<b>Projet FLEx</b>") == "<b>FLEx project</b>", "le contenu d'un gabarit est traduit"
        assert traduction.tr("Lexique\nExports") == "Lexicon\nExports", "ligne par ligne"
        assert traduction.tr("bísī") == "bísī", "une donnée n'est pas touchée"
        assert traduction.tr("") == ""
    finally:
        traduction.charger("fr")
    assert traduction.tr("Lexique") == "Lexique", "en français, rien ne change"


def test_interface_anglaise_garde_les_valeurs(tmp_path):
    """Lancée dans un processus séparé (la traduction modifie Qt pour toute la session)."""
    script = tmp_path / "essai.py"
    script.write_text(f"""
import os, sys
sys.path.insert(0, {RACINE!r})
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\\Windows\\Fonts")
from PySide6.QtWidgets import QApplication, QComboBox, QInputDialog
from lexicographe.ui import commun, traduction
app = QApplication([])
traduction.charger("en"); traduction.installer(app)
from lexicographe.projet import Projet
from lexicographe.ui.fenetre import FenetrePrincipale
p = Projet.creer(r"{tmp_path / 'p.lexique'}", nom="Essai", langue_vern_code="xxx", langue_vern_nom="essai")
f = FenetrePrincipale(p)
print(f.navigation.item(1).text())
c = QComboBox(); c.addItems(["brouillon", "à vérifier", "validé"])
c.setCurrentText("validé")
print(c.currentText(), "|", c.itemText(0), "|", c.findText("à vérifier"))
from PySide6.QtWidgets import QComboBox as Q
print(Q.currentText.__name__)
""", encoding="utf-8")
    sortie = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, encoding="utf-8",
                            timeout=120)
    lignes = sortie.stdout.strip().splitlines()
    assert sortie.returncode == 0, sortie.stderr[-2000:]
    assert lignes[0] == "Lexicon"
    assert lignes[1] == "validé | brouillon | 1", "la valeur d'origine est rendue, l'affichage est traduit"

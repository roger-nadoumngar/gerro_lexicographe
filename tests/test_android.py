import os

import pytest

from lexicographe import appli_android, lexique
from lexicographe.lexique import Entree, Sens

APPDEF = """<?xml version="1.0" encoding="utf-8"?>
<app-definition type="DAB" program-version="14.7">
  <project-name>{nom}</project-name>
  <lexicon-db type="lift"></lexicon-db>

  <signing>
  </signing>
</app-definition>
"""


def test_nom_de_paquet():
    assert appli_android.nom_de_paquet("sba", "Ngambay") == "org.gerro.sba.dictionnaire"
    assert appli_android.nom_de_paquet("", "Gor (Bodo)") == "org.gerro.gorbodo.dictionnaire"
    assert appli_android.nom_de_paquet("2x", "") == "org.gerro.l2x.dictionnaire"


def test_relier_lift(tmp_path):
    chemin = tmp_path / "App.appDef"
    chemin.write_text(APPDEF.format(nom="App"), encoding="utf-8")
    appli_android._relier_lift(str(chemin), "Ngambay.lift", r"C:\a & b\Ngambay.lift")
    texte = chemin.read_text(encoding="utf-8")
    assert '<lexicon-db type="lift">Ngambay.lift</lexicon-db>' in texte
    assert r"<source>C:\a &amp; b\Ngambay.lift</source>" in texte
    appli_android._relier_lift(str(chemin), "Autre.lift", r"C:\x\Autre.lift")
    texte = chemin.read_text(encoding="utf-8")
    assert texte.count("<source>") == 1 and "Autre.lift" in texte, "relier deux fois ne duplique rien"


def test_declarer_illustrations(tmp_path):
    from PySide6.QtGui import QColor, QImage
    dossier = tmp_path / "illustrations"
    dossier.mkdir()
    image = QImage(40, 30, QImage.Format_RGB32)
    image.fill(QColor("red"))
    image.save(str(dossier / "chien.png"))
    (dossier / "pas_une_image.txt").write_text("x")
    chemin = tmp_path / "App.appDef"
    chemin.write_text(APPDEF.format(nom="App").replace(
        "  <signing>", '  <images type="launcher">\n    <image width="72" height="72">a.png</image>\n  </images>\n\n'
                       "  <signing>"), encoding="utf-8")
    assert appli_android._declarer_illustrations(str(chemin), str(dossier)) == 1
    assert appli_android._declarer_illustrations(str(chemin), str(dossier)) == 1
    texte = chemin.read_text(encoding="utf-8")
    assert texte.count('<images type="illustration">') == 1, "réécrite, jamais dupliquée"
    assert '<image width="40" height="30">chien.png</image>' in texte
    assert texte.index('type="launcher"') < texte.index('type="illustration"') < texte.index("<signing>")


def test_construction_simulee(projet, tmp_path, monkeypatch):
    """DAB est remplacé par une imitation : création du projet sur -new, APK sur -build."""
    conn = projet.conn
    eid = lexique.enregistrer_entree(conn, Entree(forme="bísī", sens=[Sens(glose="chien")]))
    image = tmp_path / "dog.jpg"
    image.write_bytes(b"\xff\xd8\xff")
    os.makedirs(projet.dossier_medias, exist_ok=True)
    copie = os.path.join(projet.dossier_medias, "dog.jpg")
    open(copie, "wb").write(image.read_bytes())
    lexique.lier_media(conn, eid, copie, "image")
    keystore = tmp_path / "cle.keystore"
    keystore.write_bytes(b"x")
    appels = []

    def faux_dab(dab, arguments, secrets, delai=3600):
        appels.append(arguments)
        if "-new" in arguments:
            nom = arguments[arguments.index("-n") + 1]
            dossier = arguments[arguments.index("-fp") + 1].split("=", 1)[1]
            os.makedirs(os.path.join(dossier, nom), exist_ok=True)
            with open(os.path.join(dossier, nom, f"{nom}.appDef"), "w", encoding="utf-8") as f:
                f.write(APPDEF.format(nom=nom))
            return 0, "Create New App Project"
        sortie = next(a.split("=", 1)[1] for a in arguments if a.startswith("apk.output="))
        open(os.path.join(sortie, "Dictionnaire-1.0.apk"), "wb").write(b"apk")
        journal = "Build App: mot de passe secret123 utilisé"
        for s in secrets:
            journal = journal.replace(s, "••••")
        return 0, journal

    monkeypatch.setattr(appli_android, "_executer", faux_dab)
    monkeypatch.setattr(appli_android, "dossier_dab", lambda: r"C:\DAB")
    monkeypatch.setattr(appli_android, "dossiers_construction", lambda: {"jdk": r"C:\jdk", "android.sdk": r"C:\sdk"})
    options = appli_android.Options(nom_app="Dictionnaire", paquet="org.gerro.sba.dictionnaire",
                                    dossier_projets=str(tmp_path / "projets"), dossier_apk=str(tmp_path / "apk"),
                                    keystore=str(keystore), alias="key1", mot_de_passe="secret123")
    etapes = []
    r = appli_android.construire(projet, options, etapes.append)
    assert r.apk.endswith("Dictionnaire-1.0.apk") and os.path.isfile(r.apk)
    assert "secret123" not in r.journal and "••••" in r.journal
    donnees = tmp_path / "projets" / "Dictionnaire" / "Dictionnaire_data"
    assert (donnees / "images" / "illustrations" / "dog.jpg").is_file()
    lift = [f for f in os.listdir(donnees / "lexicon") if f.endswith(".lift")]
    assert lift and "bísī" in (donnees / "lexicon" / lift[0]).read_text(encoding="utf-8")
    assert f"<lexicon-db type=\"lift\">{lift[0]}</lexicon-db>" in open(r.projet_dab, encoding="utf-8").read()
    construction = appels[-1]
    assert "-build" in construction and construction.count("-ic") == 2, "icônes 72 et 144 produites"
    assert any(a == r"app.builder=C:\DAB" for a in construction), "dossier du programme DAB toujours donné"
    assert len(etapes) >= 3

    # deuxième construction : le projet DAB existe, il n'est pas recréé
    appli_android.construire(projet, options)
    assert sum("-new" in a for a in appels) == 1


def test_keystore_obligatoire(projet, tmp_path, monkeypatch):
    monkeypatch.setattr(appli_android, "dossier_dab", lambda: r"C:\DAB")
    monkeypatch.setattr(appli_android, "dossiers_construction", lambda: {"jdk": "j", "android.sdk": "s"})
    options = appli_android.Options(nom_app="D", paquet="org.x.d", dossier_projets=str(tmp_path),
                                    dossier_apk=str(tmp_path), keystore="", alias="", mot_de_passe="")
    with pytest.raises(RuntimeError, match="keystore"):
        appli_android.construire(projet, options)

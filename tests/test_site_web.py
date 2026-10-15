import json
import os

from lexicographe import lexique, publication, site_web
from lexicographe.lexique import Entree, Exemple, Sens


def _lire_donnees(dossier):
    texte = open(os.path.join(dossier, "donnees.js"), encoding="utf-8").read()
    assert texte.startswith("window.DICO = ") and texte.rstrip().endswith(";")
    return json.loads(texte[len("window.DICO = "):].rstrip().rstrip(";"))


def test_site(projet, tmp_path):
    conn = projet.conn
    projet.definir_reglages({"alphabet_vern": "a b ɓ k"})
    chien = lexique.enregistrer_entree(conn, Entree(forme="bísī", statut="validé", sens=[Sens(
        glose="chien", exemples=[Exemple(vernaculaire="Bísī lé àw̄.", traduction="Le chien est parti.")])]))
    lexique.enregistrer_entree(conn, Entree(forme="ɓá", statut="validé", sens=[Sens(glose="<b>piège</b>")]))
    lexique.enregistrer_entree(conn, Entree(forme="kàw", statut="brouillon", sens=[Sens(glose="oeuf")]))
    image = tmp_path / "dog.jpg"
    image.write_bytes(b"\xff\xd8\xff")
    lexique.lier_media(conn, chien, str(image), "image")

    n, chemin = site_web.exporter(projet, str(tmp_path / "site"), publication.Options(titre="Essai <i>"))
    assert n == 2, "brouillon non publié, comme pour le dictionnaire imprimé"
    d = _lire_donnees(str(tmp_path / "site"))
    assert [e["v"] for e in d["entrees"]] == ["bísī", "ɓá"] and d["lettres"] == ["B", "Ɓ"], "ordre de l'alphabet"
    bisi = d["entrees"][0]
    assert bisi["k"] == "bisi", "clé de recherche sans tons"
    assert bisi["s"][0]["x"] == [["Bísī lé àw̄.", "Le chien est parti."]]
    assert bisi["img"] and os.path.isfile(os.path.join(str(tmp_path / "site"), "images", bisi["img"][0]))
    page = open(chemin, encoding="utf-8").read()
    assert "<title>Essai &lt;i&gt;</title>" in page, "le titre est échappé"
    assert "innerHTML = \"\"" in page and ".innerHTML =" not in page.replace("innerHTML = \"\"", ""), \
        "les données ne sont jamais insérées comme du HTML"
    assert d["entrees"][1]["s"][0]["g"] == "<b>piège</b>", "texte gardé tel quel, affiché comme du texte"

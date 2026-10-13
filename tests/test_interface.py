import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from lexicographe import alignement, lexique  # noqa: E402
from lexicographe.projet import Projet  # noqa: E402
from lexicographe.ui import commun  # noqa: E402
from lexicographe.ui.application import ouvrir_projet  # noqa: E402
from lexicographe.ui.fenetre import FenetrePrincipale  # noqa: E402


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    commun.appliquer_style(a)
    return a


@pytest.fixture
def messages(monkeypatch):
    """Remplace les boîtes de dialogue bloquantes ; enregistre ce qui aurait été affiché."""
    vus = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a: vus.append(("erreur", a[1], a[2])))
    monkeypatch.setattr(QMessageBox, "information", lambda *a: vus.append(("info", a[1], a[2])))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    return vus


@pytest.fixture
def fenetre(app, tmp_path, messages, monkeypatch):
    monkeypatch.setattr("lexicographe.chemins.dossier_donnees", lambda *a: str(tmp_path / "donnees"))
    chemin = str(tmp_path / "ngambay.lexique")
    Projet.creer(chemin, nom="Ngambay", langue_vern_code="sba", langue_vern_nom="ngambay",
                 caracteres_mot_vern="-", longueur_min_mot="2", corpus_integre="ngambay_ruth_job").fermer()
    projet = ouvrir_projet(chemin)
    f = FenetrePrincipale(projet)
    f.show()
    yield f
    f.close()
    projet.fermer()


def page(fenetre, nom):
    return dict(fenetre.pages)[nom]


def test_ouverture_et_tableau_de_bord(fenetre):
    tdb = page(fenetre, "Tableau de bord")
    assert tdb.chiffres["phrases_paralleles"].text().replace(" ", "") == "1146"
    assert int(tdb.chiffres["en_attente"].text().replace(" ", "")) > 1000


def test_validation_cree_une_entree(fenetre):
    fenetre.navigation.setCurrentRow(2)
    v = page(fenetre, "Validation")
    forme = v.forme_courante
    assert forme and "phrase(s) contiennent" in v.preuves.toPlainText()
    assert v.editeur.onglets.widget(0).exemples.rowCount() == 1, "exemple pris dans le corpus"
    v.btn_valider.click()
    assert v.forme_courante != forme
    ids = lexique.chercher_par_forme(fenetre.projet.conn, forme)
    assert len(ids) == 1
    lex = page(fenetre, "Lexique")
    assert any(lex.liste.item(r, 0).text() == forme for r in range(lex.liste.rowCount()))


def test_passer_et_rejeter(fenetre):
    v = page(fenetre, "Validation")
    v.rafraichir()
    a = v.forme_courante
    v.btn_passer.click()
    b = v.forme_courante
    assert a != b
    v.btn_rejeter.click()
    statut = fenetre.projet.conn.execute("SELECT statut FROM hypotheses WHERE forme=?", (b,)).fetchone()[0]
    assert statut == "rejete"


def test_file_vide_desactive_les_boutons(fenetre):
    with fenetre.projet.conn:
        fenetre.projet.conn.execute("UPDATE hypotheses SET statut='rejete'")
    v = page(fenetre, "Validation")
    v.rafraichir()
    assert v.forme_courante is None and not v.btn_valider.isEnabled()


def test_lexique_edition_complete(fenetre, messages):
    fenetre.navigation.setCurrentRow(1)
    lex = page(fenetre, "Lexique")
    lex._nouvelle()
    ed = lex.editeur
    ed.forme.setText("kó")
    ed.onglets.widget(0).glose.setText("arbre")
    ed.btn_ajouter_sens.click()
    ed.onglets.widget(1).glose.setText("bois")
    ed._ajouter_propriete("ton", "haut")
    eid = ed.enregistrer()
    assert eid
    e = lexique.lire_entree(fenetre.projet.conn, eid)
    assert [s.glose for s in e.sens] == ["arbre", "bois"] and e.proprietes == {"ton": "haut"}

    # deuxième entrée et relation
    lex._nouvelle()
    ed.forme.setText("ndɔ")
    ed.onglets.widget(0).glose.setText("jour")
    autre = ed.enregistrer()
    i = ed.cible_relation.findData(eid)
    ed.cible_relation.setCurrentIndex(i)
    ed._ajouter_relation()
    assert [f for _, _, _, f in lexique.relations(fenetre.projet.conn, autre)] == ["kó"]

    # modifications non enregistrées : demandées avant de changer d'entrée (réponse simulée : oui)
    ed.onglets.widget(0).glose.setText("journée")
    ed.onglets.widget(0).glose.textEdited.emit("journée")
    assert ed.modifiee
    lex.ouvrir_entree(eid)
    assert lexique.lire_entree(fenetre.projet.conn, autre).sens[0].glose == "journée"
    assert ed.entree.id == eid
    assert not [m for m in messages if m[0] == "erreur"]


def test_corpus_ajout_de_phrase(fenetre):
    fenetre.navigation.setCurrentRow(3)
    c = page(fenetre, "Corpus")
    c.nouvelle_vern.setPlainText("Kó ndɔ")
    c.nouvelle_analyse.setPlainText("arbre jour")
    c._ajouter()
    n = fenetre.projet.conn.execute("SELECT COUNT(*) FROM phrases WHERE source='saisie_manuelle'").fetchone()[0]
    assert n == 1
    assert c.table.item(0, 1).text() == "Kó ndɔ"


def test_contradiction_dans_le_tableau_de_bord(fenetre):
    projet = fenetre.projet
    alignement.valider(projet, "ala", lexique.Entree(forme="ala", sens=[lexique.Sens(glose="xyz")]))
    alignement.recalculer(projet)
    tdb = page(fenetre, "Tableau de bord")
    tdb.rafraichir()
    tdb.contradictions.setCurrentRow(0)
    tdb._resoudre(adopter=True)
    assert alignement.contradictions_ouvertes(projet) == []
    eid = lexique.chercher_par_forme(projet.conn, "ala")[0]
    assert lexique.lire_entree(projet.conn, eid).sens[0].glose != "xyz"


def test_sauvegarde_a_la_fermeture(fenetre, tmp_path):
    fenetre.close()
    sauvegardes = os.listdir(tmp_path / "donnees" / "Sauvegardes")
    assert len(sauvegardes) == 1 and sauvegardes[0].endswith(".lexique")


def test_premier_lancement_convertit_l_ancienne_base(app, tmp_path, messages, monkeypatch, base_v01):
    from PySide6.QtCore import QSettings
    from lexicographe.ui import application
    monkeypatch.setattr("lexicographe.chemins.dossier_donnees", lambda *a: str(tmp_path / "donnees"))
    monkeypatch.setattr(application, "anciennes_bases", lambda: [base_v01])
    reglages = QSettings(str(tmp_path / "reglages.ini"), QSettings.IniFormat)
    projet = application.choisir_projet(reglages, premier_lancement=True)
    try:
        assert projet.nom == "Ngambay"
        assert projet.chemin.startswith(str(tmp_path / "donnees" / "Projets"))
        assert {f for _, f, *_ in lexique.lister_entrees(projet.conn)} == {"ala", "ndɔ"}
        # le corpus intégré complète la base convertie
        assert projet.conn.execute("SELECT COUNT(*) FROM phrases").fetchone()[0] == 1146
    finally:
        projet.fermer()

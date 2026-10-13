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


def aller(fenetre, nom):
    fenetre.navigation.setCurrentRow([n for n, _ in fenetre.pages].index(nom))
    return page(fenetre, nom)


def test_ouverture_et_tableau_de_bord(fenetre):
    tdb = page(fenetre, "Tableau de bord")
    assert tdb.chiffres["phrases_paralleles"].text().replace(" ", "") == "1146"
    assert int(tdb.chiffres["en_attente"].text().replace(" ", "")) > 1000


def test_validation_cree_une_entree(fenetre):
    v = aller(fenetre, "Validation")
    forme = v.forme_courante
    assert forme and "phrase(s) contiennent" in v.preuves.toPlainText()
    assert v.editeur.onglets.widget(0).exemples.rowCount() == 1, "exemple pris dans le corpus"
    v.btn_valider.click()
    assert v.forme_courante != forme
    ids = lexique.chercher_par_forme(fenetre.projet.conn, forme)
    assert len(ids) == 1
    lex = aller(fenetre, "Lexique")
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
    lex = aller(fenetre, "Lexique")
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
    c = aller(fenetre, "Corpus")
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


# -- phase 1 : lexique complet ------------------------------------------------------------

def _nouvelle_entree(lex, forme, glose):
    lex._nouvelle()
    lex.editeur.forme.setText(forme)
    lex.editeur.onglets.widget(0).glose.setText(glose)
    return lex.editeur.enregistrer()


def test_editeur_formes_variantes_composants(fenetre):
    lex = aller(fenetre, "Lexique")
    ed = lex.editeur
    a = _nouvelle_entree(lex, "kó", "arbre")
    b = _nouvelle_entree(lex, "man", "eau")
    lex._nouvelle()
    ed.forme.setText("kó-man")
    ed.forme_citation.setText("kóman")
    ed.prononciation.setText("kóˈman")
    ed.type_morph.setCurrentIndex(ed.type_morph.findData("stem"))
    ed.statut.setCurrentText("à vérifier")
    ed.onglets.widget(0).glose.setText("sève")
    ed.onglets.widget(0).inverse.setText("sève ; liquide")
    ed._ajouter_variante(lexique.Variante("kɔ́man", "variante dialectale"))
    ed.type_complexe.setEditText("composé")
    for cid in (a, b):
        ed.choix_composant.setCurrentIndex(ed.choix_composant.findData(cid))
        ed._ajouter_composant()
    eid = ed.enregistrer()
    e = lexique.lire_entree(fenetre.projet.conn, eid)
    assert (e.forme_citation, e.prononciation, e.type_morph, e.statut) == ("kóman", "kóˈman", "stem", "à vérifier")
    assert e.composants == [a, b] and e.type_forme_complexe == "composé"
    assert [(v.forme, v.type) for v in e.variantes] == [("kɔ́man", "variante dialectale")]
    assert e.sens[0].inverse == "sève ; liquide"
    # la liste affiche la vedette (forme de citation) et le statut
    lignes = {lex.liste.item(r, 0).text(): lex.liste.item(r, 3).text() for r in range(lex.liste.rowCount())}
    assert lignes["kóman"] == "à vérifier"
    # l'entrée composante indique les formes complexes qui la contiennent
    ed.charger(a)
    assert "kó-man" in ed.contenu_dans.text()


def test_homographes_affiches(fenetre):
    lex = aller(fenetre, "Lexique")
    _nouvelle_entree(lex, "ɓa", "père")
    _nouvelle_entree(lex, "ɓa", "venir")
    vedettes = [lex.liste.item(r, 0).text() for r in range(lex.liste.rowCount())]
    assert "ɓa¹" in vedettes and "ɓa²" in vedettes


def test_filtres_et_modification_en_masse(fenetre, monkeypatch):
    lex = aller(fenetre, "Lexique")
    ids = [_nouvelle_entree(lex, f, f + "-glose") for f in ("aa", "bb", "cc")]
    lex.recherche.setText("-glose")
    assert lex.liste.rowCount() == 3
    lex.liste.selectAll()
    assert sorted(lex.ids_selectionnes()) == sorted(ids) and lex.btn_masse.isEnabled()

    from lexicographe.ui import pages
    class Faux:
        def __init__(self, projet, n, parent=None):
            self.statut = type("C", (), {"currentData": lambda s: "validé"})()
            self.categorie = type("C", (), {"currentData": lambda s: None})()
            self.domaine = None
        def exec(self):
            return True
    monkeypatch.setattr(pages, "DialogueMasse", Faux)
    lex._modifier_en_masse()
    assert {lexique.lire_entree(fenetre.projet.conn, i).statut for i in ids} == {"validé"}
    lex.f_statut.setCurrentIndex(lex.f_statut.findData("validé"))
    assert lex.liste.rowCount() == 3
    lex.f_statut.setCurrentIndex(lex.f_statut.findData("brouillon"))
    assert lex.liste.rowCount() == 0


def test_index_inverse_et_navigation(fenetre):
    lex = aller(fenetre, "Lexique")
    eid = _nouvelle_entree(lex, "kó", "arbre ; bois")
    idx = aller(fenetre, "Index inverse")
    idx.recherche.setText("bois")
    assert idx.table.rowCount() == 1 and idx.table.item(0, 1).text() == "kó"
    idx.ouvrir_entree.emit(eid)
    assert fenetre.pile.currentWidget() is lex and lex.editeur.entree.id == eid


def test_page_domaines(fenetre):
    projet = fenetre.projet
    if not projet.conn.execute("SELECT 1 FROM domaines LIMIT 1").fetchone():  # FLEx absent
        from lexicographe import domaines
        domaines.importer(projet.conn, [{"guid": "g-ciel", "code": "1.1", "parent": None, "noms": {"fr": "Ciel"},
                                         "descriptions": {"fr": "Le ciel."}, "questions": []}])
    guid = projet.conn.execute("SELECT guid FROM domaines ORDER BY code LIMIT 1").fetchone()[0]
    lexique.enregistrer_entree(projet.conn, lexique.Entree(forme="dɔ", sens=[lexique.Sens(glose="ciel",
                                                                                          domaines=[guid])]))
    d = aller(fenetre, "Domaines")
    d.arbre.selectionner(guid)
    assert d.mots.rowCount() == 1 and d.mots.item(0, 0).text() == "dɔ"
    d.arbre.recherche.setText("zzzzzz-introuvable")
    assert all(item.isHidden() for item in d.arbre.items.values())


def test_import_lift_depuis_la_page(fenetre, tmp_path, monkeypatch, messages):
    from lexicographe import exports
    from PySide6.QtWidgets import QFileDialog
    autre = Projet.creer(str(tmp_path / "autre.lexique"), nom="Autre", langue_vern_code="sba")
    lexique.enregistrer_entree(autre.conn, lexique.Entree(forme="ŋgon", sens=[lexique.Sens(glose="enfant")]))
    exports.exporter_lift(autre, str(tmp_path / "autre.lift"))
    autre.fermer()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(tmp_path / "autre.lift"), ""))
    lex = aller(fenetre, "Lexique")
    lex._importer_lift()
    assert lexique.chercher_par_forme(fenetre.projet.conn, "ŋgon")
    assert any(m[0] == "info" and "1 entrée(s) créée(s)" in m[2] for m in messages)

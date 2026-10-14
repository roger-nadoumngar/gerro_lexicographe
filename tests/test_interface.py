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
    # détruire réellement la fenêtre : sinon les fenêtres des tests précédents s'accumulent
    # et chaque traitement d'événements devient plus lent
    f.deleteLater()
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


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


# -- phase 2 : textes et analyse ---------------------------------------------------------------

def _affixe(projet, forme, glose, type_morph):
    return lexique.enregistrer_entree(projet.conn, lexique.Entree(forme=forme, type_morph=type_morph,
                                                                  sens=[lexique.Sens(glose=glose)]))


def test_import_texte_et_interlineaire(fenetre, monkeypatch):
    from lexicographe import interlineaire as il
    from lexicographe.ui import pages_analyse
    projet = fenetre.projet
    _affixe(projet, "kó", "arbre", "stem")
    _affixe(projet, "-je", "PL", "suffix")

    class Faux:
        def __init__(self, texte, importer=False, parent=None):
            texte.titre, texte.genre = "Conte test", "conte"
            self.texte = texte
            self.vern = type("Z", (), {"toPlainText": lambda s: "Kóje xyz."})()
            self.trad = type("Z", (), {"toPlainText": lambda s: "Des arbres."})()
        def exec(self):
            return True
    monkeypatch.setattr(pages_analyse, "DialogueTexte", Faux)
    t = aller(fenetre, "Textes")
    t._importer()
    assert t._ref_courante == "T001 1"
    blocs = t.vue.blocs
    assert [(b.mot.texte, b.mot.statut) for b in blocs] == [("Kóje", il.PROPOSEE), ("xyz", il.INCONNUE)]

    # clic sur le mot, validation de la découpe proposée
    t.vue._clic(blocs[0])
    assert t.panneau.forme == "kóje" and t.panneau.propositions.count() == 1
    t.panneau._valider_proposition()
    assert t.vue.blocs[0].mot.statut == il.VALIDEE

    # découpe manuelle d'un mot inconnu après création de son radical
    _affixe(projet, "xy", "chose", "stem")
    _affixe(projet, "z", "DEM", "enclitic")
    t.vue._clic(t.vue.blocs[1])
    t.panneau.segmentation.setText("xy-z")
    assert [c.currentData() is not None for c in t.panneau.combos] == [True, True]
    t.panneau._valider_manuel()
    assert [b.mot.statut for b in t.vue.blocs] == [il.VALIDEE, il.VALIDEE]

    # traduction littérale enregistrée
    t.litterale.setText("arbre-PL chose-DEM")
    t._enregistrer_champs()
    assert projet.conn.execute("SELECT traduction_litterale FROM phrases WHERE ref='T001 1'").fetchone()[0] == \
        "arbre-PL chose-DEM"


def test_formes_concordance_et_navigation(fenetre):
    f = aller(fenetre, "Formes de mots")
    assert f.table.rowCount() > 1000 and "occurrences" in f.couverture.text()
    premiere = f.table.item(0, 0).text()
    f.table.setCurrentCell(0, 0)
    f._concordance()
    c = dict(fenetre.pages)["Concordance"]
    assert fenetre.pile.currentWidget() is c and c.table.rowCount() > 10
    assert c.table.item(0, 2).text().lower() == premiere
    ref = c.table.item(0, 0).text()
    c.ouvrir_phrase.emit(ref)
    t = dict(fenetre.pages)["Textes"]
    assert fenetre.pile.currentWidget() is t and t._ref_courante == ref and t.vue.blocs


def test_formes_ajout_au_lexique_avec_exemple(fenetre, messages):
    f = aller(fenetre, "Formes de mots")
    f.filtre.setCurrentIndex(f.filtre.findData("hors_lexique"))
    forme = f.table.item(0, 0).text()
    f.table.setCurrentCell(0, 0)
    eid = f._ajouter_au_lexique()
    e = lexique.lire_entree(fenetre.projet.conn, eid)
    assert e.forme == forme and e.statut == "brouillon" and e.sens[0].exemples[0].reference


# -- import FLEx ---------------------------------------------------------------------------------

def test_import_projet_flex_depuis_l_accueil(app, tmp_path, messages, monkeypatch):
    from lexicographe import flex_import
    from lexicographe.ui import application, dialogues
    from tests.test_flex import FWDATA
    dossier = tmp_path / "Projects" / "demo"
    dossier.mkdir(parents=True)
    (dossier / "demo.fwdata").write_text(FWDATA, encoding="utf-8")
    monkeypatch.setattr("lexicographe.chemins.dossier_donnees", lambda *a: str(tmp_path / "donnees"))
    monkeypatch.setattr(flex_import, "dossier_projets_flex", lambda: str(tmp_path / "Projects"))

    d = dialogues.DialogueFlex()
    assert d.liste.count() == 1 and "demo" in d.liste.item(0).text()
    d._accepter()
    assert d.chemin.endswith("demo.fwdata") and d.statut_choisi == "à vérifier" and d.textes_choisis

    projet = application.importer_projet_flex(d.chemin, d.statut_choisi, d.textes_choisis)
    try:
        assert projet.nom == "demo" and projet.reglage("langue_vern_code") == "sba"
        assert len(lexique.lister_entrees(projet.conn)) == 4
        assert any(m[0] == "info" and "4 entrée(s) créée(s)" in m[2] for m in messages)
    finally:
        projet.fermer()


def test_page_imports_et_menu(fenetre, monkeypatch):
    imports = aller(fenetre, "Imports")
    from PySide6.QtWidgets import QPushButton
    textes = [b.text() for b in imports.findChildren(QPushButton)]
    assert textes.count("Importer…") == 9
    menu = [a.text() for a in fenetre.menuBar().actions()[0].menu().actions()]
    assert "Importer un projet FLEx…" in menu and "Tous les imports…" in menu
    appels = []
    monkeypatch.setattr("lexicographe.ui.dialogues.DialogueFlex.exec", lambda self: appels.append(1) or False)
    imports.findChildren(QPushButton)[0].click()
    assert appels == [1], "le premier bouton ouvre le choix du projet FLEx"


def test_dialogue_paratext(fenetre, tmp_path, monkeypatch, messages):
    from lexicographe import paratext
    from lexicographe.ui import paratext_ui
    from tests.test_paratext import _projet_pt
    racine = tmp_path / "PT"
    _projet_pt(racine, "sbanb", "sba", "Ngambay", {"RUT": "\\id RUT\n\\c 1\n\\v 1 Kó ndɔ.\n"})
    _projet_pt(racine, "FRB", "fr", "Français", {"RUT": "\\id RUT\n\\c 1\n\\v 1 Un arbre.\n"})
    monkeypatch.setattr(paratext, "dossier_projets_paratext", lambda: str(racine))
    d = paratext_ui.DialogueParatext(fenetre.projet)
    assert d.projet_pt.nom == "sbanb", "le projet dans la langue documentée est proposé d'abord"
    assert d.cote.currentData() == "vernaculaire" and d.avec_termes.isEnabled()
    d.projets.setCurrentRow([d.projets.item(i).data(0x0100).nom for i in range(d.projets.count())].index("FRB"))
    assert d.cote.currentData() == "analyse" and not d.avec_glossaire.isEnabled()
    assert d.livres_coches() == ["RUT"]

    def choisir_frb(dialogue):
        noms = [dialogue.projets.item(i).data(0x0100).nom for i in range(dialogue.projets.count())]
        dialogue.projets.setCurrentRow(noms.index("FRB"))
        return True
    monkeypatch.setattr(paratext_ui.DialogueParatext, "exec", choisir_frb)
    assert paratext_ui.importer_paratext(fenetre, fenetre.projet)
    assert fenetre.projet.conn.execute("SELECT analyse FROM phrases WHERE ref='RUT 1:1'").fetchone()[0] == "Un arbre."
    assert any(m[0] == "info" and "1 livre(s)" in m[2] for m in messages)


def test_pages_recalculees_seulement_si_donnees_changees(fenetre, monkeypatch):
    from lexicographe.ui import pages_analyse
    appels = []
    original = pages_analyse.il.inventaire
    monkeypatch.setattr(pages_analyse.il, "inventaire", lambda p: appels.append(1) or original(p))
    f = aller(fenetre, "Formes de mots")
    aller(fenetre, "Lexique")
    aller(fenetre, "Formes de mots")
    assert len(appels) == 1, "pas de recalcul si rien n'a changé"
    # validation d'une analyse dans la page : mise à jour ciblée, sans inventaire complet
    _affixe(fenetre.projet, "ɓa", "venir", "stem")
    ligne = next(r for r in range(f.table.rowCount()) if f.table.item(r, 0).text() == "ɓa")
    f.table.setCurrentCell(ligne, 0)
    f.panneau._valider_proposition()
    assert len(appels) == 1 and f.table.item(f.table.currentRow(), 3).text() == "validée"
    aller(fenetre, "Lexique")
    lex = dict(fenetre.pages)["Lexique"]
    _nouvelle_entree(lex, "zzz", "test")
    aller(fenetre, "Formes de mots")
    assert len(appels) == 2, "recalcul après une modification faite ailleurs"


def test_colonnes_reglables_a_la_souris(fenetre):
    from PySide6.QtWidgets import QHeaderView
    lex = aller(fenetre, "Lexique")
    _nouvelle_entree(lex, "kó", "arbre")
    entete = lex.liste.horizontalHeader()
    assert {entete.sectionResizeMode(i) for i in range(lex.liste.columnCount())} == {QHeaderView.Interactive}
    lex.liste.setColumnWidth(1, 333)
    lex.rafraichir()
    assert lex.liste.columnWidth(1) == 333, "une largeur réglée par l'utilisateur est conservée"
    ed = lex.editeur
    assert ed.onglets.widget(0).exemples.horizontalHeader().sectionResizeMode(0) == QHeaderView.Interactive


def test_page_syllabaire(fenetre, tmp_path, monkeypatch, messages):
    from PySide6.QtWidgets import QFileDialog
    from lexicographe import syllabaire as sy
    s = aller(fenetre, "Syllabaire")
    assert s.ordre.count() == s.graphemes.rowCount() > 20, "une leçon par graphème du corpus"
    assert "aucun alphabet déclaré" in s.resume.text()
    s.alphabet.setText("a a̰ b ɓ d e ə g i k l m n ŋ ŋg nj o ɔ r s t u w y")
    s._enregistrer_alphabet()
    assert fenetre.projet.reglage("alphabet_vern").startswith("a a̰ b")
    lignes = {s.graphemes.item(r, 0).data(0x0100): s.graphemes.item(r, 1).text() for r in range(s.graphemes.rowCount())}
    assert lignes["ŋg"] == "lettre" and lignes["́"] == "ton"
    # réordonner puis enregistrer
    premier = s._ordre_courant[0]
    s.ordre.setCurrentRow(0)
    s._deplacer(1)
    assert s._ordre_courant[1] == premier and s.btn_enregistrer_ordre.isEnabled()
    s._enregistrer_ordre()
    assert sy.ordre_enregistre(fenetre.projet) == s._ordre_courant
    s.rafraichir()
    assert s._ordre_courant[1] == premier, "l'ordre enregistré est rechargé"
    s.ordre.setCurrentRow(5)
    assert s.mots.rowCount() >= 0 and "Leçon 6" in s.titre_lecon.text()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(tmp_path / "s.txt"), ""))
    s._exporter("txt")
    assert "Leçon 1" in open(tmp_path / "s.txt", encoding="utf-8").read()


def test_publication_depuis_les_exports(fenetre, tmp_path, monkeypatch, messages):
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QFileDialog
    from lexicographe.ui import pages
    ouverts = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: ouverts.append(url.toLocalFile()))
    monkeypatch.setattr(pages.DialoguePublication, "exec", lambda self: True)
    lex = aller(fenetre, "Lexique")
    _nouvelle_entree(lex, "kó", "arbre")
    fenetre.projet.conn.execute("UPDATE entrees SET statut='validé'")
    fenetre.projet.conn.commit()
    e = aller(fenetre, "Exports")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(tmp_path / "dico.pdf"), ""))
    e._publier("pdf", "PDF (*.pdf)", "exporter_pdf")
    assert os.path.getsize(tmp_path / "dico.pdf") > 1000 and ouverts[-1].endswith("dico.pdf")
    assert fenetre.projet.reglage("publication_titre").startswith("Dictionnaire")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    e._preparer_dab()
    assert any(m[0] == "info" and "Dictionary App Builder" in m[2] for m in messages)


# -- phase 6 : collecte communautaire -------------------------------------------------------------

def _domaines_test(projet):
    from lexicographe import domaines
    if not projet.conn.execute("SELECT 1 FROM domaines LIMIT 1").fetchone():
        domaines.importer(projet.conn, [{"guid": "d-corps", "code": "2.1", "parent": None, "noms": {"fr": "Corps"},
                                         "descriptions": {}, "questions": []}])


def test_collecte_par_domaine(fenetre):
    projet = fenetre.projet
    _domaines_test(projet)
    c = aller(fenetre, "Collecte")
    assert "à faire" in c.collecte.cartes["glose"].text() or "rien" in c.collecte.cartes["glose"].text()
    c.collecte.commencer("domaine_collecte")
    d = c.collecte.par_domaine
    assert c.collecte.pile.currentWidget() is d and d.question.text()
    guid = d.questions[d.index].guid
    d.mot.setText("Dɔ-test")
    d.glose.setText("tête")
    d._ajouter()
    (eid,) = lexique.chercher_par_forme(projet.conn, "Dɔ-test")
    e = lexique.lire_entree(projet.conn, eid)
    assert e.statut == "brouillon" and e.sens[0].domaines == [guid] and d.liste.count() >= 1
    assert d.enregistreur.entree_id == eid, "l'enregistreur est prêt pour le mot qui vient d'être ajouté"
    d._aller_a(d.index + 1)
    from lexicographe import collecte
    assert collecte.position_enregistree(projet)["guid"] == d.questions[d.index].guid
    d.retour.emit()
    assert c.collecte.pile.currentIndex() == 0


def test_taches_de_complement(fenetre):
    projet = fenetre.projet
    lex = aller(fenetre, "Lexique")
    _nouvelle_entree(lex, "zza", "")
    c = aller(fenetre, "Collecte")
    c.collecte.commencer("glose")
    f = c.collecte.fiche
    assert f.ids and f.champ.isVisibleTo(f) and not f.btn_domaine.isVisibleTo(f)
    rang = f.ids.index(lexique.chercher_par_forme(projet.conn, "zza")[0])
    f.index = rang
    f._afficher()
    f.champ.setText("essai")
    f._valider()
    assert lexique.lire_entree(projet.conn, f.ids[rang]).sens[0].glose == "essai"
    c.collecte.commencer("exemple")
    assert f.champ2.isVisibleTo(f)
    c.collecte.commencer("audio")
    assert f.enregistreur.isVisibleTo(f) and not f.btn_valider.isVisibleTo(f)


def test_mode_locuteur(fenetre):
    from lexicographe.ui.collecte_ui import ModeLocuteur
    d = ModeLocuteur(fenetre.projet, fenetre)
    assert d.collecte.pile.currentIndex() == 0 and d.font().pointSizeF() > fenetre.font().pointSizeF()
    d.done(0)


def test_fusion_depuis_les_imports(fenetre, tmp_path, monkeypatch, messages):
    from PySide6.QtWidgets import QFileDialog
    from lexicographe.projet import Projet
    autre = str(tmp_path / "poste2.lexique")
    fenetre.projet.sauvegarder_vers(autre)
    p2 = Projet(autre)
    lexique.enregistrer_entree(p2.conn, lexique.Entree(forme="motdeposte2", sens=[lexique.Sens(glose="x")]))
    p2.fermer()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (autre, ""))
    fenetre._fusionner()
    assert lexique.chercher_par_forme(fenetre.projet.conn, "motdeposte2")
    assert any(m[0] == "info" and "1 entrée(s) ajoutée(s)" in m[2] for m in messages)

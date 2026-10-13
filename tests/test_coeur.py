import json
import sqlite3
import xml.etree.ElementTree as ET

import pytest

from lexicographe import alignement, base, corpus, exports, lexique, usfm
from lexicographe.lexique import Entree, Exemple, Sens
from lexicographe.projet import Projet
from lexicographe.texte import Tokeniseur, normaliser


# -- texte ------------------------------------------------------------------------

def test_normalisation_unifie_les_formes():
    assert normaliser("ko\u0301") == normaliser("kó")


def test_tokeniseur_garde_les_marques_combinantes():
    tok = Tokeniseur("-")
    assert tok.mots("Ka̰ Boaj, yeḛ!") == ["ka̰", "boaj", "yeḛ"]


def test_tokeniseur_apostrophe_selon_la_regle_declaree():
    assert Tokeniseur("-").mots("dee’g d’aw") == ["dee", "g", "d", "aw"]
    assert Tokeniseur("-’").mots("dee’g d’aw") == ["dee’g", "d’aw"]


def test_tokeniseur_bordures_et_longueur_minimale():
    tok = Tokeniseur("-’", longueur_min=2)
    assert tok.mots("- pəl-pəl ’g a") == ["pəl-pəl"]
    # une marque combinante ne compte pas comme une lettre
    assert Tokeniseur("", longueur_min=2).mots("a̰ ka̰") == ["ka̰"]


def test_mots_vides():
    tok = Tokeniseur("-", mots_vides=["le", "de"])
    assert tok.mots_pleins("Le nom de l'homme") == ["nom", "l", "homme"]


# -- projet et migrations -----------------------------------------------------------

def test_creation_projet(projet):
    assert base.version(projet.conn) == base.VERSION_SCHEMA
    assert projet.reglage("langue_vern_code") == "sba"
    assert any(nom == "nom" for _, nom, _, _ in lexique.categories(projet.conn))


def test_reouverture_ne_rejoue_pas_les_migrations(projet):
    chemin = projet.chemin
    lexique.enregistrer_entree(projet.conn, Entree(forme="ala", sens=[Sens(glose="dieu")]))
    projet.fermer()
    p2 = Projet(chemin)
    assert len(lexique.lister_entrees(p2.conn)) == 1
    p2.fermer()


def test_projet_plus_recent_refuse(tmp_path):
    chemin = str(tmp_path / "futur.lexique")
    conn = sqlite3.connect(chemin)
    conn.execute(f"PRAGMA user_version = {base.VERSION_SCHEMA + 1}")
    conn.close()
    with pytest.raises(RuntimeError):
        Projet(chemin)


def test_import_v01(base_v01, tmp_path):
    with open(base_v01, "rb") as f:
        avant = f.read()
    p = Projet.importer_v01(base_v01, str(tmp_path / "ngambay.lexique"))
    with open(base_v01, "rb") as f:
        assert f.read() == avant, "la base d'origine ne doit pas être modifiée"

    conn = p.conn
    assert p.reglage("caracteres_mot_vern") == "-"
    assert conn.execute("SELECT vernaculaire, analyse FROM phrases").fetchall() == [("Ala ndɔ", "Dieu jour")]
    entrees = {forme: eid for eid, forme, *_ in lexique.lister_entrees(conn)}
    assert set(entrees) == {"ala", "ndɔ"}

    ala = lexique.lire_entree(conn, entrees["ala"])
    s = ala.sens[0]
    assert (s.glose, s.definition, s.domaine) == ("dieu", "être suprême", "religion / spirituel")
    assert lexique.nom_categorie(conn, s.categorie_id) == "nom"
    assert (s.exemples[0].vernaculaire, s.exemples[0].traduction) == ("Ala ndɔ", "Dieu jour")
    assert ala.proprietes == {"genre (traduction)": "masculin", "nombre (traduction)": "singulier"}
    assert "Relation non reliée : synonyme → inconnu" in ala.notes
    assert [(t, f) for _, t, _, f in lexique.relations(conn, ala.id)] == [("voir aussi", "ndɔ")]

    statuts = dict(conn.execute("SELECT forme, statut FROM hypotheses"))
    assert statuts == {"ala": "valide", "ndɔ": "valide", normaliser("kó"): "en_attente", "bé": "rejete"}
    assert conn.execute("SELECT forme, nouvelle FROM contradictions").fetchall() == [("ala", "seigneur")]
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not any(t.startswith("_v01_") for t in tables)
    p.fermer()


# -- lexique --------------------------------------------------------------------------

def test_entree_plusieurs_sens(projet):
    conn = projet.conn
    e = Entree(forme="ko\u0301", notes="n", proprietes={"ton": "haut"}, sens=[
        Sens(glose="arbre", exemples=[Exemple("kó ndɔ", "un arbre", "RUT 1:1")]),
        Sens(glose="bois")])
    eid = lexique.enregistrer_entree(conn, e)
    lu = lexique.lire_entree(conn, eid)
    assert lu.forme == "kó"
    assert [s.glose for s in lu.sens] == ["arbre", "bois"]
    assert lu.sens[0].exemples[0].reference == "RUT 1:1"
    assert lu.proprietes == {"ton": "haut"}

    lu.sens.pop(0)
    lexique.enregistrer_entree(conn, lu)
    assert [s.glose for s in lexique.lire_entree(conn, eid).sens] == ["bois"]
    assert conn.execute("SELECT COUNT(*) FROM exemples").fetchone()[0] == 0


def test_relations(projet):
    conn = projet.conn
    a = lexique.enregistrer_entree(conn, Entree(forme="a", sens=[Sens(glose="x")]))
    b = lexique.enregistrer_entree(conn, Entree(forme="b", sens=[Sens(glose="y")]))
    assert lexique.ajouter_relation(conn, a, b, "synonyme")
    assert not lexique.ajouter_relation(conn, a, b, "synonyme")
    with pytest.raises(ValueError):
        lexique.ajouter_relation(conn, a, a, "synonyme")
    lexique.supprimer_entree(conn, b)
    assert lexique.relations(conn, a) == []


def test_recherche(projet):
    conn = projet.conn
    lexique.enregistrer_entree(conn, Entree(forme="ala", sens=[Sens(glose="dieu")]))
    lexique.enregistrer_entree(conn, Entree(forme="ndɔ", sens=[Sens(glose="jour")]))
    assert [r[1] for r in lexique.lister_entrees(conn, "DIEU")] == ["ala"]
    assert [r[1] for r in lexique.lister_entrees(conn, "nd")] == ["ndɔ"]


# -- alignement --------------------------------------------------------------------

def _corpus(projet, paires):
    with projet.conn:
        projet.conn.executemany("INSERT INTO phrases (ref, vernaculaire, analyse, source) VALUES (?,?,?,?)",
                                [(f"T 1:{i}", v, a, "test") for i, (v, a) in enumerate(paires, 1)])


def test_alignement_et_preuves(projet):
    _corpus(projet, [("kó ndɔ", "un arbre et le jour"), ("kó", "arbre"), ("ndɔ ala", "jour Dieu")])
    alignement.recalculer(projet)
    hyp = {f: (c, s) for f, _, c, s, _, _ in alignement.file_validation(projet)}
    assert hyp["kó"][0] == "arbre" and hyp["kó"][1] == 1.0
    assert hyp["ndɔ"][0] == "jour"
    assert [r for r, _, _ in alignement.preuves(projet, "kó", "arbre")] == ["T 1:1", "T 1:2"]


def test_validation_et_contradiction(projet):
    _corpus(projet, [("kó", "arbre"), ("kó ndɔ", "arbre jour")])
    alignement.recalculer(projet)
    alignement.valider(projet, "kó", Entree(forme="kó", sens=[Sens(glose="bois")]))
    assert alignement.recalculer(projet) == 1
    assert alignement.recalculer(projet) == 0, "une contradiction n'est signalée qu'une fois"
    (cid, forme, ancienne, nouvelle), = alignement.contradictions_ouvertes(projet)
    assert (forme, ancienne, nouvelle) == ("kó", "bois", "arbre")
    alignement.resoudre_contradiction(projet, cid, adopter=True)
    eid = projet.conn.execute("SELECT entree_id FROM hypotheses WHERE forme='kó'").fetchone()[0]
    assert lexique.lire_entree(projet.conn, eid).sens[0].glose == "arbre"
    assert alignement.contradictions_ouvertes(projet) == []


def test_glose_validee_conforme_pas_de_contradiction(projet):
    _corpus(projet, [("kó", "arbre"), ("kó ndɔ", "arbre jour")])
    alignement.recalculer(projet)
    alignement.valider(projet, "kó", Entree(forme="kó", sens=[Sens(glose="un arbre")]))
    assert alignement.recalculer(projet) == 0


def test_hypotheses_perimees_supprimees(projet):
    _corpus(projet, [("dee’g", "lui")])
    alignement.recalculer(projet)
    assert {f for f, *_ in alignement.file_validation(projet)} == {"dee’g"}
    projet.definir_reglages({"caracteres_mot_vern": "-"})
    alignement.recalculer(projet)
    assert {f for f, *_ in alignement.file_validation(projet)} == {"dee", "g"}


def test_rejet_et_suppression_entree(projet):
    _corpus(projet, [("kó", "arbre")])
    alignement.recalculer(projet)
    alignement.rejeter(projet, "kó")
    assert alignement.file_validation(projet) == []
    alignement.remettre_en_attente(projet, "kó")
    eid = alignement.valider(projet, "kó", Entree(forme="kó", sens=[Sens(glose="arbre")]))
    lexique.supprimer_entree(projet.conn, eid)
    assert [f for f, *_ in alignement.file_validation(projet)] == ["kó"]


# -- corpus intégré et USFM ----------------------------------------------------------

def test_corpus_integre(projet):
    projet.definir_reglages({"corpus_integre": "ngambay_ruth_job"})
    assert corpus.synchroniser(projet) == 1146
    texte = projet.conn.execute("SELECT vernaculaire FROM phrases WHERE ref='RUT 2:3'").fetchone()[0]
    assert "|" not in texte
    # un verset importé par l'utilisateur n'est jamais réécrit
    with projet.conn:
        projet.conn.execute("UPDATE phrases SET vernaculaire='perso', source='mon.usfm' WHERE ref='RUT 1:1'")
    corpus.synchroniser(projet)
    assert projet.conn.execute("SELECT vernaculaire FROM phrases WHERE ref='RUT 1:1'").fetchone()[0] == "perso"


def test_usfm():
    texte = ('\\id RUT Ruth\n\\h Ruth\n\\c 1\n\\s1 Titre de section\n\\p\n'
             '\\v 1 Mot \\w ka\u0301g|lemma="x"\\w* \\f + \\ft note\\f* fin.\n'
             '\\q1 suite du verset\n\\v 2-3 Deux \\fig Légende|src="a.tif"\\fig*\n')
    versets, code = usfm.analyser_usfm(texte)
    assert code == "RUT"
    assert versets == {"RUT 1:1": "Mot kág fin. suite du verset", "RUT 1:2": "Deux"}


def test_import_usfm(projet):
    assert usfm.importer(projet, {"RUT 1:1": "a"}, "vernaculaire", "x.usfm") == (1, 0)
    assert usfm.importer(projet, {"RUT 1:1": "b"}, "analyse", "y.usfm") == (0, 1)
    assert projet.conn.execute("SELECT vernaculaire, analyse FROM phrases").fetchone() == ("a", "b")


# -- exports ---------------------------------------------------------------------------

def _lexique_exemple(projet):
    conn = projet.conn
    cat = conn.execute("SELECT id FROM categories WHERE nom='nom'").fetchone()[0]
    a = lexique.enregistrer_entree(conn, Entree(forme="ala", notes="n", proprietes={"ton": "bas"}, sens=[
        Sens(glose="dieu", definition="être <suprême> & créateur", categorie_id=cat, domaine="religion",
             exemples=[Exemple("Ala ndɔ", "Dieu jour", "RUT 1:1")]),
        Sens(glose="ciel")]))
    b = lexique.enregistrer_entree(conn, Entree(forme="ndɔ", sens=[Sens(glose="jour")]))
    lexique.ajouter_relation(conn, a, b, "voir aussi")


def test_lift(projet, tmp_path):
    _lexique_exemple(projet)
    chemin = str(tmp_path / "t.lift")
    assert exports.exporter_lift(projet, chemin) == 2
    racine = ET.parse(chemin).getroot()
    entrees = racine.findall("entry")
    ids = {e.get("id") for e in entrees}
    ala = next(e for e in entrees if e.find("lexical-unit/form/text").text == "ala")
    assert ala.find("lexical-unit/form").get("lang") == "sba"
    assert [s.find("gloss/text").text for s in ala.findall("sense")] == ["dieu", "ciel"]
    assert ala.find("sense/grammatical-info").get("value") == "nom"
    assert ala.find("sense/definition/form/text").text == "être <suprême> & créateur"
    assert ala.find("sense/example").get("source") == "RUT 1:1"
    assert ala.find("sense/example/translation/form/text").text == "Dieu jour"
    assert all(r.get("ref") in ids for r in racine.iter("relation"))


def test_exports_texte(projet, tmp_path):
    _lexique_exemple(projet)
    assert exports.exporter_json(projet, str(tmp_path / "t.json")) == 2
    donnees = json.load(open(tmp_path / "t.json", encoding="utf-8"))
    assert donnees["entrees"][0]["relations"] == [{"type": "voir aussi", "forme": "ndɔ"}]
    assert exports.exporter_csv(projet, str(tmp_path / "t.csv")) == 2
    assert len(open(tmp_path / "t.csv", encoding="utf-8-sig").read().splitlines()) == 4
    assert exports.exporter_texte(projet, str(tmp_path / "t.txt")) == 2
    assert "1. (nom, religion) dieu" in open(tmp_path / "t.txt", encoding="utf-8").read()


def test_decouper_conserve_le_texte():
    tok = Tokeniseur("-’", longueur_min=2)
    texte = "Deḛ d’ḭ ɓee, - a pəl-pəl’!"
    morceaux = tok.decouper(texte)
    assert "".join(m for m, _ in morceaux) == normaliser(texte)
    assert [m for _, m in morceaux if m] == tok.mots(texte)


def test_tri_canonique_des_references():
    refs = ["JOB 1:1", "RUT 1:10", "MANUEL x", "RUT 1:9", "RUT 2:1", "GEN 50:1", "XYZ 1:1"]
    assert sorted(refs, key=usfm.cle_reference) == ["GEN 50:1", "RUT 1:9", "RUT 1:10", "RUT 2:1", "JOB 1:1",
                                                    "XYZ 1:1", "MANUEL x"]

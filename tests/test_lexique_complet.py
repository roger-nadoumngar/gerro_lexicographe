import os
import xml.etree.ElementTree as ET

import pytest

from lexicographe import base, domaines, exports, lexique, lift_import
from lexicographe.lexique import Entree, Exemple, Sens, Variante
from lexicographe.projet import Projet
from lexicographe.texte import OrdreAlphabetique

FLEX_FR = r"C:\Program Files\SIL\FieldWorks 9\Templates\LocalizedLists-fr.zip"
BIATAH = r"C:\ProgramData\SIL\WeSay\Samples\biatah\biatah.lift"

DOMAINES_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Lists><List owner="LangProject" field="SemanticDomainList" itemClass="CmSemanticDomain"><Possibilities>
  <CmSemanticDomain guid="AAAA0001-0000-0000-0000-000000000001">
    <Name><AUni ws="en">Universe, creation</AUni><AUni ws="fr">L’univers, la création</AUni></Name>
    <Abbreviation><AUni ws="en">1</AUni></Abbreviation>
    <Questions><CmDomainQ><Question><AUni ws="fr">(1) Quels mots désignent tout ?</AUni></Question>
      <ExampleWords><AUni ws="fr">univers, cosmos</AUni></ExampleWords></CmDomainQ></Questions>
    <SubPossibilities>
      <CmSemanticDomain guid="AAAA0001-0000-0000-0000-000000000002">
        <Name><AUni ws="en">Sky</AUni><AUni ws="fr">Ciel</AUni></Name>
        <Abbreviation><AUni ws="en">1.1</AUni></Abbreviation>
        <Description><AStr ws="fr"><Run ws="fr">Vocabulaire du ciel.</Run></AStr></Description>
        <Questions><CmDomainQ><Question><AUni ws="fr">(1) Le ciel ?</AUni></Question>
          <ExampleWords><AUni ws="fr">firmament, azur</AUni></ExampleWords></CmDomainQ></Questions>
      </CmSemanticDomain>
      <CmSemanticDomain guid="AAAA0001-0000-0000-0000-000000000010">
        <Name><AUni ws="fr">Eau</AUni></Name><Abbreviation><AUni ws="en">1.10</AUni></Abbreviation>
      </CmSemanticDomain>
      <CmSemanticDomain guid="AAAA0001-0000-0000-0000-000000000009">
        <Name><AUni ws="fr">Lune</AUni></Name><Abbreviation><AUni ws="en">1.9</AUni></Abbreviation>
      </CmSemanticDomain>
    </SubPossibilities>
  </CmSemanticDomain>
</Possibilities></List></Lists>"""

CIEL = "aaaa0001-0000-0000-0000-000000000002"


@pytest.fixture
def avec_domaines(projet, tmp_path):
    chemin = tmp_path / "domaines.xml"
    chemin.write_text(DOMAINES_XML, encoding="utf-8")
    domaines.importer(projet.conn, domaines.lire_liste(str(chemin)))
    return projet


# -- migration -----------------------------------------------------------------------

def test_migration_2_depuis_un_projet_phase_0(tmp_path):
    chemin = str(tmp_path / "ancien.lexique")
    conn = base.connecter(chemin)
    conn.isolation_level = None
    conn.execute("BEGIN")
    base._migration_1(conn)
    conn.execute("PRAGMA user_version = 1")
    conn.execute("INSERT INTO entrees (guid, forme) VALUES ('g1', 'ala')")
    conn.execute("COMMIT")
    conn.close()
    p = Projet(chemin)
    assert base.version(p.conn) == base.VERSION_SCHEMA
    e = lexique.lire_entree(p.conn, 1)
    assert e.statut == "validé" and e.variantes == [] and e.composants == []
    p.fermer()


# -- domaines sémantiques ------------------------------------------------------------

def test_lecture_domaines_et_questions_propres(avec_domaines):
    conn = avec_domaines.conn
    assert domaines.nombre(conn) == 4
    racine = domaines.details(conn, "aaaa0001-0000-0000-0000-000000000001")
    assert racine["nom"] == "L’univers, la création"
    assert len(racine["questions"]) == 1, "les questions des sous-domaines ne remontent pas au parent"
    ciel = domaines.details(conn, CIEL)
    assert ciel["description"] == "Vocabulaire du ciel." and ciel["questions"][0]["mots"] == "firmament, azur"
    assert [c for _, c, _, _ in domaines.arbre(conn)] == ["1", "1.1", "1.9", "1.10"]
    assert [c for _, c, _ in domaines.chercher(conn, "azur")] == ["1.1"]


def test_domaines_des_sens_et_filtre_hierarchique(avec_domaines):
    conn = avec_domaines.conn
    eid = lexique.enregistrer_entree(conn, Entree(forme="dɔ", sens=[Sens(glose="ciel", domaines=[CIEL])]))
    lexique.enregistrer_entree(conn, Entree(forme="man", sens=[Sens(glose="eau")]))
    assert lexique.lire_entree(conn, eid).sens[0].domaines == [CIEL]
    assert [l.forme for l in lexique.lister_entrees(conn, domaine_code="1")] == ["dɔ"]
    assert [l.forme for l in lexique.lister_entrees(conn, domaine_code="1.1")] == ["dɔ"]
    assert lexique.lister_entrees(conn, domaine_code="1.10") == []
    assert domaines.sens_du_domaine(conn, CIEL) == [(eid, "dɔ", "ciel")]
    # réimporter la liste conserve les classements
    domaines.importer(conn, [{"guid": CIEL, "code": "1.1", "parent": None, "noms": {"fr": "Ciel"},
                              "descriptions": {}, "questions": []}])
    assert lexique.lire_entree(conn, eid).sens[0].domaines == [CIEL]


@pytest.mark.skipif(not os.path.isfile(FLEX_FR), reason="FLEx n'est pas installé")
def test_liste_officielle_flex(projet):
    chemin = domaines.charger_depuis_flex(projet.conn, "fr")
    assert chemin and chemin.endswith("LocalizedLists-fr.zip")
    assert domaines.nombre(projet.conn) == 1792
    assert domaines.libelle(projet.conn, domaines.par_code(projet.conn, "1.1")) == "1.1 Ciel"
    assert domaines.charger_depuis_flex(projet.conn, "fr") is None, "déjà chargée : pas de rechargement"


# -- ordre alphabétique et homographes ------------------------------------------------

def test_ordre_alphabetique_declare():
    ordre = OrdreAlphabetique("a b ɓ d ɗ e ə g i k m n ŋ ŋg o ɔ")
    mots = ["ŋgon", "ɓa", "ba", "ŋa", "nan", "da", "ɗa", "ka̰", "ká", "ka"]
    assert sorted(mots, key=ordre.cle) == ["ba", "ɓa", "da", "ɗa", "ka", "ká", "ka̰", "nan", "ŋa", "ŋgon"]
    assert ordre.initiale("ŋgon") == "ŋg" and ordre.initiale("Ɓa") == "ɓ"


def test_ordre_sans_alphabet_ignore_les_accents():
    assert sorted(["éb", "ea", "ec"], key=OrdreAlphabetique().cle) == ["ea", "éb", "ec"]


def test_homographes_et_tri_du_projet(projet):
    conn = projet.conn
    projet.definir_reglages({"alphabet_vern": "a b ɓ d"})
    a1 = lexique.enregistrer_entree(conn, Entree(forme="ɓa", sens=[Sens(glose="x")]))
    lexique.enregistrer_entree(conn, Entree(forme="da", sens=[Sens(glose="y")]))
    a2 = lexique.enregistrer_entree(conn, Entree(forme="ɓa", sens=[Sens(glose="z")]))
    lexique.enregistrer_entree(conn, Entree(forme="ba", sens=[Sens(glose="w")]))
    lignes = lexique.lister_entrees(conn)
    assert [l.forme for l in lignes] == ["ba", "ɓa", "ɓa", "da"]
    assert {l.id: l.homographe for l in lignes if l.forme == "ɓa"} == {a1: 1, a2: 2}
    assert lexique.vedette("ɓa", 2) == "ɓa²"
    assert lexique.libelle_entree(conn, a2) == "ɓa² — z"


# -- formes, variantes, composants, statut ---------------------------------------------

def test_entree_complete_aller_retour(projet):
    conn = projet.conn
    mot = lexique.enregistrer_entree(conn, Entree(forme="kó", sens=[Sens(glose="arbre")]))
    eau = lexique.enregistrer_entree(conn, Entree(forme="man", sens=[Sens(glose="eau")]))
    e = Entree(forme="kó-man", forme_citation="kóman", prononciation="kóˈman", type_morph="stem",
               statut="à vérifier", type_forme_complexe="composé", composants=[mot, eau],
               variantes=[Variante("kɔ́man", "variante dialectale", note="sud"),
                          Variante("-man", "allomorphe", environnement="après voyelle")],
               sens=[Sens(glose="sève", inverse="sève ; liquide d'arbre")])
    eid = lexique.enregistrer_entree(conn, e)
    lu = lexique.lire_entree(conn, eid)
    assert (lu.forme_citation, lu.prononciation, lu.statut, lu.tete) == ("kóman", "kóˈman", "à vérifier", "kóman")
    assert lu.composants == [mot, eau] and lu.type_forme_complexe == "composé"
    assert [(v.forme, v.type, v.environnement) for v in lu.variantes] == [
        ("kɔ́man", "variante dialectale", ""), ("-man", "allomorphe", "après voyelle")]
    assert lexique.formes_inverses(lu.sens[0]) == ["sève", "liquide d'arbre"]
    assert lexique.formes_complexes_de(conn, mot) == [(eid, "kó-man")]
    assert [l.forme for l in lexique.lister_entrees(conn, "kɔ́man")] == ["kó-man"], "recherche dans les variantes"
    with pytest.raises(ValueError):
        lu.composants.append(eid)
        lexique.enregistrer_entree(conn, lu)


def test_statut_inconnu_refuse(projet):
    with pytest.raises(ValueError):
        lexique.enregistrer_entree(projet.conn, Entree(forme="a", statut="fini"))


def test_modification_en_masse(avec_domaines):
    conn = avec_domaines.conn
    ids = [lexique.enregistrer_entree(conn, Entree(forme=f, sens=[Sens(glose=f), Sens(glose=f + "2")]))
           for f in ("a", "b")]
    nom = conn.execute("SELECT id FROM categories WHERE nom='nom'").fetchone()[0]
    assert lexique.modifier_en_masse(conn, ids, statut="validé", categorie_id=nom, ajouter_domaine=CIEL) == 2
    for eid in ids:
        e = lexique.lire_entree(conn, eid)
        assert e.statut == "validé"
        assert all(s.categorie_id == nom and s.domaines == [CIEL] for s in e.sens)
    assert [l.forme for l in lexique.lister_entrees(conn, statut="validé", categorie_id=nom)] == ["a", "b"]


def test_categories_hierarchiques(projet):
    conn = projet.conn
    nom = lexique.categorie_par_nom(conn, "nom")
    comptable = lexique.ajouter_categorie(conn, "nom comptable", "n.c", parent_id=nom)
    arbre = {c[1]: c[3] for c in lexique.categories_arbre(conn)}
    assert arbre["nom"] == 0 and arbre["nom comptable"] == 1
    with pytest.raises(ValueError):
        lexique.deplacer_categorie(conn, nom, comptable)
    lexique.supprimer_categorie(conn, nom)
    assert conn.execute("SELECT parent_id FROM categories WHERE id=?", (comptable,)).fetchone()[0] is None


def test_index_inverse(projet):
    conn = projet.conn
    lexique.enregistrer_entree(conn, Entree(forme="kó", sens=[Sens(glose="arbre ; bois")]))
    lexique.enregistrer_entree(conn, Entree(forme="ɗek", sens=[Sens(glose="bois", inverse="bois de chauffe")]))
    index = dict(lexique.index_inverse(conn))
    assert [x[1] for x in index["bois"]] == ["kó"]
    assert [x[1] for x in index["bois de chauffe"]] == ["ɗek"]
    assert list(index) == ["arbre", "bois", "bois de chauffe"]


def test_medias(projet, tmp_path):
    conn = projet.conn
    eid = lexique.enregistrer_entree(conn, Entree(forme="a", sens=[Sens(glose="x")]))
    lexique.lier_media(conn, eid, str(tmp_path / "a.wav"), "prononciation", "locuteur 1")
    (lien, _, role, _, nom, _, note), = lexique.medias_de(conn, eid)
    assert (role, nom, note) == ("prononciation", "a.wav", "locuteur 1")
    lexique.delier_media(conn, lien)
    assert lexique.medias_de(conn, eid) == []


# -- LIFT : export puis import --------------------------------------------------------------

def _lexique_riche(projet):
    conn = projet.conn
    cat = lexique.categorie_par_nom(conn, "nom")
    a = lexique.enregistrer_entree(conn, Entree(forme="kó", sens=[Sens(glose="arbre", categorie_id=cat,
                                                                          domaines=[CIEL])]))
    b = lexique.enregistrer_entree(conn, Entree(forme="man", sens=[Sens(glose="eau")]))
    c = lexique.enregistrer_entree(conn, Entree(
        forme="kó-man", forme_citation="kóman", prononciation="kóˈman", type_morph="stem", statut="validé",
        type_forme_complexe="composé", composants=[a, b], notes="note", proprietes={"ton": "HB"},
        variantes=[Variante("kɔ́man", "variante dialectale")],
        sens=[Sens(glose="sève", inverse="sève ; liquide", definition="liquide des plantes",
                   exemples=[Exemple("kóman ɓa", "la sève coule", "RUT 1:1")])]))
    lexique.ajouter_relation(conn, a, b, "voir aussi")
    return a, b, c


def test_lift_export_complet(avec_domaines, tmp_path):
    _lexique_riche(avec_domaines)
    chemin = str(tmp_path / "x.lift")
    exports.exporter_lift(avec_domaines, chemin)
    racine = ET.parse(chemin).getroot()
    km = next(e for e in racine.findall("entry") if e.find("lexical-unit/form/text").text == "kó-man")
    assert km.find("citation/form/text").text == "kóman"
    assert km.find("pronunciation/form").get("lang") == "sba-fonipa"
    assert km.find("variant/form/text").text == "kɔ́man"
    assert [r.get("type") for r in km.findall("relation")] == ["_component-lexeme", "_component-lexeme"]
    assert {t.get("name"): t.get("value") for t in km.findall("trait")}["morph-type"] == "stem"
    assert [r.find("form/text").text for r in km.findall("sense/reversal")] == ["sève", "liquide"]
    ko = next(e for e in racine.findall("entry") if e.find("lexical-unit/form/text").text == "kó")
    assert ko.find("sense/trait[@name='semantic-domain-ddp4']").get("value") == "1.1 Ciel"


def test_lift_aller_retour(avec_domaines, tmp_path):
    _lexique_riche(avec_domaines)
    chemin = str(tmp_path / "x.lift")
    exports.exporter_lift(avec_domaines, chemin)

    cible = Projet.creer(str(tmp_path / "cible.lexique"), nom="Cible", langue_vern_code="sba")
    domaines.importer(cible.conn, domaines.lire_liste(str(tmp_path / "domaines.xml")))
    rapport = lift_import.importer(cible, chemin)
    assert (rapport.creees, rapport.mises_a_jour, rapport.avertissements) == (3, 0, [])
    conn = cible.conn
    km = lexique.lire_entree(conn, lexique.chercher_par_forme(conn, "kó-man")[0])
    assert (km.forme_citation, km.prononciation, km.type_morph, km.statut) == ("kóman", "kóˈman", "stem", "validé")
    assert [lexique.lire_entree(conn, c).forme for c in km.composants] == ["kó", "man"]
    assert km.type_forme_complexe == "composé" and km.proprietes == {"ton": "HB"} and km.notes == "note"
    assert [(v.forme, v.type) for v in km.variantes] == [("kɔ́man", "variante dialectale")]
    s = km.sens[0]
    assert (s.glose, s.definition, s.inverse) == ("sève", "liquide des plantes", "sève ; liquide")
    assert (s.exemples[0].vernaculaire, s.exemples[0].traduction, s.exemples[0].reference) == \
        ("kóman ɓa", "la sève coule", "RUT 1:1")
    ko = lexique.lire_entree(conn, lexique.chercher_par_forme(conn, "kó")[0])
    assert ko.sens[0].domaines == [CIEL] and lexique.nom_categorie(conn, ko.sens[0].categorie_id) == "nom"
    assert [(t, f) for _, t, _, f in lexique.relations(conn, ko.id)] == [("voir aussi", "man")]

    # réimporter le même fichier met à jour au lieu de dupliquer
    rapport = lift_import.importer(cible, chemin)
    assert (rapport.creees, rapport.mises_a_jour) == (0, 3)
    assert conn.execute("SELECT COUNT(*) FROM entrees").fetchone()[0] == 3
    cible.fermer()


@pytest.mark.skipif(not os.path.isfile(BIATAH), reason="exemple WeSay absent")
def test_import_lexique_wesay_reel(tmp_path):
    p = Projet.creer(str(tmp_path / "biatah.lexique"), nom="Biatah", langue_vern_code="bth",
                     langue_analyse_code="en")
    rapport = lift_import.importer(p, BIATAH)
    vivantes = p.conn.execute("SELECT COUNT(*) FROM entrees").fetchone()[0]
    assert rapport.creees == vivantes > 2500
    assert rapport.supprimees_ignorees > 0
    assert p.conn.execute("SELECT COUNT(*) FROM entrees WHERE prononciation IS NOT NULL").fetchone()[0] > 1000
    assert p.conn.execute("SELECT COUNT(*) FROM composants").fetchone()[0] > 500
    p.fermer()

import hashlib
import os

import pytest

from lexicographe import lexique, paratext
from lexicographe.lexique import Entree, Sens

SETTINGS = """<ScriptureText>
  <Versification>{versif}</Versification>
  <Language>{langue}</Language>
  <FullName>{complet}</FullName>
  <Name>{nom}</Name>
  <LanguageIsoCode>{code}:::</LanguageIsoCode>
  <FileNameBookNameForm>41MAT</FileNameBookNameForm>
  <FileNamePostPart>{nom}.SFM</FileNamePostPart>
</ScriptureText>"""

LEXICON = """<?xml version="1.0" encoding="utf-8"?>
<Lexicon><Language>sba</Language><Entries>
  <item><Lexeme Type="Word" Form="bɔ" Homograph="1" /><Entry>
    <Sense Id="a"><Gloss Language="fr">père</Gloss></Sense>
    <Sense Id="b"><Gloss Language="en">father</Gloss></Sense></Entry></item>
  <item><Lexeme Type="Suffix" Form="je" Homograph="1" /><Entry>
    <Sense Id="c"><Gloss Language="fr">PL</Gloss></Sense></Entry></item>
  <item><Lexeme Type="Word" Form="ala" Homograph="1" /><Entry>
    <Sense Id="d"><Gloss Language="fr">dieu</Gloss></Sense></Entry></item>
</Entries></Lexicon>"""

RENDUS = """<?xml version="1.0" encoding="utf-8"?>
<TermRenderingsList>
  <TermRendering Id="Βηθλέεμ" Guess="false"><Renderings>Betilehem*</Renderings></TermRendering>
  <TermRendering Id="אֱדוֹם" Guess="false"><Renderings>Edom||Edɔm</Renderings></TermRendering>
  <TermRendering Id="ἄγγελος" Guess="true"><Renderings>malaika</Renderings></TermRendering>
  <TermRendering Id="vide" Guess="false"><Renderings /></TermRendering>
  <TermRendering Id="βασιλεία τοῦ θεοῦ" Guess="false"><Renderings>Gin-ŋgar lə Ala</Renderings></TermRendering>
</TermRenderingsList>"""

TERMES = """<?xml version="1.0" encoding="utf-8"?>
<BiblicalTermsList>
  <Term Id="Βηθλέεμ"><Category>PN</Category><Gloss>Bethlehem</Gloss></Term>
  <Term Id="אֱדוֹם"><Category>PN</Category><Gloss>Edom</Gloss></Term>
  <Term Id="βασιλεία τοῦ θεοῦ"><Category>MI</Category><Gloss>kingdom of God</Gloss></Term>
</BiblicalTermsList>"""


def _projet_pt(racine, nom, code, langue, livres, versif="4", extras=None):
    dossier = racine / nom
    dossier.mkdir(parents=True)
    (dossier / "Settings.xml").write_text(SETTINGS.format(nom=nom, code=code, langue=langue, complet=f"Bible {langue}",
                                                          versif=versif), encoding="utf-8")
    for i, (code_livre, contenu) in enumerate(livres.items(), start=1):
        (dossier / f"{i:02d}{code_livre}{nom}.SFM").write_text(contenu, encoding="utf-8")
        (dossier / f"{i:02d}{code_livre}{nom}.SFM.BAK").write_text("\\id XXX\n\\c 1\n\\v 1 vieux", encoding="utf-8")
    for fichier, contenu in (extras or {}).items():
        (dossier / fichier).write_text(contenu, encoding="utf-8")
    return dossier


@pytest.fixture
def racine_pt(tmp_path):
    racine = tmp_path / "My Paratext 9 Projects"
    _projet_pt(racine, "sbanb", "sba", "Ngambay", {
        "RUT": "\\id RUT\n\\c 1\n\\p\n\\v 1 Kó ndɔ.\n\\v 2 Ala ɓa.\n",
        "JHN": "\\id JHN\n\\c 3\n\\v 16 Ala ndigi dəwje.\n",
        "XXA": "\\id XXA\n\\c 1\n\\v 1\n",
    }, extras={"Lexicon.xml": LEXICON, "TermRenderings.xml": RENDUS, "ProjectBiblicalTerms.xml": TERMES})
    _projet_pt(racine, "FRB", "fr", "Français", {
        "RUT": "\\id RUT\n\\c 1\n\\v 1 Un arbre, un jour.\n\\v 2 Dieu vient.\n",
    }, versif="1")
    (racine / "pas_un_projet").mkdir()
    return racine


def _empreinte(dossier):
    fichiers = [f for f in sorted(os.listdir(dossier)) if os.path.isfile(os.path.join(dossier, f))]
    return {f: hashlib.md5(open(os.path.join(dossier, f), "rb").read()).hexdigest() for f in fichiers}


def test_liste_des_projets(racine_pt):
    projets = {p.nom: p for p in paratext.lister_projets(str(racine_pt))}
    assert set(projets) == {"sbanb", "FRB"}
    sba = projets["sbanb"]
    assert (sba.code, sba.langue, sba.versification) == ("sba", "Ngambay", "4")
    assert sba.livres == ["RUT", "JHN", "XXA"], "ordre canonique, fichiers .BAK ignorés"


def test_corpus_parallele(projet, racine_pt):
    projets = {p.nom: p for p in paratext.lister_projets(str(racine_pt))}
    avant = _empreinte(projets["sbanb"].dossier)
    r = paratext.importer_livres(projet, projets["sbanb"], projets["sbanb"].livres, "vernaculaire")
    assert (r.livres, r.versets) == (2, 3)
    assert any("sans texte" in a and "XXA" in a for a in r.avertissements)
    r = paratext.importer_livres(projet, projets["FRB"], ["RUT"], "analyse")
    assert r.completes == 2
    assert any("Versification" in a for a in r.avertissements)
    assert projet.conn.execute("SELECT vernaculaire, analyse, source FROM phrases WHERE ref='RUT 1:1'").fetchone() \
        == ("Kó ndɔ.", "Un arbre, un jour.", "Paratext FRB")
    assert _empreinte(projets["sbanb"].dossier) == avant, "le projet Paratext ne doit jamais être modifié"


def test_glossaire(projet, racine_pt):
    conn = projet.conn
    existant = lexique.enregistrer_entree(conn, Entree(forme="ala", sens=[Sens(glose="dieu")]))
    sba = next(p for p in paratext.lister_projets(str(racine_pt)) if p.nom == "sbanb")
    r = paratext.importer_glossaire(projet, sba)
    assert (r.entrees, r.sens) == (2, 2), "« ala / dieu » existe déjà : rien n'est dupliqué"
    bo = lexique.lire_entree(conn, lexique.chercher_par_forme(conn, "bɔ")[0])
    assert [s.glose for s in bo.sens] == ["père"], "seulement les gloses dans la langue d'analyse du projet"
    je = lexique.lire_entree(conn, lexique.chercher_par_forme(conn, "-je")[0])
    assert je.type_morph == "suffix"
    assert len(lexique.lire_entree(conn, existant).sens) == 1
    assert paratext.importer_glossaire(projet, sba).sens == 0, "réimporter n'ajoute rien"


def test_termes_bibliques(projet, racine_pt):
    conn = projet.conn
    sba = next(p for p in paratext.lister_projets(str(racine_pt)) if p.nom == "sbanb")
    r = paratext.importer_termes(projet, sba)
    assert r.termes == 4, "Betilehem, Edom, Edɔm, la locution ; pas le rendu deviné ni le vide"
    bet = lexique.lire_entree(conn, lexique.chercher_par_forme(conn, "Betilehem")[0])
    assert bet.sens[0].glose == "Bethlehem" and lexique.nom_categorie(conn, bet.sens[0].categorie_id) == "nom propre"
    assert "Βηθλέεμ" in bet.notes
    assert not lexique.chercher_par_forme(conn, "malaika")
    loc = lexique.lire_entree(conn, lexique.chercher_par_forme(conn, "Gin-ŋgar lə Ala")[0])
    assert loc.type_morph == "phrase" and loc.sens[0].glose == "kingdom of God"
    assert paratext.importer_termes(projet, sba).termes == 0


@pytest.mark.skipif(not os.path.isdir(paratext.DOSSIERS_PARATEXT[0]), reason="Paratext absent")
def test_vrais_projets_paratext_intacts(projet):
    projets = [p for p in paratext.lister_projets() if p.livres]
    if not projets:
        pytest.skip("aucun projet Paratext")
    p = min(projets, key=lambda x: len(x.livres))
    avant = _empreinte(p.dossier)
    paratext.importer_livres(projet, p, p.livres[:2], "vernaculaire")
    assert _empreinte(p.dossier) == avant


# -- Bible complète : dossier ou archive, USFM ou USX ----------------------------------------------

USX3 = """<?xml version="1.0" encoding="utf-8"?>
<usx version="3.0"><book code="LUK" style="id">Luc</book>
<para style="h">Luc</para>
<chapter number="2" style="c" sid="LUK 2"/>
<para style="s1">Naissance de Jésus</para>
<para style="p"><verse number="1" style="v" sid="LUK 2:1"/>En ce temps-là parut un édit<note caller="+" style="f"><char style="ft">note</char></note> de César.<verse eid="LUK 2:1"/>
<verse number="2" style="v" sid="LUK 2:2"/>Ce premier <char style="w">recensement</char> eut lieu.<verse eid="LUK 2:2"/></para>
<chapter eid="LUK 2"/></usx>"""

USX2 = """<usx version="2.0"><book code="RUT" style="id"/><chapter number="1" style="c"/>
<para style="p"><verse number="1" style="v"/>Du temps des juges.<verse number="2-3" style="v"/>Le nom.</para></usx>"""


def test_usx():
    from lexicographe import usfm
    versets, code = usfm.analyser_usx(USX3)
    assert code == "LUK"
    assert versets == {"LUK 2:1": "En ce temps-là parut un édit de César.", "LUK 2:2": "Ce premier recensement eut lieu."}
    versets, _ = usfm.analyser_usx(USX2)
    assert versets == {"RUT 1:1": "Du temps des juges.", "RUT 1:2": "Le nom."}


def test_marqueurs_de_mots_et_apostrophes():
    from lexicographe import usfm
    versets, _ = usfm.analyser_usfm('\\id JOB\n\\c 1\n\\p\n\\v 1 \\w Il|strong="H1"\\w* était dans le pays d’\\w Uts|strong="H5780"\\w* \\+w qu’\\+w*\\w il\\w*.\n')
    assert versets == {"JOB 1:1": "Il était dans le pays d’Uts qu’il."}


def test_bible_complete_en_archive(projet, tmp_path):
    import zipfile
    from lexicographe import usfm
    archive = tmp_path / "pdv.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("release/USX_1/LUK.usx", USX3)
        z.writestr("release/USX_1/RUT.usx", USX2)
        z.writestr("autres/01GEN.SFM", "\\id GEN\n\\c 1\n\\v 1 Au commencement.\n")
        z.writestr("autres/01GEN.SFM.BAK", "\\id GEN\n\\c 1\n\\v 1 vieux\n")
        z.writestr("metadata.xml", "<x/>")
    livres = usfm.lire_bible(str(archive))
    assert set(livres) == {"LUK", "RUT", "GEN"} and livres["GEN"] == {"GEN 1:1": "Au commencement."}
    dossier = tmp_path / "dossier"
    (dossier / "sous").mkdir(parents=True)
    (dossier / "sous" / "LUK.usx").write_text(USX3, encoding="utf-8")
    assert set(usfm.lire_bible(str(dossier))) == {"LUK"}

import hashlib
import os

import pytest

from lexicographe import flex_import, interlineaire as il, lexique, textes
from lexicographe.projet import Projet

FWDATA = """<?xml version="1.0" encoding="utf-8"?>
<languageproject version="7000072">
<rt class="LangProject" guid="00000000-0000-0000-0000-000000000001">
<CurVernWss><Uni>sba sba-fonipa</Uni></CurVernWss>
<CurAnalysisWss><Uni>fr en</Uni></CurAnalysisWss>
</rt>
<rt class="MoMorphType" guid="mt-stem"><Name><AUni ws="en">stem</AUni></Name></rt>
<rt class="MoMorphType" guid="mt-suffix"><Name><AUni ws="en">suffix</AUni></Name></rt>
<rt class="PartOfSpeech" guid="pos-n"><Name><AUni ws="fr">nom</AUni></Name><Abbreviation><AUni ws="fr">n</AUni></Abbreviation></rt>
<rt class="PartOfSpeech" guid="pos-nc" ownerguid="pos-n"><Name><AUni ws="fr">nom comptable</AUni></Name></rt>
<rt class="CmSemanticDomain" guid="dom-1"><Abbreviation><AUni ws="en">1</AUni></Abbreviation><Name><AUni ws="fr">Univers</AUni></Name></rt>
<rt class="CmSemanticDomain" guid="dom-11" ownerguid="dom-1"><Abbreviation><AUni ws="en">1.1</AUni></Abbreviation><Name><AUni ws="fr">Ciel</AUni></Name></rt>

<rt class="LexEntry" guid="e-ko">
<DateCreated val="2025-01-02 10:00:00.000" />
<LexemeForm><objsur guid="a-ko" t="o" /></LexemeForm>
<Pronunciations><objsur guid="p-ko" t="o" /></Pronunciations>
<Senses><objsur guid="s-ko" t="o" /></Senses>
<Comment><AStr ws="fr"><Run ws="fr">mot courant</Run></AStr></Comment>
</rt>
<rt class="MoStemAllomorph" guid="a-ko" ownerguid="e-ko"><Form><AUni ws="sba">kó</AUni></Form><MorphType><objsur guid="mt-stem" t="r" /></MorphType></rt>
<rt class="LexPronunciation" guid="p-ko" ownerguid="e-ko"><Form><AUni ws="sba-fonipa">kó˥</AUni></Form></rt>
<rt class="MoStemMsa" guid="msa-ko" ownerguid="e-ko"><PartOfSpeech><objsur guid="pos-nc" t="r" /></PartOfSpeech></rt>
<rt class="LexSense" guid="s-ko" ownerguid="e-ko">
<Gloss><AUni ws="en">tree</AUni><AUni ws="fr">arbre</AUni></Gloss>
<Definition><AStr ws="fr"><Run ws="fr">grande plante</Run></AStr></Definition>
<MorphoSyntaxAnalysis><objsur guid="msa-ko" t="r" /></MorphoSyntaxAnalysis>
<SemanticDomains><objsur guid="dom-11" t="r" /></SemanticDomains>
<Examples><objsur guid="x-ko" t="o" /></Examples>
<UsageNote><AStr ws="fr"><Run ws="fr">surtout au sud</Run></AStr></UsageNote>
<Senses><objsur guid="s-ko-2" t="o" /></Senses>
</rt>
<rt class="LexSense" guid="s-ko-2" ownerguid="s-ko"><Gloss><AUni ws="fr">bois</AUni></Gloss></rt>
<rt class="LexExampleSentence" guid="x-ko" ownerguid="s-ko">
<Example><AStr ws="sba"><Run ws="sba">kó ndɔ</Run></AStr></Example>
<Reference><Uni>RUT 1:1</Uni></Reference>
<Translations><objsur guid="t-ko" t="o" /></Translations>
</rt>
<rt class="CmTranslation" guid="t-ko" ownerguid="x-ko"><Translation><AStr ws="fr"><Run ws="fr">un arbre</Run></AStr></Translation></rt>

<rt class="LexEntry" guid="e-je">
<LexemeForm><objsur guid="a-je" t="o" /></LexemeForm>
<Senses><objsur guid="s-je" t="o" /></Senses>
</rt>
<rt class="MoAffixAllomorph" guid="a-je" ownerguid="e-je"><Form><AUni ws="sba">je</AUni></Form><MorphType><objsur guid="mt-suffix" t="r" /></MorphType></rt>
<rt class="LexSense" guid="s-je" ownerguid="e-je"><Gloss><AUni ws="fr">PL</AUni></Gloss></rt>

<rt class="LexEntry" guid="e-koo">
<LexemeForm><objsur guid="a-koo" t="o" /></LexemeForm>
<EntryRefs><objsur guid="r-koo" t="o" /></EntryRefs>
</rt>
<rt class="MoStemAllomorph" guid="a-koo" ownerguid="e-koo"><Form><AUni ws="sba">kóo</AUni></Form></rt>
<rt class="LexEntryType" guid="vt-dial"><Name><AUni ws="en">Dialectal Variant</AUni></Name></rt>
<rt class="LexEntryRef" guid="r-koo" ownerguid="e-koo">
<ComponentLexemes><objsur guid="e-ko" t="r" /></ComponentLexemes>
<RefType val="0" /><VariantEntryTypes><objsur guid="vt-dial" t="r" /></VariantEntryTypes>
</rt>

<rt class="LexEntry" guid="e-koje">
<LexemeForm><objsur guid="a-koje" t="o" /></LexemeForm>
<Senses><objsur guid="s-koje" t="o" /></Senses>
</rt>
<rt class="MoStemAllomorph" guid="a-koje" ownerguid="e-koje"><Form><AUni ws="sba">kóje</AUni></Form></rt>
<rt class="LexSense" guid="s-koje" ownerguid="e-koje"><Gloss><AUni ws="fr">forêt</AUni></Gloss></rt>
<rt class="LexEntryType" guid="ct-comp"><Name><AUni ws="en">Compound</AUni></Name></rt>
<rt class="LexEntryRef" guid="r-koje" ownerguid="e-koje">
<ComponentLexemes><objsur guid="e-ko" t="r" /><objsur guid="s-je" t="r" /></ComponentLexemes>
<RefType val="1" /><ComplexEntryTypes><objsur guid="ct-comp" t="r" /></ComplexEntryTypes>
</rt>

<rt class="LexRefType" guid="lrt-syn"><Name><AUni ws="en">Synonyms</AUni></Name><MappingType val="0" /></rt>
<rt class="LexReference" guid="lr-1" ownerguid="lrt-syn"><Targets><objsur guid="s-ko" t="r" /><objsur guid="e-koje" t="r" /></Targets></rt>

<rt class="Text" guid="txt-1"><Name><AUni ws="fr">Le conte</AUni></Name><Contents><objsur guid="st-1" t="o" /></Contents></rt>
<rt class="StText" guid="st-1" ownerguid="txt-1"><Paragraphs><objsur guid="par-1" t="o" /></Paragraphs></rt>
<rt class="StTxtPara" guid="par-1" ownerguid="st-1">
<Contents><Str><Run ws="sba">Kóje kó. Ko</Run><Run ws="sba">́ !</Run></Str></Contents>
<Segments><objsur guid="seg-1" t="o" /><objsur guid="seg-2" t="o" /></Segments>
</rt>
<rt class="Segment" guid="seg-1" ownerguid="par-1">
<BeginOffset val="0" />
<FreeTranslation><AStr ws="fr"><Run ws="fr">Des arbres, un arbre.</Run></AStr></FreeTranslation>
<Analyses><objsur guid="g-koje" t="r" /><objsur guid="an-ko" t="r" /><objsur guid="punct" t="r" /></Analyses>
</rt>
<rt class="Segment" guid="seg-2" ownerguid="par-1"><BeginOffset val="9" /><Analyses><objsur guid="an-ko" t="r" /></Analyses></rt>
<rt class="PunctuationForm" guid="punct"><Form><Str><Run ws="sba">.</Run></Str></Form></rt>
<rt class="WfiWordform" guid="wf-koje"><Form><AUni ws="sba">kóje</AUni></Form></rt>
<rt class="WfiAnalysis" guid="an-koje" ownerguid="wf-koje"><MorphBundles><objsur guid="b1" t="o" /><objsur guid="b2" t="o" /></MorphBundles></rt>
<rt class="WfiMorphBundle" guid="b1" ownerguid="an-koje"><Form><AStr ws="sba"><Run ws="sba">kó</Run></AStr></Form><Sense><objsur guid="s-ko" t="r" /></Sense></rt>
<rt class="WfiMorphBundle" guid="b2" ownerguid="an-koje"><Morph><objsur guid="a-je" t="r" /></Morph><Sense><objsur guid="s-je" t="r" /></Sense></rt>
<rt class="WfiGloss" guid="g-koje" ownerguid="an-koje"><Form><AUni ws="fr">arbres</AUni></Form></rt>
<rt class="WfiWordform" guid="wf-ko"><Form><AUni ws="sba">kó</AUni></Form></rt>
<rt class="WfiAnalysis" guid="an-ko" ownerguid="wf-ko"><MorphBundles><objsur guid="b3" t="o" /></MorphBundles></rt>
<rt class="WfiMorphBundle" guid="b3" ownerguid="an-ko"><Form><AStr ws="sba"><Run ws="sba">kó</Run></AStr></Form><Sense><objsur guid="s-ko" t="r" /></Sense></rt>
</languageproject>"""


@pytest.fixture
def fwdata(tmp_path):
    dossier = tmp_path / "Projects" / "demo"
    dossier.mkdir(parents=True)
    chemin = dossier / "demo.fwdata"
    chemin.write_text(FWDATA, encoding="utf-8")
    return str(chemin)


def _empreinte(chemin):
    with open(chemin, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def test_detection_des_projets(fwdata, tmp_path):
    (p,) = flex_import.lister_projets_flex(str(tmp_path / "Projects"))
    assert p.nom == "demo" and p.chemin == fwdata and not p.ouvert_dans_flex
    assert flex_import.langues(fwdata) == ("sba", "fr")


def test_import_lexique(projet, fwdata):
    avant = _empreinte(fwdata)
    r = flex_import.importer(projet, fwdata)
    assert _empreinte(fwdata) == avant, "le fichier FLEx ne doit jamais être modifié"
    assert (r.creees, r.avertissements) == (4, [])
    conn = projet.conn
    ko = lexique.lire_entree(conn, lexique.chercher_par_forme(conn, "kó")[0])
    assert (ko.guid, ko.type_morph, ko.prononciation, ko.statut) == ("e-ko", "stem", "kó˥", "à vérifier")
    assert ko.date_creation.startswith("2025-01-02")
    s1, s2 = ko.sens
    assert (s1.glose, s1.definition) == ("arbre", "grande plante"), "glose prise dans la langue d'analyse du projet"
    assert lexique.nom_categorie(conn, s1.categorie_id) == "nom comptable"
    arbre = {c[1]: c[3] for c in lexique.categories_arbre(conn)}
    assert arbre["nom comptable"] == arbre["nom"] + 1, "hiérarchie des catégories conservée"
    assert s1.domaines == ["dom-11"]
    assert (s1.exemples[0].vernaculaire, s1.exemples[0].traduction, s1.exemples[0].reference) == \
        ("kó ndɔ", "un arbre", "RUT 1:1")
    assert s2.glose == "bois" and "sous-sens" in ko.notes
    assert "Note : mot courant" in ko.notes and "Usage : surtout au sud" in ko.notes
    assert [(v.forme, v.type) for v in ko.variantes] == [("kóo", "variante dialectale")]

    je = lexique.lire_entree(conn, lexique.chercher_par_forme(conn, "je")[0])
    assert je.type_morph == "suffix"
    koje = lexique.lire_entree(conn, lexique.chercher_par_forme(conn, "kóje")[0])
    assert koje.composants == [ko.id, je.id] and koje.type_forme_complexe == "composé"
    koo = lexique.chercher_par_forme(conn, "kóo")[0]
    assert ("variante de", "kó") in [(t, f) for _, t, _, f in lexique.relations(conn, koo)]
    assert ("synonyme", "kóje") in [(t, f) for _, t, _, f in lexique.relations(conn, ko.id)]


def test_import_textes_et_analyses(projet, fwdata):
    projet.definir_reglages({"caracteres_mot_vern": "-"})
    r = flex_import.importer(projet, fwdata)
    assert (r.textes, r.phrases, r.analyses) == (1, 2, 2)
    (t,) = textes.lister(projet.conn)
    assert t.titre == "Le conte" and "(FLEx txt-1)" in t.notes
    lignes = textes.phrases(projet.conn, t.code)
    assert [(v, a) for _, v, a in lignes] == [("Kóje kó.", "Des arbres, un arbre."), ("Kó !", None)], \
        "découpe aux positions FLEx, puis normalisation Unicode"
    mots = il.phrase(projet, lignes[0][0], lignes[0][1])
    assert [(m.statut, m.analyse.segmentation) for m in mots] == [(il.VALIDEE, "kó-je"), (il.VALIDEE, "kó")]
    assert mots[0].analyse.glose_mot == "arbres" and mots[0].analyse.gloses == "arbre-PL"

    # réimporter : mêmes entrées, même texte, pas de doublons
    r2 = flex_import.importer(projet, fwdata)
    assert (r2.creees, r2.mises_a_jour, r2.textes) == (0, 4, 1)
    assert len(textes.lister(projet.conn)) == 1
    assert projet.conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0] == 2


def test_import_sans_textes(projet, fwdata):
    r = flex_import.importer(projet, fwdata, statut="validé", avec_textes=False)
    assert r.textes == 0 and projet.conn.execute("SELECT COUNT(*) FROM phrases").fetchone()[0] == 0
    assert {e.statut for e in (lexique.lire_entree(projet.conn, l.id) for l in lexique.lister_entrees(projet.conn))} \
        == {"validé"}


def test_projet_ouvert_dans_flex_signale(projet, fwdata):
    open(fwdata + ".lock", "w").close()
    r = flex_import.importer(projet, fwdata)
    assert any("FLEx semble ouvert" in a for a in r.avertissements)


@pytest.mark.skipif(not os.path.isdir(flex_import.DOSSIER_FLEX_DEFAUT), reason="FLEx n'est pas installé")
def test_vrais_projets_flex_restent_intacts(tmp_path):
    projets = flex_import.lister_projets_flex()
    if not projets:
        pytest.skip("aucun projet FLEx")
    pf = min(projets, key=lambda p: p.taille)
    avant = _empreinte(pf.chemin)
    vern, analyse = flex_import.langues(pf.chemin)
    p = Projet.creer(str(tmp_path / "x.lexique"), nom=pf.nom, langue_vern_code=vern, langue_analyse_code=analyse)
    r = flex_import.importer(p, pf.chemin)
    assert r.creees > 0 and _empreinte(pf.chemin) == avant
    p.fermer()

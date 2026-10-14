import pytest

from lexicographe import syllabaire as sy
from lexicographe.syllabaire import Decoupeur, Syllabaire


def test_decoupage_multigraphes_et_tons():
    d = Decoupeur("a b ɓ d e ə g k m n ŋ ŋg nj o ɔ a̰")
    assert d.decouper("Ŋgonje") == ["ŋg", "o", "nj", "e"], "correspondance la plus longue"
    assert d.decouper("ká") == ["k", "a", "́"], "le ton est un graphème à part"
    assert d.decouper("ka̰") == ["k", "a̰"], "graphème déclaré avec sa marque"
    assert d.decouper("kx") == ["k", "x"] and d.nature("x") == "non déclaré"
    assert d.decouper("ká-ma2") == ["k", "a", "́", "m", "a"], "tiret et chiffre ne s'enseignent pas"
    assert d.nature("́") == "ton" and d.nature("ŋg") == "lettre"
    sans_tons = Decoupeur("a k", marques_separees=False)
    assert sans_tons.decouper("ká") == ["k", "á"]
    assert sy.affichage("́") == "◌́"


def _corpus(projet, phrases):
    with projet.conn:
        projet.conn.executemany("INSERT INTO phrases (ref, vernaculaire, source) VALUES (?, ?, 'test')",
                                [(f"T001 {i}", p) for i, p in enumerate(phrases, start=1)])


@pytest.fixture
def corpus(projet):
    projet.definir_reglages({"alphabet_vern": "a b d i k m n ŋg o", "caracteres_mot_vern": "-"})
    _corpus(projet, ["ma ma ma ana", "mama na", "ka ma", "ŋgoma Abakar", "dikŋgo bo", "Abakar ma"])
    return projet


def test_inventaire_et_noms_propres(corpus):
    s = Syllabaire(corpus)
    assert "abakar" in s.noms_propres
    inv = {g.grapheme: g for g in s.inventaire()}
    assert "r" not in inv, "les noms propres sont écartés par défaut"
    assert inv["a"].occurrences > inv["m"].occurrences > inv["k"].occurrences
    assert inv["ŋg"].mots == 2 and inv["ŋg"].nature == "lettre"
    avec_noms = {g.grapheme: g for g in Syllabaire(corpus, exclure_noms_propres=False).inventaire()}
    assert avec_noms["r"].nature == "non déclaré", "caractère absent de l'alphabet signalé"


def test_ordre_propose_et_justification(corpus):
    s = Syllabaire(corpus)
    ordre = s.ordre_propose()
    assert [g for g, _ in ordre][:2] == ["a", "m"], "le plus fréquent, puis celui qui débloque le plus de mots"
    assert dict(ordre)["m"] == 2, "« ma » et « mama » deviennent lisibles"
    assert sorted(g for g, _ in ordre) == sorted(g.grapheme for g in s.inventaire()), "chaque graphème une fois"


def test_lecons(corpus):
    s = Syllabaire(corpus)
    lecons = s.lecons(["a", "m", "n", "k"])
    assert [l.debloques for l in lecons] == [0, 2, 2, 1]
    assert [m for m, _ in lecons[1].mots] == ["ma", "mama"], "les plus fréquents d'abord"
    assert [r for r, _ in lecons[2].phrases] == ["T001 1", "T001 2"]
    assert lecons[3].phrases == [("T001 3", "ka ma")]
    assert lecons[-1].lisibles == 5 and 0 < lecons[-1].occurrences_lisibles < 1


def test_ordre_enregistre_et_exports(corpus, tmp_path):
    sy.enregistrer_ordre(corpus, ["a", "m", "ŋg"])
    assert sy.ordre_enregistre(corpus) == ["a", "m", "ŋg"]
    from lexicographe import lexique
    lexique.enregistrer_entree(corpus.conn, lexique.Entree(forme="ma", sens=[lexique.Sens(glose="moi")]))
    lecons = Syllabaire(corpus).lecons(sy.ordre_enregistre(corpus))
    sy.exporter_texte(corpus, lecons, str(tmp_path / "s.txt"))
    texte = open(tmp_path / "s.txt", encoding="utf-8").read()
    assert "Leçon 2 : m" in texte and "ma (moi)" in texte
    sy.exporter_csv(corpus, lecons, str(tmp_path / "s.csv"))
    assert "2,m,ma,5,moi" in open(tmp_path / "s.csv", encoding="utf-8-sig").read()


def test_suites_frequentes(corpus):
    suites = dict(Syllabaire(corpus).suites_frequentes())
    assert suites["ma"] > 0 and "ŋg" in suites, "candidats multigraphes, à examiner par le linguiste"

import os

import pytest

from lexicographe import clavier, lexique
from lexicographe.lexique import Entree, Sens

MOTS = ["ɓá", "ɗèē", "kə̀m", "sɨ̄", "ngɔ̄", "màn̄", "à̰y"] * 10 + ["bɛ̄", "naî"]


@pytest.fixture
def projet_tons(projet):
    for mot in MOTS:
        lexique.enregistrer_entree(projet.conn, Entree(forme=mot, sens=[Sens(glose="x")]))
    projet.definir_reglages({"alphabet_vern": "a b ɓ d ɗ e ə i ɨ ŋ o ɔ", "langue_vern_nom": "ngambay"})
    return projet


def test_inventaire(projet_tons):
    inv = clavier.inventaire(projet_tons.conn, projet_tons.reglage("alphabet_vern"))
    assert [(l.caractere, l.sequence, l.majuscule) for l in inv.lettres] == [
        ("ɓ", "b;", "Ɓ"), ("ɗ", "d;", "Ɗ"), ("ə", "e;", "Ə"), ("ɨ", "i;", "Ɨ"), ("ŋ", "n;", "Ŋ"), ("ɔ", "o;", "Ɔ")]
    assert "ɛ" not in [l.caractere for l in inv.lettres], "1 occurrence : sous le seuil, non déclaré"
    assert {s.code for s in inv.signes} == {"h", "m", "b", "n"}, "le circonflexe d'un seul mot est écarté"


def test_deux_lettres_sur_la_meme_base(projet_tons):
    projet_tons.definir_reglages({"alphabet_vern": "a b e ə ɛ"})
    inv = clavier.inventaire(projet_tons.conn, projet_tons.reglage("alphabet_vern"))
    assert [(l.caractere, l.sequence) for l in inv.lettres if l.base == "e"] == [("ə", "e;"), ("ɛ", "e;;")]
    kmn = clavier.construire_kmn(inv, "Ngambay", "gerro_ngambay")
    assert "U+0065 + ';' > U+0259" in kmn and "U+0259 + ';' > U+025B" in kmn
    assert "U+025B + ';' > U+0065 ';'" in kmn, "un ; de plus rend « e; »"


def test_saltillo(projet):
    """Coup de glotte écrit comme une lettre (kenga) : « '; » ; une seule règle, la base n'a pas de majuscule."""
    for _ in range(10):
        lexique.enregistrer_entree(projet.conn, Entree(forme="kaꞌa", sens=[Sens(glose="x")]))
    inv = clavier.inventaire(projet.conn)
    assert [(l.caractere, l.sequence) for l in inv.lettres] == [("ꞌ", "';")] and inv.sans_base == []
    kmn = clavier.construire_kmn(inv, "Kenga", "gerro_kenga")
    assert kmn.count("U+0027 + ';' >") == 1


def test_source_keyman(projet_tons):
    inv = clavier.inventaire(projet_tons.conn, projet_tons.reglage("alphabet_vern"))
    kmn = clavier.construire_kmn(inv, "Ngambay", "gerro_ngambay")
    assert "store(&MNEMONICLAYOUT) '1'" in kmn, "fonctionne en AZERTY comme en QWERTY"
    assert "U+0062 + ';' > U+0253" in kmn and "U+0042 + ';' > U+0181" in kmn
    assert "'=' dk(signe) + 'h' > U+0301" in kmn and "'=' dk(signe) + '=' > '='" in kmn
    assert clavier.identifiant("Ngambay") == "gerro_ngambay"
    assert clavier.identifiant("Gor (Bodo)") == "gerro_gor_bodo"
    assert clavier.identifiant("2 langues") == "gerro_k_2_langues"


def test_projet_sans_lettre_speciale(projet):
    lexique.enregistrer_entree(projet.conn, Entree(forme="maison", sens=[Sens(glose="x")]))
    with pytest.raises(ValueError):
        clavier.generer(projet, "inutilise")


@pytest.mark.skipif(not clavier.compilateur(), reason="Keyman Developer n'est pas installé")
def test_compilation_keyman(projet_tons, tmp_path):
    r = clavier.generer(projet_tons, str(tmp_path))
    assert r.paquet.endswith("gerro_ngambay.kmp") and os.path.isfile(r.paquet), r.message
    assert "e;" in open(r.aide, encoding="utf-8").read()

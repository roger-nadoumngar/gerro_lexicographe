from lexicographe import controles, lexique
from lexicographe.lexique import Entree, Exemple, Sens


def test_corriger_texte():
    assert controles.corriger_texte("à̰ӯ") == "à̰ȳ", "ӯ cyrillique → ȳ latin, signes gardés"
    assert controles.corriger_texte("dу ndɔ̀ɔ̄") == "dy ndɔ̀ɔ̄"
    assert controles.corriger_texte("kοm") == "kom", "omicron grec"
    assert controles.corriger_texte("уст") == "уст", "mot sans lettre latine : intact"
    assert controles.corriger_texte("ndɔ̀ɔ̄") == "ndɔ̀ɔ̄"


def test_retirer_le_macron(projet):
    conn = projet.conn
    eid = lexique.enregistrer_entree(conn, Entree(forme="àl̄", prononciation="àl̄", sens=[Sens(
        glose="monter", exemples=[Exemple(vernaculaire="Ā kàw̄ ndɔ̀ɔ̄.", traduction="Tu vas au champ.")])]))
    with conn:
        conn.execute("INSERT INTO phrases (ref, vernaculaire) VALUES ('GEN 1:1', 'kāw')")
    assert controles.sans_signe("à̰ā̰ ī ō m̄") == "à̰a̰ i o m", "autres signes (grave, tilde souscrit) gardés"
    occ = controles.retirer_signe(conn)
    assert sorted(o.apres for o in occ) == ["A kàw ndɔ̀ɔ.", "àl"]
    controles.corriger(conn, occ)
    e = lexique.lire_entree(conn, eid)
    assert (e.forme, e.prononciation) == ("àl", "àl̄"), "la prononciation n'est pas touchée"
    assert conn.execute("SELECT vernaculaire FROM phrases").fetchone()[0] == "kāw", "le corpus n'est pas touché"
    assert controles.retirer_signe(conn) == []


def test_trouver_et_corriger(projet):
    conn = projet.conn
    eid = lexique.enregistrer_entree(conn, Entree(forme="à̰ӯ", sens=[Sens(
        glose="ombre", exemples=[Exemple(vernaculaire="Kə́y à̰ӯ.", traduction="L'ombre.")])]))
    lexique.enregistrer_entree(conn, Entree(forme="ndɔ̀ɔ̄", sens=[Sens(glose="champ")]))
    trouves = controles.trouver(conn)
    assert sorted((o.table, o.colonne) for o in trouves) == [("entrees", "forme"), ("exemples", "vernaculaire")]
    assert controles.corriger(conn, trouves) == 2
    e = lexique.lire_entree(conn, eid)
    assert e.forme == "à̰ȳ" and e.sens[0].exemples[0].vernaculaire == "Kə́y à̰ȳ."
    assert controles.trouver(conn) == []

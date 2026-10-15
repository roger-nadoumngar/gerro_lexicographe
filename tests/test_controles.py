from lexicographe import controles, lexique
from lexicographe.lexique import Entree, Exemple, Sens


def test_corriger_texte():
    assert controles.corriger_texte("à̰ӯ") == "à̰ȳ", "ӯ cyrillique → ȳ latin, signes gardés"
    assert controles.corriger_texte("dу ndɔ̀ɔ̄") == "dy ndɔ̀ɔ̄"
    assert controles.corriger_texte("kοm") == "kom", "omicron grec"
    assert controles.corriger_texte("уст") == "уст", "mot sans lettre latine : intact"
    assert controles.corriger_texte("ndɔ̀ɔ̄") == "ndɔ̀ɔ̄"


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

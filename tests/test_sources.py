from lexicographe import lexique, sources
from lexicographe.lexique import Entree, Exemple, Sens

SOURCE = "dictionnaire d'exemple"


def _e(conn, forme, notes="", exemples=(), **kw):
    return lexique.enregistrer_entree(conn, Entree(forme=forme, notes=notes, sens=[Sens(
        glose="x", exemples=[Exemple(v, "t", r) for v, r in exemples])], **kw))


def test_retirer_une_source(projet):
    conn = projet.conn
    seul = _e(conn, "bàb", f"Source : {SOURCE}", [("bàb lé.", SOURCE)])
    paratext = _e(conn, "ala", f"Source : {SOURCE}\nGlossaire Paratext (sbanb)", [("Ala ɗèe.", SOURCE)])
    photo = _e(conn, "bísi", f"Source : {SOURCE}")
    lexique.lier_media(conn, photo, "chien.jpg", "image")
    mien = _e(conn, "kédé", "", [("Kédé ɓa.", SOURCE), ("Kédé lé.", "")])   # entrée sans marque : gardée
    corpus = _e(conn, "ndà", "", [("Ndà ɓa.", "RUT 1:1")])

    assert sources.lister(conn) == {SOURCE: (3, 3)}, "les références de versets ne sont pas des sources"
    p = sources.plan(conn, SOURCE)
    assert p.entrees_supprimees == [seul]
    assert sorted(p.entrees_gardees) == sorted([paratext, photo])
    assert len(p.exemples) == 3
    sources.appliquer(conn, p)

    assert lexique.lire_entree(conn, seul) is None
    e = lexique.lire_entree(conn, paratext)
    assert e.notes == "Glossaire Paratext (sbanb)" and e.sens[0].exemples == []
    assert lexique.lire_entree(conn, photo).notes == "" and lexique.medias_de(conn, photo)
    assert [x.vernaculaire for x in lexique.lire_entree(conn, mien).sens[0].exemples] == ["Kédé lé."]
    assert lexique.lire_entree(conn, corpus).sens[0].exemples[0].reference == "RUT 1:1"
    assert sources.lister(conn) == {}

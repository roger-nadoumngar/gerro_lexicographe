from lexicographe import doublons, lexique
from lexicographe.lexique import Entree, Exemple, Sens, Variante


def _e(conn, forme, *gloses, **kw):
    return lexique.enregistrer_entree(conn, Entree(forme=forme, sens=[
        g if isinstance(g, Sens) else Sens(glose=g) for g in gloses], **kw))


def test_reperage(projet):
    conn = projet.conn
    a = _e(conn, "kédé", "avant")
    b = _e(conn, "Kédé", "avant, devant")
    _e(conn, "tó", "être")
    _e(conn, "tó", "brûler")            # homographe : aucune glose commune
    _e(conn, "-je", "PL", type_morph="suffix")
    _e(conn, "je", "PL")                # autre type : pas un doublon du suffixe
    groupes = doublons.candidats(conn)
    assert [(g.forme, sorted(g.entrees)) for g in groupes] == [("kédé", sorted([a, b]))]
    assert groupes[0].gloses_communes == ["avant"]


def test_fusion_sans_perte(projet):
    conn = projet.conn
    cat = lexique.ajouter_categorie(conn, "Nom", "n")
    garder = _e(conn, "bísī", Sens(glose="chien", exemples=[Exemple("Bísī lé àw̄.", "Le chien part.")]),
                statut="à vérifier", notes="Source : Keegan")
    retirer = _e(conn, "Bísī", Sens(glose="chien domestique", categorie_id=cat, definition="animal",
                                     exemples=[Exemple("Bísī lé àw̄.", "doublon"), Exemple("Bísī ndɔ̄.", "Le chien mord.")]),
                 Sens(glose="ami fidèle"), statut="validé", prononciation="bísī", notes="Glossaire Paratext",
                 variantes=[Variante("bísɨ̄", "variante libre")])
    autre = _e(conn, "kàgɨ̀", "panthère")
    lexique.ajouter_relation(conn, autre, retirer, "voir aussi")
    lexique.ajouter_relation(conn, retirer, garder, "synonyme")      # deviendrait une relation à soi-même
    lexique.lier_media(conn, retirer, "chien.jpg", "image")
    compose = _e(conn, "bísī-kɔ̄r", "chien enragé", composants=[retirer])

    (groupe,) = doublons.candidats(conn)
    assert doublons.plus_complete(conn, groupe.entrees) == retirer, "le plus d'exemples"
    doublons.fusionner(conn, garder, retirer)

    assert lexique.lire_entree(conn, retirer) is None
    e = lexique.lire_entree(conn, garder)
    assert [s.glose for s in e.sens] == ["chien domestique", "ami fidèle"], "glose plus complète gardée, sens ajouté"
    chien = e.sens[0]
    assert [x.vernaculaire for x in chien.exemples] == ["Bísī lé àw̄.", "Bísī ndɔ̄."], "exemple identique pas dupliqué"
    assert chien.categorie_id == cat and chien.definition == "animal"
    assert (e.statut, e.prononciation) == ("validé", "bísī"), "statut le plus avancé, prononciation reprise"
    assert e.notes.splitlines() == ["Source : Keegan", "Glossaire Paratext"]
    assert [v.forme for v in e.variantes] == ["bísɨ̄"]
    assert lexique.medias_de(conn, garder)
    assert conn.execute("SELECT source_id, cible_id, type FROM relations").fetchall() == [(autre, garder, "voir aussi")]
    assert lexique.lire_entree(conn, compose).composants == [garder]
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert doublons.candidats(conn) == []

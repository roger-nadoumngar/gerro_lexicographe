import os

from lexicographe import dico_imprime as d, lexique
from lexicographe.lexique import Entree, Exemple, Sens

# extrait au format du livre, page et en-tête compris
LIVRE = """Petit Dictionnaire de la Langue Ngambay
Ordre Alphabétique
a, a̰, b, ɓ, d, e, ḛ, ə, g, h, i, ḭ, ɨ, j, k, l, m, mb, n, nd, ng, nj, o, o̰, ↄ, p, r, ɗ, s, t, u, ṵ, w, y
bàtú
N chat domestique. Bàtú ngḛ̀y yégɨ̄ mbā kùwà-á. Le chat guette le rat pour le saisir.
bàń [bà̰ń]
INT comment? í-ɗā bàń ɓá í-gə̀r̄ wà? Comment as-tu fait pour savoir?INT pourquoi? ɗèē bàń wà? Pourquoi viens-tu?
7
bàw̄ (Mang)
N père (v. bɔ̀ɔ̄). Tō bɔ̀b-m̄ á ùlà-m̄. C'est mon père qui m'envoie.
bèrè (Syn: bèlè)
AV demain. Bèrè ɓá m-ā kàw̄. Demain je vais partir.
bèlè
AV demain.
làkɔ́l̀ Franτais
N l'école.
kédé
AV avant. Màm ùr dùl. Le boa a avalé la biche-cochon. Expr: àw̄ kédé -poursuivre la route úr nàńg ngàā, m-ā kàw̄ kédé.Descends maintenant, je vais poursuivre ma route.
dūú
Id petit. Ngōn gɨ́ dūú un petit enfant
òō
VT voir. m-ō, ō, òō - je vois, tu vois, il voit
Web Design by A. Concepteur, May 2017
""".splitlines()


def test_lecture_des_articles():
    lecture = d.lire(LIVRE)
    articles = {a.forme: a for a in lecture.articles}
    assert list(articles) == ["bàtú", "bàń", "bàw̄", "bèrè", "bèlè", "làkɔ́l̀", "kédé", "dūú", "òō"]
    assert articles["bàń"].prononciation == "bà̰ń"
    assert [s.glose for s in articles["bàń"].sens] == ["comment?", "pourquoi?"], "sens collé « …savoir?INT »"
    assert articles["bàw̄"].precisions == ["Mang"]
    assert articles["bàw̄"].sens[0].glose == "père (v. bɔ̀ɔ̄)", "le point de « v. » ne coupe pas la glose"
    assert articles["bèrè"].synonymes == ["bèlè"]
    assert articles["làkɔ́l̀"].origine == "Français"
    ex = articles["bàtú"].sens[0].exemples
    assert [(e.vernaculaire, e.traduction) for e in ex] == [
        ("Bàtú ngḛ̀y yégɨ̄ mbā kùwà-á.", "Le chat guette le rat pour le saisir.")]
    assert any("Web Design" in a for a in lecture.avertissements)


def test_regles_de_langue():
    # sans lettre spéciale : ù hors de « où », à en milieu de mot, è sans e final
    assert d.est_langue_documentee("Màm ùr dùl.")
    assert d.est_langue_documentee("Yèé àr nè.")
    assert not d.est_langue_documentee("Le boa a avalé la biche-cochon.")
    assert not d.est_langue_documentee("Où est mon père? Il est très loin.")
    assert d.est_langue_documentee("àl̄-m̄ Kūbū."), "« m » ngambay n'est pas l'élision française m'"
    assert not d.marque_propre("très") and not d.marque_propre("père") and not d.marque_propre("voilà")
    assert d.marque_propre("ndògō") and d.marque_propre("hègè")


def test_exemples_expressions_et_cas_limites():
    articles = {a.forme: a for a in d.lire(LIVRE).articles}
    kede = articles["kédé"]
    assert [(e.vernaculaire, e.traduction) for e in kede.sens[0].exemples] == [
        ("Màm ùr dùl.", "Le boa a avalé la biche-cochon.")]
    expr = kede.expressions[0]
    assert (expr.forme, expr.glose) == ("àw̄ kédé", "poursuivre la route")
    assert expr.exemples[0].vernaculaire == "úr nàńg ngàā, m-ā kàw̄ kédé."
    assert expr.exemples[0].traduction == "Descends maintenant, je vais poursuivre ma route."
    assert (articles["dūú"].sens[0].exemples[0].vernaculaire,
            articles["dūú"].sens[0].exemples[0].traduction) == ("Ngōn gɨ́ dūú", "un petit enfant")
    assert (articles["òō"].sens[0].exemples[0].vernaculaire,
            articles["òō"].sens[0].exemples[0].traduction) == ("m-ō, ō, òō", "je vois, tu vois, il voit")


def _projet_abime(projet):
    """Comme une ancienne extraction : prononciation et dialecte collés à la forme, gloses coupées."""
    conn = projet.conn
    nom = lexique.ajouter_categorie(conn, "Nom", "n")
    ids = {
        "bàń": lexique.enregistrer_entree(conn, Entree(forme="bàń [bà̰ń]", sens=[Sens(glose="comment?")])),
        "bàw̄": lexique.enregistrer_entree(conn, Entree(forme="bàw̄ Mang", sens=[Sens(glose="père (v")])),
        "bàtú": lexique.enregistrer_entree(conn, Entree(forme="bàtú", sens=[Sens(
            glose="chat domestique. Bàtú ngḛ̀y yégɨ̄", categorie_id=nom)])),
        "bèlè": lexique.enregistrer_entree(conn, Entree(forme="bèlè", statut="validé", sens=[Sens(
            glose="demain", exemples=[Exemple(vernaculaire="à ɗèē bèlè.", traduction="Il viendra demain.")])])),
    }
    return ids


def test_fusion(projet):
    ids = _projet_abime(projet)
    conn = projet.conn
    lecture = d.lire(LIVRE)

    simulation = d.fusionner(projet, lecture, "dictionnaire d'exemple", simulation=True)
    assert simulation.simulation and simulation.entrees_creees > 0
    assert lexique.lire_entree(conn, ids["bàń"]).forme == "bàń [bà̰ń]", "la simulation ne touche pas au projet"

    rapport = d.fusionner(projet, lecture, "dictionnaire d'exemple")
    assert (rapport.entrees_creees, rapport.entrees_completees) == (simulation.entrees_creees,
                                                                     simulation.entrees_completees)
    ban = lexique.lire_entree(conn, ids["bàń"])
    assert (ban.forme, ban.prononciation) == ("bàń", "bà̰ń")
    assert [s.glose for s in ban.sens] == ["comment?", "pourquoi?"], "sens manquant ajouté, rien en double"
    assert ban.sens[0].exemples[0].reference == "dictionnaire d'exemple"
    baw = lexique.lire_entree(conn, ids["bàw̄"])
    assert (baw.forme, baw.sens[0].glose) == ("bàw̄", "père (v. bɔ̀ɔ̄)")
    assert "Dialecte : Mang" in baw.notes
    batu = lexique.lire_entree(conn, ids["bàtú"])
    assert batu.sens[0].glose == "chat domestique" and len(batu.sens[0].exemples) == 1
    bele = lexique.lire_entree(conn, ids["bèlè"])
    assert bele.statut == "validé" and len(bele.sens[0].exemples) == 1, "exemple déjà présent : pas de doublon"

    bere = lexique.chercher_par_forme(conn, "bèrè")
    assert bere, "article absent du projet : entrée créée"
    assert any(r[1] == "synonyme" for r in conn.execute(
        "SELECT source_id, type FROM relations WHERE source_id=? OR cible_id=?", (bere[0], bere[0])))
    ecole = lexique.lire_entree(conn, lexique.chercher_par_forme(conn, "làkɔ́l̀")[0])
    assert "Emprunt : français" in ecole.notes and "Source : dictionnaire d'exemple" in ecole.notes
    assert lexique.nom_categorie(conn, ecole.sens[0].categorie_id) == "Nom", "catégorie existante réutilisée"
    expr = lexique.lire_entree(conn, lexique.chercher_par_forme(conn, "àw̄ kédé")[0])
    assert expr.type_forme_complexe == "expression idiomatique"
    assert expr.composants == lexique.chercher_par_forme(conn, "kédé")[:1]

    again = d.fusionner(projet, lecture, "dictionnaire d'exemple")
    assert (again.entrees_creees, again.entrees_completees, again.exemples, again.relations,
            again.expressions_creees) == (0, 0, 0, 0, 0), "réimporter ne change rien"


def test_fichier_word(tmp_path):
    import docx
    document = docx.Document()
    for ligne in LIVRE:
        document.add_paragraph(ligne)
    chemin = os.path.join(tmp_path, "dico.docx")
    document.save(chemin)
    assert len(d.lire(chemin).articles) == 9

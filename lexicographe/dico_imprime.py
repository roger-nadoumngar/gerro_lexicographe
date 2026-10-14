"""Lecture d'un dictionnaire imprimé, présenté comme ceux du Projet des langues
Sara-Baguirmiennes (Keegan et al., Morkeg Books) puis converti en Word ou en texte :

    bèngè [bḛ̀ŋgè] (Syn: kàgɨ̀)            ← vedette, prononciation, synonymes, dialecte, langue d'origine
    N panthère. Bàw̄ dèné jē ... Le père de la fille ...VT laisser. ...   ← sens : étiquette, glose, exemples

Tout se décide par des règles écrites ici :
- une ligne qui commence par une étiquette grammaticale déclarée (N, VT, AV…) contient des sens ;
  une étiquette collée après une fin de phrase (« …avec.VT laisser ») commence un nouveau sens ;
- la glose est la première phrase du sens ; « Expr: forme -glose » introduit une expression ;
- une phrase d'exemple est en langue documentée si elle contient plus de mots portant une marque
  propre à cette langue (lettres et accents absents du français : ɨ ə ɔ ɓ ɗ ŋ, macron, tilde souscrit,
  aigu sur a/i/o/u…) que de mots-outils français ; sinon c'est la traduction. Une phrase en langue
  documentée suivie d'une ou plusieurs phrases en français forme un exemple.
Ce qui ne suit pas ces règles est compté dans les avertissements, jamais deviné."""

import os
import re
import unicodedata
from dataclasses import dataclass, field

from .texte import normaliser

# étiquettes du livre → nom de catégorie (cherchée dans le projet par abréviation puis par nom)
ETIQUETTES = {
    "N": "nom", "NIN": "nom inaliénable", "NP": "nom propre", "NPL": "nom pluriel", "VN": "nom verbal",
    "V": "verbe", "VT": "verbe transitif", "VI": "verbe intransitif", "VPL": "verbe pluriel",
    "AV": "adverbe", "ID": "idéophone", "PR": "pronom", "PRA": "affixe pronominal", "PRP": "préposition",
    "INJ": "interjection", "INT": "interrogatif", "NUM": "numéral", "CNJ": "conjonction",
    "CMP": "complémenteur", "SPC": "spécificateur", "CNT": "contraction", "LOC": "locatif",
    "AUX": "auxiliaire",
}
_ETIQ = "|".join(sorted({e for c in ETIQUETTES for e in (c, c.capitalize(), c[0] + c[1:].lower(), "NIn", "PrA",
                                                          "NPl", "VPl")}, key=len, reverse=True))
_DEBUT_SENS = re.compile(rf"^({_ETIQ})(?= |$)")
# une étiquette en milieu de ligne n'ouvre un sens qu'après une fin de phrase
_SENS_SUIVANT = re.compile(rf"(?<=[.!?)\]}}»\"'’])\s*(?=(?:{_ETIQ}) )")

# abréviations qui ne terminent pas une phrase
ABREVIATIONS = {"esp", "pers", "v", "cf", "qqc", "qqn", "descr", "obj", "pl", "sg", "litt", "lit", "ex", "fréq",
                "irrég", "acc", "inf", "syn", "var", "dial", "m", "mme", "st", "env", "p", "c-à-d", "c.-à-d",
                "ang", "fr", "ar", "subj", "intr", "tr", "expr", "nég", "dém", "sp", "spp", "ca", "av", "apr"}
LANGUES_ORIGINE = ("Français", "Francais", "Arabe", "Anglais", "Sango", "Hausa", "Haoussa", "Fulfulde",
                   "Kanuri", "Latin", "Portugais")

# mots-outils du français (pour reconnaître une traduction)
MOTS_FRANCAIS = set("""le la les un une des du de au aux et ou est sont était il elle ils elles je tu nous
vous on me te se lui leur leurs que qui quoi pour par dans avec sans sur sous pas ne plus mon ma mes ton
ta tes son sa ses notre nos votre vos ce cet cette ces à a y en comme mais donc car si quand où dont très
bien ai as avons avez ont été être avoir fait faire va vais vas allons veut peut doit ça cela""".split())
# formes élidées : comptées seulement devant une apostrophe (« l'eau » ; mais « àl̄-m̄ » est ngambay)
ELISIONS = {"l", "d", "j", "m", "t", "s", "n", "c", "qu", "jusqu", "lorsqu", "puisqu"}
# lettres et accents qu'on ne trouve jamais dans un mot français
_MARQUES = set("ɨəɔɓɗŋӯɛʉƴ") | {"̄", "̰", "̃", "̌"}
_VOYELLES_SANS_AIGU_FR = set("aiouAIOU")   # á í ó ú : aigu impossible en français
_GRAVE_IMPOSSIBLE_FR = set("ioIOmnlrMNLR")  # ì ò ǹ m̀… : grave impossible en français


_A_GRAVE_FRANCAIS = {"à", "là", "voilà", "déjà", "çà", "holà", "au-delà"}


def marque_propre(mot):
    """Vrai si le mot ne peut pas être français : lettre ou accent absent du français, ou accent placé
    là où l'orthographe française ne le met jamais (ù hors de « où », à hors de fin de mot, è non suivi
    de consonnes et d'un e final comme dans « père », « très »), ou début mb-, nd-, ng-, nj-."""
    minuscule = unicodedata.normalize("NFC", mot.lower()).strip("'’-")
    if re.match(r"(mb|nd|ng|nj)[^\W\d_]", minuscule):
        return True
    if "ù" in minuscule and minuscule != "où":
        return True
    if "à" in minuscule and minuscule not in _A_GRAVE_FRANCAIS and not minuscule.endswith("-là"):
        return True
    for m in re.finditer("è", minuscule):
        if not re.match(r"[bcçdfghjklmnpqrstvwxz]+(e|es|ent|ement|ements|ue|ues|s)?$", minuscule[m.end():]) \
                and minuscule[m.end():] != "s":
            return True
    d = unicodedata.normalize("NFD", mot)
    for i, ch in enumerate(d):
        if ch in _MARQUES:
            return True
        precedent = d[i - 1] if i else ""
        if ch == "́" and (precedent in _VOYELLES_SANS_AIGU_FR or precedent.isalpha() and precedent not in "eEyY"):
            return True
        if ch == "̀" and (precedent in _GRAVE_IMPOSSIBLE_FR):
            return True
    return False


def est_langue_documentee(phrase):
    mots = _mots(phrase)
    return sum(marque_propre(m) for m in mots) > sum(map(mot_outil_francais, mots))


def _mots(texte):
    # suites sans espace ni ponctuation : les accents combinants (w̄, ḛ̀) restent dans le mot
    return re.findall(r"[^\s.,;:!?()\[\]{}«»\"“”=]+", unicodedata.normalize("NFC", texte))


def mot_outil_francais(mot):
    mot = mot.lower().replace("’", "'")
    if "'" in mot:
        return mot.split("'")[0] in ELISIONS
    return mot in MOTS_FRANCAIS


def separer_phrase_mixte(phrase):
    """« Ngōn gɨ́ dūú un petit enfant » (exemple et traduction sans point entre eux) : coupe après
    le dernier mot qui ne peut pas être français, si la suite contient un mot-outil français.
    Retourne (vernaculaire, traduction) ou None."""
    morceaux = re.split(r"(\s+)", phrase.strip())
    mots = morceaux[::2]
    derniers = [i for i, m in enumerate(mots) if marque_propre(m.strip(".,;:!?()«»\""))]
    if not derniers or derniers[-1] == len(mots) - 1:
        return None
    coupure = derniers[-1] + 1
    suite = mots[coupure:]
    if any(marque_propre(m) for m in suite) or not any(mot_outil_francais(m.strip(".,;:!?()«»\"")) for m in suite):
        return None
    return " ".join(mots[:coupure]), " ".join(suite)


def separer_debut_vernaculaire(phrase):
    """« Jōó bè deux comme ça » : les premiers mots, s'ils ne peuvent pas être français, forment
    l'exemple ; le reste est sa traduction. Retourne (vernaculaire, traduction) ou None."""
    mots = phrase.strip().split()
    n = 0
    while n < len(mots) and marque_propre(mots[n].strip(".,;:!?()«»\"")):
        n += 1
    if n == 0 or n == len(mots):
        return None
    return " ".join(mots[:n]), " ".join(mots[n:])


@dataclass
class Exemple:
    vernaculaire: str
    traduction: str = ""


@dataclass
class Sens:
    etiquette: str
    glose: str
    exemples: list[Exemple] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class Expression:
    forme: str
    glose: str
    exemples: list[Exemple] = field(default_factory=list)


@dataclass
class Article:
    forme: str
    prononciation: str = ""
    synonymes: list[str] = field(default_factory=list)
    voir: list[str] = field(default_factory=list)
    precisions: list[str] = field(default_factory=list)   # (Mang), (dialecte)…
    origine: str = ""
    sens: list[Sens] = field(default_factory=list)
    expressions: list[Expression] = field(default_factory=list)
    ligne: int = 0


@dataclass
class Lecture:
    articles: list[Article] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)

    def compter(self):
        sens = [s for a in self.articles for s in a.sens]
        return {"articles": len(self.articles), "sens": len(sens),
                "exemples": sum(len(s.exemples) for s in sens) + sum(len(e.exemples) for a in self.articles
                                                                      for e in a.expressions),
                "expressions": sum(len(a.expressions) for a in self.articles),
                "prononciations": sum(bool(a.prononciation) for a in self.articles),
                "synonymes": sum(len(a.synonymes) for a in self.articles)}


# -- lecture du fichier ---------------------------------------------------------------

def lire_lignes(chemin):
    """Paragraphes d'un .docx ou lignes d'un .txt, normalisés (NFC)."""
    if os.path.splitext(chemin)[1].lower() == ".docx":
        import docx
        lignes = [p.text for p in docx.Document(chemin).paragraphs]
    else:
        with open(chemin, encoding="utf-8-sig", errors="replace") as f:
            lignes = f.read().splitlines()
    return [_preparer(l) for l in lignes]


def _preparer(ligne):
    # « Franτais » : ç mal converti par certains extracteurs PDF
    return normaliser(ligne.replace("Franτais", "Français")).strip()


def _debut_du_lexique(lignes):
    """Après la ligne d'ordre alphabétique (« a, a̰, b, ɓ… »), sinon au début."""
    for i, l in enumerate(lignes):
        if l.count(",") >= 10 and all(len(x.strip()) <= 3 for x in l.split(",")):
            return i + 1
    return 0


def _bruit(ligne):
    return not ligne or re.fullmatch(r"/?\s*\d+(\s*/\s*\d+)?", ligne) is not None


def lire(chemin_ou_lignes):
    lignes = lire_lignes(chemin_ou_lignes) if isinstance(chemin_ou_lignes, str) else \
        [_preparer(l) for l in chemin_ou_lignes]
    lecture = Lecture()
    article = None
    for numero in range(_debut_du_lexique(lignes), len(lignes)):
        ligne = lignes[numero]
        if _bruit(ligne):
            continue
        if _DEBUT_SENS.match(ligne):
            if article is None:
                lecture.avertissements.append(f"ligne {numero + 1} : sens sans vedette, ignoré")
                continue
            _lire_sens(ligne, article, lecture)
        elif _ressemble_a_une_vedette(ligne):
            article = _lire_vedette(ligne, numero + 1)
            lecture.articles.append(article)
        else:
            lecture.avertissements.append(f"ligne {numero + 1} : ni vedette ni sens, ignorée : {ligne[:60]}")
    return lecture


def _ressemble_a_une_vedette(ligne):
    sans_parentheses = re.sub(r"\[[^\]]*\]|\([^)]*\)", "", ligne)
    return len(sans_parentheses) <= 50 and not re.search(r"[.!?]\s", sans_parentheses + " ") \
        and len(sans_parentheses.split()) <= 4


def _lire_vedette(ligne, numero):
    article = Article(forme="", ligne=numero)
    m = re.search(r"\[([^\]]*)\]", ligne)
    if m:
        article.prononciation = m.group(1).strip()
        ligne = ligne[:m.start()] + " " + ligne[m.end():]
    for m in re.finditer(r"\(([^)]*)\)", ligne):
        contenu = m.group(1).strip()
        renvoi = re.match(r"(Syn|v\.(?:\s*aussi)?)\s*[.:]?\s*(.*)", contenu, re.I)
        if renvoi:
            cibles = [c.strip() for c in re.split(r"[,;]", renvoi.group(2)) if c.strip()]
            (article.synonymes if renvoi.group(1).lower() == "syn" else article.voir).extend(cibles)
        else:
            article.precisions.append(contenu)
    ligne = re.sub(r"\([^)]*\)", " ", ligne).split()
    if ligne and ligne[-1] in LANGUES_ORIGINE:
        article.origine = "Français" if ligne[-1] == "Francais" else ligne[-1]
        ligne = ligne[:-1]
    article.forme = " ".join(ligne)
    return article


def _lire_sens(ligne, article, lecture):
    debuts = [0] + [m.end() for m in _SENS_SUIVANT.finditer(ligne)]
    for debut, fin in zip(debuts, debuts[1:] + [len(ligne)]):
        morceau = ligne[debut:fin].strip()
        m = _DEBUT_SENS.match(morceau)
        if not m:
            continue
        etiquette = m.group(1)
        reste = morceau[m.end():].strip()
        principal, *expressions = re.split(r"\bExpr\s*:\s*", reste)
        phrases = decouper_phrases(principal)
        sens = Sens(etiquette=etiquette, glose=_sans_point(phrases[0]) if phrases else "")
        sens.exemples = _apparier(phrases[1:], article, lecture, sens.notes)
        article.sens.append(sens)
        for texte in expressions:
            expr = _lire_expression(texte, article, lecture)
            if expr:
                article.expressions.append(expr)


def _lire_expression(texte, article, lecture):
    """« àw̄ kédé -poursuivre la route Úr nàńg…. Descends… » : forme, glose (jusqu'à la fin de phrase
    ou au premier mot en langue documentée), puis exemples."""
    m = re.match(r"(.+?)\s+-\s*(.*)", texte.strip())
    if not m:
        lecture.avertissements.append(f"{article.forme} : expression sans glose : {texte[:50]}")
        return None
    forme, suite = m.group(1).strip(), m.group(2)
    phrases = decouper_phrases(suite)
    if not phrases:
        return Expression(forme=forme, glose="")
    mots = phrases[0].split()
    coupure = next((i for i, mot in enumerate(mots) if i and marque_propre(mot)), len(mots))
    glose = _sans_point(" ".join(mots[:coupure]).rstrip(",;"))
    reste = ([" ".join(mots[coupure:])] if coupure < len(mots) else []) + phrases[1:]
    return Expression(forme=forme, glose=glose, exemples=_apparier(reste, article, lecture, []))


def decouper_phrases(texte):
    """Découpe en phrases : . ! ? hors parenthèses, sauf après une abréviation ou dans « … ».
    Une phrase collée à la suivante (« kédé.Descends ») est séparée si la suivante commence par une majuscule."""
    phrases, debut, profondeur = [], 0, 0
    i = 0
    while i < len(texte):
        ch = texte[i]
        if ch in "([{":
            profondeur += 1
        elif ch in ")]}" and profondeur:
            profondeur -= 1
        elif ch in ".!?" and profondeur == 0:
            j = i + 1
            while j < len(texte) and texte[j] in ".!?»\"'’)":
                j += 1
            suivant = texte[j] if j < len(texte) else ""
            # mot entier avant le point (\w s'arrêterait au premier accent combinant : « jùgɨ̀m » ≠ « m »)
            mot = re.search(r"(\S+)$", texte[debut:i])
            abreviation = ch == "." and mot and mot.group(1).lower().lstrip("([{«\"'").rstrip(".") in ABREVIATIONS
            points = texte[i:j].count(".") >= 2 and ch == "."   # « ni ... ni »
            if not points and (not suivant or suivant.isspace() and not abreviation
                               or suivant.isupper() and not abreviation):
                phrases.append(texte[debut:j].strip())
                debut = j
                i = j
                continue
            i = j
            continue
        i += 1
    if texte[debut:].strip():
        phrases.append(texte[debut:].strip())
    return [p for p in phrases if p]


def _sans_point(texte):
    return texte.strip().rstrip(".").strip()


def _apparier(phrases, article, lecture, notes):
    """Phrases en langue documentée suivies de leur traduction française → exemples."""
    exemples = []
    # « m-ō, ō, òō - je vois, tu vois, il voit » : le tiret sépare le ngambay de sa traduction
    morceaux = []
    for phrase in phrases:
        gauche, tiret, droite = phrase.partition(" - ")
        if tiret and est_langue_documentee(gauche) and droite and not est_langue_documentee(droite):
            morceaux += [gauche.strip(), droite.strip()]
        else:
            morceaux.append(phrase)
    for phrase in morceaux:
        if re.fullmatch(r"[({\[].*[)}\]]", phrase):   # (proverbe), {dit à un garçon}
            if exemples:
                exemples[-1].traduction = (exemples[-1].traduction + " " + phrase).strip()
            else:
                notes.append(phrase)
            continue
        if est_langue_documentee(phrase):
            if exemples and not exemples[-1].traduction:
                exemples[-1].vernaculaire += " " + phrase
            else:
                exemples.append(Exemple(vernaculaire=phrase))
        elif exemples and not exemples[-1].traduction:
            exemples[-1].traduction = phrase
        elif separer_debut_vernaculaire(phrase):   # « Ngàb-ḿ/ngàb-í mon mari, ton mari »
            exemples.append(Exemple(*separer_debut_vernaculaire(phrase)))
        elif exemples:
            exemples[-1].traduction += " " + phrase
        else:
            lecture.avertissements.append(f"{article.forme} : phrase française sans exemple, gardée en note : "
                                          f"{phrase[:60]}")
            notes.append(phrase)
    for ex in exemples:
        if not ex.traduction:
            coupe = separer_phrase_mixte(ex.vernaculaire)
            if coupe:
                ex.vernaculaire, ex.traduction = coupe
            else:
                lecture.avertissements.append(f"{article.forme} : exemple sans traduction : {ex.vernaculaire[:60]}")
    return exemples


# -- fusion dans un projet ------------------------------------------------------------

@dataclass
class RapportFusion:
    entrees_completees: int = 0
    entrees_creees: int = 0
    expressions_creees: int = 0
    sens_ajoutes: int = 0
    gloses_reparees: int = 0
    formes_reparees: int = 0
    prononciations: int = 0
    categories: int = 0
    exemples: int = 0
    relations: int = 0
    a_verifier: int = 0
    simulation: bool = False

    def resume(self):
        debut = "Simulation (rien n'a été écrit) :" if self.simulation else "Import terminé :"
        return "\n".join([
            debut,
            f"  {self.entrees_completees} entrée(s) existante(s) complétée(s), {self.entrees_creees} entrée(s) "
            f"créée(s), {self.expressions_creees} expression(s) créée(s) ;",
            f"  {self.sens_ajoutes} sens ajouté(s), {self.exemples} exemple(s) ajouté(s), "
            f"{self.prononciations} prononciation(s), {self.relations} synonyme(s) et renvoi(s) ;",
            f"  réparations : {self.formes_reparees} forme(s) (« bàń [bà̰ń] » → forme + prononciation), "
            f"{self.gloses_reparees} glose(s) coupée(s) ou mêlée(s) à un exemple, "
            f"{self.categories} catégorie(s) manquante(s) ;",
            f"  {self.a_verifier} entrée(s) marquée(s) « à vérifier » (exemple mal séparé dans le livre).",
        ])


def cle_forme(forme):
    """Forme sans prononciation [..] ni précision (..) : « bàń [bà̰ń] » et « bàń » ont la même clé."""
    forme = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", normaliser(forme or ""))
    return " ".join(forme.split())


def cle_glose(glose):
    """Glose comparable : sans [nom scientifique] ni {remarque}, minuscules, première phrase seulement."""
    glose = normaliser(glose or "").replace("\xa0", " ").lower()
    # crochets fermés, puis crochet resté ouvert par une glose coupée (« net (cesser [de parler, etc »)
    glose = re.sub(r"\[[^\]]*\]|\{[^}]*\}", " ", glose)
    glose = re.sub(r"[\[{][^\]}]*$", " ", glose)
    glose = re.sub(r"\s+([.,;!?])", r"\1", " ".join(glose.split()))
    glose = re.split(r"\.\s", glose + " ", maxsplit=1)[0]
    return glose.strip(" .;,")


def gloses_concordent(du_projet, du_livre):
    """Même glose, ou l'une est le début de l'autre (glose coupée à « (v. », « etc. »… par une
    extraction précédente)."""
    a, b = cle_glose(du_projet), cle_glose(du_livre)
    if not a or not b:
        return False
    return a == b or (len(a) >= 3 and b.startswith(a)) or (len(b) >= 3 and a.startswith(b))


def glose_abimee(du_projet, du_livre):
    """La glose du projet est une version abîmée de celle du livre : coupée (« père (v »),
    sans le nom scientifique, ou suivie de l'exemple (« eau. Dèné lé… »)."""
    def propre(g):
        g = normaliser(g or "").replace("\xa0", " ")
        return re.sub(r"\s+([.,;!?])", r"\1", " ".join(g.split())).casefold()
    p, l = propre(du_projet), propre(du_livre)
    if not p or p == l:
        return False
    sans_crochets = " ".join(re.sub(r"\[[^\]]*\]", " ", l).split()).rstrip(".")
    debut = p.rstrip(". ")
    return (l.startswith(debut) and l[len(debut):].startswith(".") and len(l) > len(debut) + 1   # coupée au point
            # d'une abréviation : « père (v » pour « père (v. bàw̄) »
            or p.startswith(l.rstrip(".") + ".")                              # suivie de l'exemple
            or p.rstrip(".") == sans_crochets                                 # nom scientifique perdu
            or p.startswith(sans_crochets + ".") and sans_crochets != l.rstrip("."))


def categorie_pour(conn, etiquette, creer=True):
    """Catégorie du projet pour une étiquette du livre : d'abord par abréviation ou nom égal à
    l'étiquette, puis par le nom français ; à égalité, la plus utilisée. Sinon elle est créée."""
    from . import lexique

    def plus_utilisee(lignes):
        if not lignes:
            return None
        return max(lignes, key=lambda r: (conn.execute("SELECT COUNT(*) FROM sens WHERE categorie_id=?",
                                                        (r[0],)).fetchone()[0], -r[0]))[0]
    trouvee = plus_utilisee(conn.execute(
        "SELECT id FROM categories WHERE lower(abreviation)=lower(?) OR lower(nom)=lower(?)",
        (etiquette, etiquette)).fetchall())
    nom = ETIQUETTES.get(etiquette.upper(), etiquette)
    trouvee = trouvee or plus_utilisee(conn.execute("SELECT id FROM categories WHERE lower(nom)=lower(?)",
                                                    (nom,)).fetchall())
    if trouvee or not creer:
        return trouvee
    return lexique.ajouter_categorie(conn, nom, etiquette)


def exemple_douteux(exemple):
    """Exemple probablement mal séparé : traduction contenant du ngambay, exemple contenant
    plusieurs mots-outils français, ou traduction absente."""
    return sum(map(marque_propre, _mots(exemple.traduction))) >= 2 or \
        sum(map(mot_outil_francais, _mots(exemple.vernaculaire))) >= 3 or not exemple.traduction


def fusionner(projet, lecture, source, simulation=False):
    """Complète le lexique du projet avec les articles lus. Règles :
    - un article correspond à une entrée de même forme (clé sans [..] ni (..)) dont au moins une
      glose concorde ; sinon une nouvelle entrée est créée ;
    - dans une entrée correspondante, chaque sens du livre complète le sens dont la glose concorde
      (glose abîmée réparée, catégorie manquante ajoutée, exemples absents ajoutés), sinon il est ajouté ;
    - la forme « bàń [bà̰ń] » devient forme « bàń » + prononciation ; dialecte et langue d'origine
      vont dans les notes ;
    - synonymes et renvois deviennent des relations ; chaque « Expr: » devient une entrée
      « expression idiomatique » dont l'article est le composant ;
    - rien n'est supprimé ; une entrée dont un exemple semble mal séparé passe « à vérifier ».
    Avec simulation=True, la fusion est faite sur une copie temporaire du projet : seul le
    rapport est rendu, le projet n'est pas touché."""
    if simulation:
        return _simuler(projet, lecture, source)
    from . import lexique
    conn = projet.conn
    rapport = RapportFusion()
    with projet.en_lot():
        par_cle, gloses = {}, {}
        for eid, forme in conn.execute("SELECT id, forme FROM entrees ORDER BY id").fetchall():
            par_cle.setdefault(cle_forme(forme), []).append(eid)
        for eid, glose in conn.execute("SELECT entree_id, glose FROM sens").fetchall():
            gloses.setdefault(eid, []).append(glose or "")

        prises, correspondance = set(), {}
        for article in lecture.articles:
            cles = {article.forme} | {f"{article.forme} {p}" for p in article.precisions}
            if article.origine:
                cles |= {f"{article.forme} {article.origine}", f"{article.forme} Franτais"}
            candidates = list(dict.fromkeys(i for c in cles for i in par_cle.get(cle_forme(c), [])
                                            if i not in prises))

            def accords(eid):
                return sum(any(gloses_concordent(g, s.glose) for g in gloses.get(eid, [])) for s in article.sens)
            meilleure = max(candidates, key=lambda i: (accords(i), -i), default=None)
            if meilleure is not None and (accords(meilleure) or not article.sens):
                prises.add(meilleure)
                eid = _completer(conn, lexique, article, meilleure, rapport, source)
            else:
                eid = _creer(conn, lexique, article, rapport, source)
                par_cle.setdefault(cle_forme(article.forme), []).append(eid)
                prises.add(eid)
            correspondance[id(article)] = eid

        # renvois et expressions, une fois toutes les entrées en place ; un renvoi vise d'abord
        # l'entrée qui correspond à l'article du livre de cette forme (même résultat à chaque import)
        par_article = {}
        for article in lecture.articles:
            par_article.setdefault(cle_forme(article.forme), correspondance[id(article)])
        for article in lecture.articles:
            eid = correspondance[id(article)]
            for cibles, type_rel in ((article.synonymes, "synonyme"), (article.voir, "voir aussi")):
                for cible in cibles:
                    cid = par_article.get(cle_forme(cible)) or next(iter(par_cle.get(cle_forme(cible), [])), None)
                    if cid is not None:
                        if cid != eid and not conn.execute(
                                "SELECT 1 FROM relations WHERE type=? AND ((source_id=? AND cible_id=?) OR "
                                "(source_id=? AND cible_id=?))", (type_rel, eid, cid, cid, eid)).fetchone():
                            lexique.ajouter_relation(conn, eid, cid, type_rel)
                            rapport.relations += 1
            for expr in article.expressions:
                _expression(conn, lexique, expr, eid, par_cle, gloses, rapport, source)
    return rapport


def _simuler(projet, lecture, source):
    import tempfile
    from .projet import Projet
    dossier = tempfile.mkdtemp(prefix="simulation-")
    copie = projet.sauvegarder_vers(os.path.join(dossier, "copie.lexique"))
    essai = Projet(copie)
    try:
        rapport = fusionner(essai, lecture, source)
    finally:
        essai.fermer()
        import shutil
        shutil.rmtree(dossier, ignore_errors=True)
    rapport.simulation = True
    return rapport


def _vers_exemple(e, source):
    from .lexique import Exemple as ExempleProjet
    return ExempleProjet(vernaculaire=e.vernaculaire, traduction=e.traduction, reference=source)


def _ajouter_exemples(sens_projet, exemples, source, rapport):
    deja = {cle_forme(e.vernaculaire) for e in sens_projet.exemples}
    for e in exemples:
        if cle_forme(e.vernaculaire) not in deja:
            sens_projet.exemples.append(_vers_exemple(e, source))
            deja.add(cle_forme(e.vernaculaire))
            rapport.exemples += 1


def _notes(article, notes, source=None):
    lignes = (notes or "").splitlines()
    ajouts = [f"Dialecte : {p}" if re.fullmatch(r"[A-ZÀ-Ý][\w-]*", p) else p for p in article.precisions]
    if article.origine:
        ajouts.append(f"Emprunt : {article.origine.lower()}")
    if source:
        ajouts.append(f"Source : {source}")
    for a in ajouts:
        if a not in lignes:
            lignes.append(a)
    return "\n".join(lignes).strip()


def _completer(conn, lexique, article, eid, rapport, source):
    entree = lexique.lire_entree(conn, eid)

    def etat():
        return (entree.forme, entree.prononciation, entree.notes, entree.statut,
                [(s.glose, s.categorie_id, len(s.exemples)) for s in entree.sens])
    avant = etat()
    if entree.forme != article.forme:   # « bàń [bà̰ń] », « bàw̄ Mang » : même clé que l'article
        entree.forme = article.forme
        rapport.formes_reparees += 1
    if article.prononciation and not entree.prononciation:
        entree.prononciation = article.prononciation
        rapport.prononciations += 1
    entree.notes = _notes(article, entree.notes)
    utilises = set()
    for sl in article.sens:
        sp = next((s for s in entree.sens if id(s) not in utilises and gloses_concordent(s.glose, sl.glose)), None)
        if sp is None:
            sp = lexique.Sens(glose=sl.glose, categorie_id=categorie_pour(conn, sl.etiquette))
            entree.sens.append(sp)
            rapport.sens_ajoutes += 1
        else:
            if glose_abimee(sp.glose, sl.glose):
                sp.glose = sl.glose
                rapport.gloses_reparees += 1
            if sp.categorie_id is None:
                sp.categorie_id = categorie_pour(conn, sl.etiquette)
                rapport.categories += 1
        utilises.add(id(sp))
        _ajouter_exemples(sp, sl.exemples, source, rapport)
    if entree.statut == "brouillon" and any(exemple_douteux(e) for s in article.sens for e in s.exemples):
        entree.statut = "à vérifier"
        rapport.a_verifier += 1
    if etat() != avant:
        lexique.enregistrer_entree(conn, entree)
        rapport.entrees_completees += 1
    return eid


def _creer(conn, lexique, article, rapport, source):
    entree = lexique.Entree(forme=article.forme, prononciation=article.prononciation,
                            type_morph=_type_morph(article.forme), notes=_notes(article, "", source))
    for sl in article.sens:
        entree.sens.append(lexique.Sens(glose=sl.glose, categorie_id=categorie_pour(conn, sl.etiquette),
                                        exemples=[_vers_exemple(e, source) for e in sl.exemples]))
        rapport.exemples += len(sl.exemples)
    if any(exemple_douteux(e) for s in article.sens for e in s.exemples):
        entree.statut = "à vérifier"
        rapport.a_verifier += 1
    rapport.entrees_creees += 1
    rapport.prononciations += bool(article.prononciation)
    return lexique.enregistrer_entree(conn, entree)


def _type_morph(forme):
    if forme.startswith("-") and forme.endswith("-"):
        return "infix"
    if forme.startswith("-"):
        return "suffix"
    if forme.endswith("-"):
        return "prefix"
    return "stem"


def _expression(conn, lexique, expr, tete_id, par_cle, gloses, rapport, source):
    """Une expression déjà présente (même forme, glose concordante) reçoit les exemples manquants ;
    sinon elle est créée, avec l'article pour composant."""
    for eid in par_cle.get(cle_forme(expr.forme), []):
        if not expr.glose or any(gloses_concordent(g, expr.glose) for g in gloses.get(eid, [])):
            entree = lexique.lire_entree(conn, eid)
            if entree.sens:
                avant = len(entree.sens[0].exemples)
                _ajouter_exemples(entree.sens[0], expr.exemples, source, rapport)
                if len(entree.sens[0].exemples) != avant:
                    lexique.enregistrer_entree(conn, entree)
            return eid
    entree = lexique.Entree(forme=expr.forme, type_morph="phrase", type_forme_complexe="expression idiomatique",
                            composants=[tete_id], notes=f"Source : {source}",
                            sens=[lexique.Sens(glose=expr.glose,
                                               exemples=[_vers_exemple(e, source) for e in expr.exemples])])
    rapport.exemples += len(expr.exemples)
    rapport.expressions_creees += 1
    if any(exemple_douteux(e) for e in expr.exemples):
        entree.statut = "à vérifier"
        rapport.a_verifier += 1
    eid = lexique.enregistrer_entree(conn, entree)
    par_cle.setdefault(cle_forme(expr.forme), []).append(eid)
    gloses.setdefault(eid, []).append(expr.glose)
    return eid

"""Interlinéaire, inventaire des formes de mots et concordance.

Pour chaque forme de mot, le linguiste valide une ou plusieurs analyses
(suite de morphèmes reliés au lexique + glose du mot). Dans le texte, un mot
reçoit, dans cet ordre :
1. l'analyse choisie pour cette occurrence précise, s'il y en a une ;
2. sinon la première analyse validée de la forme ;
3. sinon, à titre de proposition seulement, la décomposition unique trouvée par
   l'analyseur à règles (jamais quand il y en a plusieurs : on ne choisit pas
   à la place du linguiste).
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from .morphologie import Analyseur, Decomposition
from .texte import normaliser

VALIDEE, PROPOSEE, AMBIGUE, INCONNUE = "validée", "proposée", "ambiguë", "inconnue"


@dataclass
class MorphemeAnalyse:
    forme: str
    entree_id: int | None = None
    sens_id: int | None = None
    glose: str = ""
    categorie: str = ""


@dataclass
class Analyse:
    forme: str
    morphemes: list[MorphemeAnalyse] = field(default_factory=list)
    glose_mot: str = ""
    id: int | None = None

    @property
    def segmentation(self):
        return "-".join(m.forme for m in self.morphemes)

    @property
    def gloses(self):
        return "-".join(m.glose or "?" for m in self.morphemes)


@dataclass
class MotInterlineaire:
    position: int              # rang du mot dans la phrase (0, 1, …)
    texte: str                 # tel qu'écrit
    forme: str                 # normalisé (minuscules, NFC)
    statut: str
    analyse: Analyse | None = None
    possibilites: int = 0      # nombre de décompositions trouvées par l'analyseur


def _maintenant():
    return datetime.now().isoformat(timespec="seconds")


def depuis_decomposition(forme, d: Decomposition):
    return Analyse(forme=forme, glose_mot="", morphemes=[
        MorphemeAnalyse(m.forme, m.entree_id, m.sens_id, m.glose, m.categorie) for m in d.morphemes])


# -- analyses validées ------------------------------------------------------------------

def _gloses_sens(conn):
    return {sid: (glose or "", cat or "") for sid, glose, cat in conn.execute(
        "SELECT s.id, s.glose, c.nom FROM sens s LEFT JOIN categories c ON c.id = s.categorie_id")}


def analyses_de(conn, forme, _cache=None):
    """Analyses validées d'une forme, dans l'ordre de validation."""
    gloses = _cache if _cache is not None else _gloses_sens(conn)
    resultat = []
    for aid, glose_mot in conn.execute("SELECT id, glose_mot FROM analyses WHERE forme=? ORDER BY id",
                                       (normaliser(forme).lower(),)).fetchall():
        a = Analyse(forme=forme, glose_mot=glose_mot or "", id=aid)
        for f, eid, sid in conn.execute("""SELECT forme, entree_id, sens_id FROM analyse_morphemes
                                           WHERE analyse_id=? ORDER BY ordre""", (aid,)):
            g, c = gloses.get(sid, ("", ""))
            a.morphemes.append(MorphemeAnalyse(f, eid, sid, g, c))
        resultat.append(a)
    return resultat


def reconstitue(analyse: Analyse):
    """True si les morphèmes, mis bout à bout, redonnent le mot."""
    bout_a_bout = "".join(normaliser(m.forme).lower() for m in analyse.morphemes)
    forme = normaliser(analyse.forme).lower()
    return bout_a_bout in (forme, forme.replace("-", ""))


def valider(conn, analyse: Analyse, cache_gloses=None, formes_sous_jacentes=False):
    """Enregistre l'analyse d'une forme (réutilise une analyse identique existante).
    Retourne son id. Par défaut les morphèmes doivent reconstituer le mot ;
    `formes_sous_jacentes` accepte des morphèmes notés sous leur forme de base
    (« buk-o » pour « buki »), comme le permet FLEx."""
    forme = normaliser(analyse.forme).lower()
    if not analyse.morphemes:
        raise ValueError("Une analyse contient au moins un morphème.")
    if not formes_sous_jacentes and not reconstitue(analyse):
        raise ValueError(f"Les morphèmes « {analyse.segmentation} » ne reconstituent pas le mot « {forme} ».")
    signature = [(normaliser(m.forme).lower(), m.entree_id, m.sens_id) for m in analyse.morphemes]
    for existante in analyses_de(conn, forme, cache_gloses):
        if [(m.forme, m.entree_id, m.sens_id) for m in existante.morphemes] == signature:
            if analyse.glose_mot and analyse.glose_mot != existante.glose_mot:
                with conn:
                    conn.execute("UPDATE analyses SET glose_mot=? WHERE id=?", (analyse.glose_mot, existante.id))
            return existante.id
    with conn:
        aid = conn.execute("INSERT INTO analyses (forme, glose_mot, date) VALUES (?, ?, ?)",
                           (forme, analyse.glose_mot or None, _maintenant())).lastrowid
        conn.executemany("""INSERT INTO analyse_morphemes (analyse_id, ordre, forme, entree_id, sens_id)
                            VALUES (?, ?, ?, ?, ?)""",
                         [(aid, i, f, eid, sid) for i, (f, eid, sid) in enumerate(signature, start=1)])
    return aid


def supprimer(conn, analyse_id):
    with conn:
        conn.execute("DELETE FROM analyses WHERE id=?", (analyse_id,))


def choisir_pour_occurrence(conn, ref, position, analyse_id):
    """Fixe l'analyse d'une occurrence précise (mot ambigu) ; None revient au choix par défaut."""
    with conn:
        if analyse_id is None:
            conn.execute("DELETE FROM choix_occurrences WHERE ref=? AND position=?", (ref, position))
        else:
            conn.execute("INSERT OR REPLACE INTO choix_occurrences (ref, position, analyse_id) VALUES (?, ?, ?)",
                         (ref, position, analyse_id))


# -- interlinéaire d'une phrase -----------------------------------------------------------

class Contexte:
    """Données partagées pour analyser beaucoup de phrases d'un coup."""

    def __init__(self, projet):
        self.projet = projet
        self.conn = projet.conn
        self.tokeniseur = projet.tokeniseur_vern
        self.analyseur = Analyseur(self.conn)
        self.gloses = _gloses_sens(self.conn)
        self._analyses = {}
        self._decompositions = {}

    def analyses(self, forme):
        if forme not in self._analyses:
            self._analyses[forme] = analyses_de(self.conn, forme, self.gloses)
        return self._analyses[forme]

    def decompositions(self, forme):
        if forme not in self._decompositions:
            self._decompositions[forme] = self.analyseur.analyser(forme)
        return self._decompositions[forme]

    def statut(self, forme):
        """(statut, analyse ou None, nombre de décompositions)"""
        validees = self.analyses(forme)
        if validees:
            return VALIDEE, validees[0], 0
        decs = self.decompositions(forme)
        if len(decs) == 1:
            return PROPOSEE, depuis_decomposition(forme, decs[0]), 1
        return (AMBIGUE if decs else INCONNUE), None, len(decs)


def phrase(projet, ref, texte, contexte=None):
    """[MotInterlineaire] de la phrase."""
    ctx = contexte or Contexte(projet)
    choix = dict(ctx.conn.execute("SELECT position, analyse_id FROM choix_occurrences WHERE ref=?", (ref,)))
    mots = []
    for brut, forme in ctx.tokeniseur.decouper(texte or ""):
        if not forme:
            continue
        position = len(mots)
        statut, analyse, n = ctx.statut(forme)
        if position in choix:
            choisie = next((a for a in ctx.analyses(forme) if a.id == choix[position]), None)
            if choisie:
                statut, analyse = VALIDEE, choisie
        mots.append(MotInterlineaire(position, brut, forme, statut, analyse, n))
    return mots


# -- inventaire des formes de mots ---------------------------------------------------------

@dataclass
class FormeMot:
    forme: str
    frequence: int
    phrases: int
    statut: str
    au_lexique: bool
    analyse: str = ""          # segmentation et gloses, pour affichage


def inventaire(projet):
    """Toutes les formes de mots du corpus (langue documentée), les plus fréquentes d'abord."""
    ctx = Contexte(projet)
    frequences, dans_phrases = Counter(), Counter()
    for (texte,) in ctx.conn.execute("SELECT vernaculaire FROM phrases WHERE vernaculaire IS NOT NULL"):
        mots = ctx.tokeniseur.mots(texte)
        frequences.update(mots)
        dans_phrases.update(set(mots))
    lexique_formes = {normaliser(f).lower() for (f,) in ctx.conn.execute(
        "SELECT forme FROM entrees UNION SELECT forme_citation FROM entrees WHERE forme_citation IS NOT NULL")}
    resultat = []
    for forme, n in frequences.items():
        statut, analyse, _ = ctx.statut(forme)
        resume = f"{analyse.segmentation}  «{analyse.gloses}»" if analyse else ""
        resultat.append(FormeMot(forme, n, dans_phrases[forme], statut, forme in lexique_formes, resume))
    resultat.sort(key=lambda f: (-f.frequence, f.forme))
    return resultat


def couverture(projet):
    """Part des occurrences du corpus dont l'analyse est validée : {statut: occurrences}."""
    compte = Counter()
    for f in inventaire(projet):
        compte[f.statut] += f.frequence
    return dict(compte)


# -- concordance ---------------------------------------------------------------------------

@dataclass
class Ligne:
    ref: str
    gauche: str
    cle: str
    droite: str
    traduction: str


def concordance(projet, recherche, mode="mot", cote="vernaculaire", contexte=60, limite=2000):
    """Occurrences de `recherche` avec leur contexte.
    mode « mot » : forme de mot exacte (insensible à la casse) ;
    mode « morphème » : mots dont une analyse validée contient ce morphème ;
    mode « texte » : suite de caractères n'importe où ;
    mode « regex » : expression régulière."""
    recherche = normaliser(recherche).strip()
    if not recherche:
        return []
    conn = projet.conn
    if cote not in ("vernaculaire", "analyse"):
        raise ValueError(cote)
    autre = "analyse" if cote == "vernaculaire" else "vernaculaire"
    tokeniseur = projet.tokeniseur_vern if cote == "vernaculaire" else projet.tokeniseur_analyse

    formes_cibles = None
    if mode == "morphème":
        formes_cibles = {f for (f,) in conn.execute(
            """SELECT DISTINCT a.forme FROM analyses a JOIN analyse_morphemes m ON m.analyse_id = a.id
               WHERE lower(m.forme) = ?""", (recherche.lower(),))}
    elif mode == "regex":
        try:
            motif = re.compile(recherche, re.IGNORECASE)
        except re.error as e:
            raise ValueError(f"Expression régulière invalide : {e}") from e
    resultat = []
    lignes = conn.execute(f"SELECT ref, {cote}, {autre} FROM phrases WHERE {cote} IS NOT NULL").fetchall()
    from .usfm import cle_reference
    lignes.sort(key=lambda l: cle_reference(l[0]))
    for ref, texte, traduction in lignes:
        texte = normaliser(texte)
        trouves = []
        if mode in ("mot", "morphème"):
            pos = 0
            for brut, forme in tokeniseur.decouper(texte):
                if forme and (forme == recherche.lower() if mode == "mot" else forme in formes_cibles):
                    trouves.append((pos, pos + len(brut)))
                pos += len(brut)
        elif mode == "texte":
            bas, cible = texte.lower(), recherche.lower()
            i = bas.find(cible)
            while i >= 0:
                trouves.append((i, i + len(cible)))
                i = bas.find(cible, i + max(1, len(cible)))
        else:
            trouves = [(m.start(), m.end()) for m in motif.finditer(texte) if m.end() > m.start()]
        for debut, fin in trouves:
            resultat.append(Ligne(ref, texte[max(0, debut - contexte):debut], texte[debut:fin],
                                  texte[fin:fin + contexte], traduction or ""))
            if len(resultat) >= limite:
                return resultat
    return resultat

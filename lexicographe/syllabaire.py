"""Préparation de syllabaires (inspiré de PrimerPrep, SIL).

Méthode explicite, sans devinette :
* les mots sont découpés en graphèmes selon l'alphabet déclaré par le linguiste
  (multigraphes compris : « ng », « ŋg », « nj »… ; correspondance la plus longue) ;
  un caractère absent de l'alphabet compte comme un graphème à part, et il est signalé ;
* les marques de ton (accents combinants) peuvent être enseignées séparément :
  « ká » = « k » + « a » + « ◌́ » ;
* ordre proposé : à chaque leçon, le graphème qui rend lisibles le plus de nouveaux
  mots avec les graphèmes déjà appris ; à égalité, le plus fréquent ; la
  justification (« débloque N mots ») accompagne chaque leçon ; le linguiste peut
  réordonner librement ;
* les noms propres (mots écrits avec une majuscule dans au moins 80 % de leurs
  occurrences) peuvent être écartés des listes de mots.
"""

import csv
import json
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .texte import normaliser

CERCLE = "◌"   # ◌ : support d'affichage d'une marque isolée


def affichage(grapheme):
    """Une marque combinante seule s'affiche sur un cercle pointillé (◌́)."""
    if grapheme and all(unicodedata.category(c)[0] == "M" for c in grapheme):
        return CERCLE + grapheme
    return grapheme


class Decoupeur:
    def __init__(self, alphabet="", marques_separees=True):
        self.graphemes = []
        for g in (alphabet or "").split():
            g = unicodedata.normalize("NFD", normaliser(g).lower())
            if g and g not in self.graphemes:
                self.graphemes.append(g)
        self.declares = set(self.graphemes)
        self.longueur_max = max((len(g) for g in self.graphemes), default=1)
        self.marques_separees = marques_separees

    def decouper(self, mot):
        """Graphèmes du mot (NFC), dans l'ordre."""
        d = unicodedata.normalize("NFD", normaliser(mot).lower())
        resultat, i = [], 0
        while i < len(d):
            # correspondance la plus longue avec un graphème déclaré, sinon un seul caractère
            n = next((n for n in range(min(self.longueur_max, len(d) - i), 0, -1)
                      if d[i:i + n] in self.declares), 1)
            j = i + n
            if n == 1 and unicodedata.category(d[i])[0] not in "LM":
                i += 1   # tiret, apostrophe, chiffre… : rien à enseigner
                continue
            if not self.marques_separees and unicodedata.category(d[i])[0] != "M":
                # tons non séparés : la lettre garde les marques qui la suivent (« á » = une unité)
                while j < len(d) and unicodedata.category(d[j])[0] == "M" and d[j] not in self.declares:
                    j += 1
            resultat.append(unicodedata.normalize("NFC", d[i:j]))
            i = j
        return resultat

    def est_declare(self, grapheme):
        return unicodedata.normalize("NFD", grapheme) in self.declares

    def nature(self, grapheme):
        """« lettre » (déclarée), « ton » (marque enseignée à part) ou « non déclaré »."""
        if self.est_declare(grapheme):
            return "lettre"
        if all(unicodedata.category(c)[0] == "M" for c in grapheme):
            return "ton"
        return "non déclaré"


@dataclass
class Grapheme:
    grapheme: str
    occurrences: int = 0
    mots: int = 0
    nature: str = "lettre"            # « lettre », « ton » ou « non déclaré »
    exemples: list[str] = field(default_factory=list)


@dataclass
class Lecon:
    numero: int
    grapheme: str
    debloques: int                      # nouveaux mots lisibles grâce à ce graphème
    lisibles: int                       # total de mots lisibles après cette leçon
    occurrences_lisibles: float         # part des occurrences du corpus lisibles (0–1)
    mots: list[tuple[str, int]] = field(default_factory=list)       # (mot, fréquence) nouveaux
    phrases: list[tuple[str, str]] = field(default_factory=list)    # (référence, phrase) nouvellement lisibles


class Syllabaire:
    """Calculs sur le corpus du projet (langue documentée)."""

    def __init__(self, projet, marques_separees=True, exclure_noms_propres=True):
        self.projet = projet
        self.decoupeur = Decoupeur(projet.reglage("alphabet_vern"), marques_separees)
        tok = projet.tokeniseur_vern
        self.frequences = Counter()
        majuscules = Counter()
        self.phrases = []
        for ref, texte in projet.conn.execute("SELECT ref, vernaculaire FROM phrases WHERE vernaculaire IS NOT NULL"):
            mots = []
            for brut, mot in tok.decouper(texte):
                if not mot:
                    continue
                mots.append(mot)
                self.frequences[mot] += 1
                if brut[:1].isupper():
                    majuscules[mot] += 1
            if mots:
                self.phrases.append((ref, texte, mots))
        self.noms_propres = {m for m, n in self.frequences.items() if majuscules[m] >= 0.8 * n}
        self.exclure_noms_propres = exclure_noms_propres
        self.graphemes_de = {m: self.decoupeur.decouper(m) for m in self.frequences}

    def mots_utiles(self):
        return {m: n for m, n in self.frequences.items()
                if not (self.exclure_noms_propres and m in self.noms_propres)
                and not any(c.isdigit() for c in m) and self.graphemes_de[m]}

    # -- inventaire -------------------------------------------------------------------
    def inventaire(self):
        """Graphèmes du corpus, les plus fréquents d'abord."""
        infos = {}
        for mot, n in self.mots_utiles().items():
            vus = set()
            for g in self.graphemes_de[mot]:
                info = infos.setdefault(g, Grapheme(g, nature=self.decoupeur.nature(g)))
                info.occurrences += n
                if g not in vus:
                    info.mots += 1
                    vus.add(g)
                    if len(info.exemples) < 40:
                        info.exemples.append(mot)
        for info in infos.values():
            info.exemples = sorted(info.exemples, key=lambda m: -self.frequences[m])[:8]
        return sorted(infos.values(), key=lambda g: (-g.occurrences, g.grapheme))

    def suites_frequentes(self, limite=30):
        """Suites de deux lettres les plus fréquentes : candidats multigraphes à examiner
        par le linguiste (le logiciel ne décide pas qu'une suite est un graphème)."""
        compte = Counter()
        for mot, n in self.mots_utiles().items():
            lettres = [c for c in unicodedata.normalize("NFD", mot) if unicodedata.category(c)[0] != "M"]
            for a, b in zip(lettres, lettres[1:]):
                if a.isalpha() and b.isalpha():
                    compte[a + b] += n
        return compte.most_common(limite)

    # -- ordre d'enseignement --------------------------------------------------------------
    def ordre_propose(self):
        """[(graphème, mots débloqués)] : à chaque étape, le graphème qui rend lisibles le plus de
        nouveaux mots ; à égalité, le plus fréquent dans le corpus."""
        mots = self.mots_utiles()
        frequence_g = {g.grapheme: g.occurrences for g in self.inventaire()}
        restants = {m: set(self.graphemes_de[m]) for m in mots}
        par_grapheme = defaultdict(set)
        for m, gs in restants.items():
            for g in gs:
                par_grapheme[g].add(m)
        a_un = defaultdict(int)          # graphème → nb de mots auxquels il ne manque que lui
        for m, gs in restants.items():
            if len(gs) == 1:
                a_un[next(iter(gs))] += 1
        candidats = set(frequence_g)
        ordre = []
        while candidats:
            g = max(candidats, key=lambda x: (a_un[x], frequence_g[x], x))
            ordre.append((g, a_un[g]))
            candidats.discard(g)
            for m in par_grapheme[g]:
                gs = restants[m]
                if len(gs) == 1:
                    a_un[g] -= 1
                gs.discard(g)
                if len(gs) == 1:
                    a_un[next(iter(gs))] += 1
        return ordre

    def lecons(self, ordre, mots_par_lecon=40, phrases_par_lecon=10, longueur_max_phrase=12):
        """Leçons dans l'ordre donné : nouveaux mots et phrases lisibles à chaque étape."""
        mots = self.mots_utiles()
        total_occ = sum(mots.values()) or 1
        appris = set()
        deja_mots, deja_phrases = set(), set()
        resultat = []
        lisibles_occ = 0
        for numero, g in enumerate(ordre, start=1):
            appris.add(g)
            nouveaux = [(m, n) for m, n in mots.items()
                        if m not in deja_mots and set(self.graphemes_de[m]) <= appris]
            nouveaux.sort(key=lambda x: (-x[1], x[0]))
            deja_mots.update(m for m, _ in nouveaux)
            lisibles_occ += sum(n for _, n in nouveaux)
            phrases = []
            for ref, texte, mots_phrase in self.phrases:
                if ref in deja_phrases or len(mots_phrase) > longueur_max_phrase:
                    continue
                if all(set(self.graphemes_de[m]) <= appris for m in mots_phrase):
                    deja_phrases.add(ref)
                    if len(phrases) < phrases_par_lecon:
                        phrases.append((ref, texte))
            resultat.append(Lecon(numero, g, len(nouveaux), len(deja_mots), lisibles_occ / total_occ,
                                  nouveaux[:mots_par_lecon], phrases))
        return resultat


# -- ordre enregistré dans le projet -------------------------------------------------------------

def ordre_enregistre(projet):
    try:
        return json.loads(projet.reglage("syllabaire_ordre") or "[]")
    except ValueError:
        return []


def enregistrer_ordre(projet, ordre):
    projet.definir_reglages({"syllabaire_ordre": json.dumps(list(ordre), ensure_ascii=False)})


# -- exports -------------------------------------------------------------------------------------

def gloses(conn):
    """{forme en minuscules: première glose} pour accompagner les mots des leçons."""
    resultat = {}
    for forme, glose in conn.execute("""SELECT e.forme, s.glose FROM entrees e JOIN sens s ON s.entree_id = e.id
                                        WHERE s.glose IS NOT NULL ORDER BY s.ordre"""):
        resultat.setdefault(normaliser(forme).lower(), glose)
    return resultat


def exporter_texte(projet, lecons, chemin):
    g = gloses(projet.conn)
    with open(chemin, "w", encoding="utf-8") as f:
        titre = f"SYLLABAIRE — {projet.reglage('langue_vern_nom') or projet.nom}".upper()
        f.write(titre + "\n" + "=" * len(titre) + "\n\n")
        for l in lecons:
            f.write(f"Leçon {l.numero} : {affichage(l.grapheme)}\n")
            f.write(f"  {l.debloques} nouveau(x) mot(s) ; {l.lisibles} mots lisibles en tout "
                    f"({100 * l.occurrences_lisibles:.0f} % du corpus)\n")
            if l.mots:
                f.write("  Mots : " + ", ".join(m + (f" ({g[m]})" if m in g else "") for m, _ in l.mots) + "\n")
            for ref, texte in l.phrases:
                f.write(f"  « {texte} »  [{ref}]\n")
            f.write("\n")
    return len(lecons)


def exporter_csv(projet, lecons, chemin):
    g = gloses(projet.conn)
    with open(chemin, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lecon", "grapheme", "mot", "frequence", "glose"])
        for l in lecons:
            for m, n in l.mots:
                w.writerow([l.numero, affichage(l.grapheme), m, n, g.get(m, "")])
    return len(lecons)

"""Analyseur morphologique à règles déclarées.

L'analyseur ne devine rien : il n'utilise que ce que le linguiste a déclaré
dans le lexique.
* Les morphèmes sont les entrées du lexique et leurs allomorphes.
* Leur position vient de leur type morphologique : préfixes et proclitiques
  avant le radical, suffixes et enclitiques après, clitiques des deux côtés ;
  tout autre type (radical, racine, particule…) peut servir de radical.
* Les marques de frontière écrites dans les formes d'affixes (« ka- »,
  « -je », « =g ») sont retirées pour la comparaison.
* Un mot = préfixes* + un radical + suffixes*, chaque morceau égal à une forme
  déclarée. Toutes les découpes possibles sont proposées, les plus simples
  d'abord ; c'est le linguiste qui valide la bonne.

* Un allomorphe dont l'environnement est écrit de façon formelle (« / N _ »,
  « / _ # »…, classes déclarées dans les réglages du projet) n'est proposé que si
  cet environnement est respecté ; un environnement en texte libre est seulement
  affiché.

* Redoublement : un mot fait de deux copies d'une même suite analysable (« tɔ̄l-tɔ̄l », « njálnjál »)
  reçoit aussi la décomposition base + copie (glosée « RED »). La copie doit avoir les mêmes lettres ;
  ses tons peuvent différer (« déréré-dèrèrè »). Un mot redoublé enregistré tel quel dans le lexique
  reste proposé d'abord (un seul morphème).
* Infixe (type « infix » dans le lexique) : proposé à l'intérieur d'un radical déclaré — jamais en
  bordure —, et seulement là où son environnement formel le permet s'il en a un (« / #C _ » : après
  la première consonne). Le radical est alors noté en deux morceaux autour de l'infixe : k‹ar›tab.

* Corpus sans tons (réglage « analyse_sans_tons » déclaré dans le projet) : quand l'écriture du corpus
  n'a pas toujours les tons ni les autres signes combinants, les formes sont aussi comparées sans ces
  signes, mais seulement pour un mot qui n'a aucune décomposition exacte. Ces décompositions sont
  marquées « approchées » et ne sont jamais proposées comme évidentes : le linguiste choisit.

* Circonfixe (type « circumfix », forme écrite en deux parties : « ka- -ŋ » ou « ka-…-ŋ ») : proposé
  seulement quand ses deux parties entourent directement un radical déclaré (ka + radical + ŋ).
* Redoublement partiel : une copie du début du radical placée devant lui (« ba-bal », « kɔ̄-kɔ̄rɔ́ »), formée
  de consonnes puis de voyelles. Il n'est proposé que si le projet déclare la classe des voyelles
  (« V = a e i o u … » dans les réglages) : sans elle, on ne peut pas dire ce qu'est une syllabe.

Limite assumée : le redoublement partiel en fin de mot (copie de la dernière syllabe) n'est pas traité.
"""

import unicodedata
from dataclasses import dataclass, field

from .texte import normaliser

AVANT = {"prefix", "proclitic"}
APRES = {"suffix", "enclitic"}
LES_DEUX = {"clitic"}
NON_RADICAUX = AVANT | APRES | LES_DEUX | {"infix", "circumfix"}
MARQUES = "-=~"
MAX_AFFIXES = 4
MAX_RESULTATS = 30


@dataclass(frozen=True)
class Morpheme:
    forme: str                 # forme telle qu'elle apparaît dans le mot
    entree_id: int
    sens_id: int | None
    glose: str
    categorie: str
    role: str                  # « avant », « radical », « après », « infixe », « redoublement »
    environnement: str = ""    # condition d'un allomorphe
    suite: bool = False        # seconde partie (radical coupé par un infixe, fin d'un circonfixe)


@dataclass
class Decomposition:
    morphemes: list[Morpheme] = field(default_factory=list)
    approchee: bool = False    # trouvée en ignorant les tons (corpus sans tons)

    @property
    def segmentation(self):
        """« ka-kó-je » : formes séparées par des tirets ; un infixe entre chevrons : « k‹ar›tab »."""
        texte = ""
        for i, m in enumerate(self.morphemes):
            if m.role == "infixe":
                texte += f"‹{m.forme}›"
            elif m.suite and m.role == "circonfixe":
                texte += "-" + m.forme      # fin du circonfixe : ka-kó-ŋ
            elif m.suite or i == 0:
                texte += m.forme
            else:
                texte += "-" + m.forme
        return texte

    @property
    def gloses(self):
        texte = ""
        for i, m in enumerate(self.morphemes):
            if m.suite:
                continue
            glose = m.glose or "?"
            texte += f"‹{glose}›" if m.role == "infixe" else (glose if i == 0 else "-" + glose)
        return texte

    def cle(self):
        # les plus simples d'abord : moins de morphèmes, puis moins d'affixes
        return (self.approchee, len(self.morphemes), sum(m.role != "radical" for m in self.morphemes),
                self.segmentation)


def _sans_signes(texte):
    """Texte décomposé (NFD) sans ses signes combinants ; les tirets sont gardés."""
    return "".join(c for c in unicodedata.normalize("NFD", texte) if not unicodedata.combining(c))


def _sans_tons(texte):
    """Lettres seules : signes combinants (tons, nasalité) et tirets retirés."""
    return "".join(c for c in unicodedata.normalize("NFD", texte) if not unicodedata.combining(c) and c != "-")


def _nettoyer(forme):
    return normaliser(forme).strip().strip(MARQUES).lower()


# -- environnements des allomorphes ---------------------------------------------------------------

BORD = "#"


def lire_classes(texte):
    """Classes phonologiques déclarées : « V = a e i o u ; N = m n ŋ » (une par ligne ou séparées
    par « ; »). Retourne {nom: [graphèmes, les plus longs d'abord]}."""
    classes = {}
    for ligne in (texte or "").replace(";", "\n").split("\n"):
        if "=" not in ligne:
            continue
        nom, membres = ligne.split("=", 1)
        nom = nom.strip()
        valeurs = [normaliser(m).lower() for m in membres.split() if m.strip()]
        if nom and valeurs:
            # ordre de déclaration conservé (tri stable), les plus longs d'abord
            classes[nom] = sorted(dict.fromkeys(valeurs), key=lambda m: -len(m))
    return classes


class Environnement:
    """Environnement d'un allomorphe, écrit comme dans FLEx : « / V _ », « / _ # », « / N _ C ».
    `_` est la place de l'allomorphe, `#` le bord du mot, une classe s'écrit par son nom (lettre
    majuscule ou [nom entre crochets]), tout autre caractère est une lettre à trouver telle quelle.
    Plusieurs environnements possibles se séparent par « ; ». Un texte qui ne suit pas cette
    écriture (« après nasale ») n'est pas formel : il est affiché mais pas appliqué."""

    def __init__(self, texte, classes):
        self.texte = (texte or "").strip()
        self.classes = classes
        self.alternatives = []
        self.formel = bool(self.texte)
        for alt in self.texte.split(";") if self.texte else []:
            alt = alt.strip()
            if not alt.startswith("/") or alt.count("_") != 1:
                self.formel = False
                return
            gauche, droite = alt[1:].split("_")
            g, d = self._jetons(gauche), self._jetons(droite)
            if g is None or d is None:
                self.formel = False
                return
            self.alternatives.append((g, d))

    def _jetons(self, texte):
        jetons, i = [], 0
        texte = normaliser(texte)
        while i < len(texte):
            c = texte[i]
            if c.isspace():
                i += 1
            elif c == BORD:
                jetons.append(("bord", None))
                i += 1
            elif c == "[":
                fin = texte.find("]", i)
                nom = texte[i + 1:fin] if fin > 0 else ""
                if nom not in self.classes:
                    return None          # classe inconnue : on ne devine pas ce qu'elle contient
                jetons.append(("classe", self.classes[nom]))
                i = fin + 1
            elif c.isupper():
                if c not in self.classes:
                    return None
                jetons.append(("classe", self.classes[c]))
                i += 1
            else:
                jetons.append(("lettre", c.lower()))
                i += 1
        return jetons

    @staticmethod
    def _gauche(jetons, contexte):
        fin = len(contexte)
        for genre, valeur in reversed(jetons):
            if genre == "bord":
                if fin != 0:
                    return False
            elif genre == "lettre":
                if not contexte[:fin].endswith(valeur):
                    return False
                fin -= len(valeur)
            else:
                membre = next((m for m in valeur if contexte[:fin].endswith(m)), None)
                if membre is None:
                    return False
                fin -= len(membre)
        return True

    @staticmethod
    def _droite(jetons, contexte):
        debut = 0
        for genre, valeur in jetons:
            if genre == "bord":
                if debut != len(contexte):
                    return False
            elif genre == "lettre":
                if not contexte.startswith(valeur, debut):
                    return False
                debut += len(valeur)
            else:
                membre = next((m for m in valeur if contexte.startswith(m, debut)), None)
                if membre is None:
                    return False
                debut += len(membre)
        return True

    def accepte(self, gauche, droite):
        """True si l'allomorphe peut apparaître entre ces contextes (toujours vrai si non formel)."""
        if not self.formel:
            return True
        return any(self._gauche(g, gauche) and self._droite(d, droite) for g, d in self.alternatives)


class Analyseur:
    """Index des formes de morphèmes du lexique ; à reconstruire après modification du lexique."""

    def __init__(self, conn):
        self.formes = {"avant": {}, "radical": {}, "apres": {}, "infixe": {}}
        self.circonfixes = {}      # partie gauche → [(partie droite, Morpheme)]
        premiers_sens = {}
        for sid, eid, glose, cat in conn.execute(
                """SELECT s.id, s.entree_id, s.glose, c.nom FROM sens s
                   LEFT JOIN categories c ON c.id = s.categorie_id ORDER BY s.entree_id, s.ordre, s.id"""):
            premiers_sens.setdefault(eid, (sid, glose or "", cat or ""))
        entrees = conn.execute("SELECT id, forme, forme_citation, type_morph FROM entrees").fetchall()
        allomorphes = {}
        for eid, forme, env in conn.execute(
                "SELECT entree_id, forme, environnement FROM variantes WHERE type='allomorphe'"):
            allomorphes.setdefault(eid, []).append((forme, env or ""))
        for eid, forme, citation, type_morph in entrees:
            sid, glose, cat = premiers_sens.get(eid, (None, "", ""))
            if type_morph in AVANT:
                roles = ["avant"]
            elif type_morph in APRES:
                roles = ["apres"]
            elif type_morph in LES_DEUX:
                roles = ["avant", "apres"]
            elif type_morph == "infix":
                roles = ["infixe"]
            elif type_morph == "circumfix":
                self._ajouter_circonfixe(eid, sid, glose, cat, [forme, citation])
                continue
            elif type_morph in NON_RADICAUX:
                continue
            else:
                roles = ["radical"]
            variantes = [(forme, ""), (citation, "")] + allomorphes.get(eid, [])
            for f, env in variantes:
                f = _nettoyer(f or "")
                if not f:
                    continue
                for role in roles:
                    m = Morpheme(f, eid, sid, glose, cat, role, env)
                    liste = self.formes[role].setdefault(f, [])
                    deja = next((i for i, x in enumerate(liste) if x.entree_id == eid), None)
                    if deja is None:
                        liste.append(m)
                    elif env and not liste[deja].environnement:
                        # un allomorphe de même forme avec un environnement déclaré : sa condition s'applique
                        liste[deja] = m
        self.longueurs = {role: sorted({len(f) for f in d}, reverse=True) for role, d in self.formes.items()}
        ligne = conn.execute("SELECT valeur FROM projet WHERE cle='classes_phonologiques'").fetchone()
        self.classes = lire_classes(ligne[0] if ligne else "")
        ligne = conn.execute("SELECT valeur FROM projet WHERE cle='analyse_sans_tons'").fetchone()
        self.sans_tons = bool(ligne and ligne[0] == "1")
        # mêmes formes, indexées sans leurs signes combinants (corpus écrit sans tons)
        self.formes_st = {role: {} for role in self.formes}
        for role, d in self.formes.items():
            for f, liste in d.items():
                self.formes_st[role].setdefault(_sans_signes(f), []).extend(liste)
        self.longueurs_st = {role: sorted({len(f) for f in d}, reverse=True) for role, d in self.formes_st.items()}
        self.circonfixes_st = {}
        for gauche, liste in self.circonfixes.items():
            for droite, m in liste:
                self.circonfixes_st.setdefault(_sans_signes(gauche), []).append((_sans_signes(droite), m))
        self._environnements = {}

    def _ajouter_circonfixe(self, eid, sid, glose, cat, formes):
        import re
        for forme in formes:
            parties = [p for p in re.split(r"\s+|…|\.\.\.", normaliser(forme or "").strip()) if p.strip(MARQUES)]
            if len(parties) != 2:
                continue
            gauche, droite = _nettoyer(parties[0]), _nettoyer(parties[1])
            if gauche and droite:
                m = Morpheme(gauche, eid, sid, glose, cat, "circonfixe")
                liste = self.circonfixes.setdefault(gauche, [])
                if all(x[1].entree_id != eid or x[0] != droite for x in liste):
                    liste.append((droite, m))

    def environnement(self, texte):
        if texte not in self._environnements:
            self._environnements[texte] = Environnement(texte, self.classes)
        return self._environnements[texte]

    def _respecte_environnements(self, mot, decomposition, longueur=len):
        position = 0
        for m in decomposition.morphemes:
            fin = position + longueur(m.forme)
            if m.environnement and not self.environnement(m.environnement).accepte(mot[:position], mot[fin:]):
                return False
            position = fin
        return True

    def analyser(self, mot):
        """Toutes les décompositions du mot, les plus simples d'abord."""
        mot = _nettoyer(mot)
        resultats = self._analyser(mot) + self._redoublements(mot) + self._redoublements_partiels(mot)
        if self.sans_tons and not resultats:   # seulement pour un mot sans aucune analyse exacte
            resultats = self._approchees(mot)
        uniques = {}
        for d in resultats:
            uniques.setdefault(tuple((m.forme, m.entree_id, m.role) for m in d.morphemes), d)
        return sorted(uniques.values(), key=Decomposition.cle)[:MAX_RESULTATS]

    def _approchees(self, mot):
        """Décompositions trouvées sans les signes combinants, remises dans la forme écrite du mot."""
        decompose = unicodedata.normalize("NFD", mot)
        # position, dans le mot décomposé, de chaque lettre du mot sans signes
        positions = [i for i, c in enumerate(decompose) if not unicodedata.combining(c)]
        nu = "".join(decompose[i] for i in positions)
        resultats = []
        for d in self._analyser(nu, self.formes_st, self.longueurs_st, lambda f: len(_sans_signes(f)),
                                self.circonfixes_st):
            morphemes, debut = [], 0
            for m in d.morphemes:
                fin = debut + len(_sans_signes(m.forme))
                a = positions[debut]
                b = positions[fin] if fin < len(positions) else len(decompose)   # signes de la dernière lettre inclus
                forme = unicodedata.normalize("NFC", decompose[a:b])
                morphemes.append(Morpheme(forme, m.entree_id, m.sens_id, m.glose, m.categorie, m.role,
                                          m.environnement, m.suite))
                debut = fin
            resultats.append(Decomposition(morphemes, approchee=True))
        return resultats

    def _redoublements_partiels(self, mot):
        """« ba-bal » : copie consonne(s) + voyelle(s) du début d'un radical déclaré, placée devant lui.
        Seulement si la classe des voyelles « V » est déclarée dans le projet."""
        voyelles = {_sans_tons(v) for v in self.classes.get("V", [])}
        if not voyelles:
            return []
        resultats = []
        for i in range(2, len(mot) - 1):
            if unicodedata.combining(mot[i]):
                continue
            copie = mot[:i]
            reste = mot[i + 1:] if mot[i] == "-" else mot[i:]
            lettres = _sans_tons(copie)
            if not lettres or "-" in copie:
                continue
            # forme C…CV…V : au moins une consonne d'abord, au moins une voyelle à la fin
            j = 0
            while j < len(lettres) and lettres[j] not in voyelles:
                j += 1
            if j == 0 or j == len(lettres) or any(c not in voyelles for c in lettres[j:]):
                continue
            for d in self._analyser(reste)[:5]:
                r = d.morphemes[0]
                if r.role != "radical" or len(_sans_tons(r.forme)) <= len(lettres)                         or not _sans_tons(r.forme).startswith(lettres):
                    continue
                red = Morpheme(copie, r.entree_id, r.sens_id, "RED", "", "redoublement")
                resultats.append(Decomposition([red] + d.morphemes))
        return resultats

    def _redoublements(self, mot):
        """« tɔ̄l-tɔ̄l » = base « tɔ̄l » (analysée) + copie « RED » ; tons de la copie libres."""
        resultats = []
        for i in range(2, len(mot) - 1):
            for separateur in ("-", ""):
                base, copie = mot[:i], mot[i + len(separateur):]
                if not mot[i:].startswith(separateur) or len(copie) < 2 or "-" in base or copie.startswith("-"):
                    continue
                if unicodedata.combining(mot[i]):   # jamais entre une lettre et ses accents
                    continue
                if _sans_tons(base) != _sans_tons(copie):
                    continue
                for d in self._analyser(base)[:5]:
                    radical = next((m for m in d.morphemes if m.role == "radical"), d.morphemes[0])
                    red = Morpheme(copie, radical.entree_id, radical.sens_id, "RED", "", "redoublement")
                    resultats.append(Decomposition(d.morphemes + [red]))
        return resultats

    def _analyser(self, mot, formes=None, longueurs=None, longueur=len, circonfixes=None):
        formes = formes or self.formes
        longueurs = longueurs or self.longueurs
        circonfixes = self.circonfixes if circonfixes is None else circonfixes
        resultats = []

        def prefixes(debut, pris):
            # radical à partir de « debut »
            radical(debut, pris)
            if len([m for m in pris if m.role == "avant"]) >= MAX_AFFIXES:
                return
            for n in longueurs["avant"]:
                if debut + n < len(mot):  # un préfixe ne peut pas être le mot entier
                    for m in formes["avant"].get(mot[debut:debut + n], []):
                        prefixes(debut + n, pris + [m])

        def radical(debut, pris):
            for n in longueurs["radical"]:
                if debut + n <= len(mot):
                    for m in formes["radical"].get(mot[debut:debut + n], []):
                        suffixes(debut + n, pris + [m], 0)
            avec_infixe(debut, pris)
            avec_circonfixe(debut, pris)

        def avec_circonfixe(debut, pris):
            # ka + radical déclaré + ŋ : les deux parties entourent directement le radical
            for gauche, liste in circonfixes.items():
                if not mot.startswith(gauche, debut):
                    continue
                milieu = debut + len(gauche)
                for droite, c in liste:
                    for n in longueurs["radical"]:
                        fin = milieu + n
                        if fin + len(droite) <= len(mot) and mot.startswith(droite, fin):
                            for r in formes["radical"].get(mot[milieu:fin], []):
                                fin_c = Morpheme(mot[fin:fin + len(droite)], c.entree_id, c.sens_id, c.glose,
                                                 c.categorie, "circonfixe", suite=True)
                                debut_c = Morpheme(mot[debut:milieu], c.entree_id, c.sens_id, c.glose, c.categorie,
                                                   "circonfixe")
                                suffixes(fin + len(droite), pris + [debut_c, r, fin_c], 0)

        def avec_infixe(debut, pris):
            # radical déclaré coupé par un infixe déclaré, jamais en bordure : k‹ar›tab
            for forme_inf, infixes in formes["infixe"].items():
                k = len(forme_inf)
                position = mot.find(forme_inf, debut + 1)
                while position != -1:
                    if unicodedata.combining(mot[position]) or (position + k < len(mot)
                                                               and unicodedata.combining(mot[position + k])):
                        position = mot.find(forme_inf, position + 1)   # jamais entre une lettre et ses accents
                        continue
                    for fin in range(position + k + 1, len(mot) + 1):
                        base = mot[debut:position] + mot[position + k:fin]
                        for r in formes["radical"].get(base, []):
                            avant_inf = Morpheme(mot[debut:position], r.entree_id, r.sens_id, r.glose, r.categorie,
                                                 "radical")
                            apres_inf = Morpheme(mot[position + k:fin], r.entree_id, r.sens_id, r.glose,
                                                 r.categorie, "radical", suite=True)
                            for inf in infixes:
                                suffixes(fin, pris + [avant_inf, inf, apres_inf], 0)
                    position = mot.find(forme_inf, position + 1)

        def suffixes(debut, pris, compte):
            if len(resultats) >= MAX_RESULTATS * 4:
                return
            if debut == len(mot):
                resultats.append(Decomposition(list(pris)))
                return
            if compte >= MAX_AFFIXES:
                return
            for n in longueurs["apres"]:
                if debut + n <= len(mot):
                    for m in formes["apres"].get(mot[debut:debut + n], []):
                        suffixes(debut + n, pris + [m], compte + 1)

        prefixes(0, [])
        # un allomorphe ou un infixe dont l'environnement (formel) n'est pas respecté est écarté
        return [d for d in resultats if self._respecte_environnements(mot, d, longueur)]

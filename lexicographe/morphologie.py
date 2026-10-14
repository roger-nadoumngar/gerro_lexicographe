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

Limites assumées : les infixes et circonfixes ne sont pas encore pris en charge.
"""

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
    role: str                  # « avant », « radical », « après »
    environnement: str = ""    # condition d'un allomorphe (affichée, pas encore appliquée)


@dataclass
class Decomposition:
    morphemes: list[Morpheme] = field(default_factory=list)

    @property
    def segmentation(self):
        """« ka-kó-je » : formes séparées par des tirets."""
        return "-".join(m.forme for m in self.morphemes)

    @property
    def gloses(self):
        return "-".join(m.glose or "?" for m in self.morphemes)

    def cle(self):
        # les plus simples d'abord : moins de morphèmes, puis moins d'affixes
        return (len(self.morphemes), sum(m.role != "radical" for m in self.morphemes), self.segmentation)


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
        self.formes = {"avant": {}, "radical": {}, "apres": {}}
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
            elif type_morph in NON_RADICAUX:
                continue  # infixes et circonfixes : pas encore pris en charge
            else:
                roles = ["radical"]
            variantes = [(forme, ""), (citation, "")] + allomorphes.get(eid, [])
            for f, env in variantes:
                f = _nettoyer(f or "")
                if not f:
                    continue
                for role in roles:
                    m = Morpheme(f, eid, sid, glose, cat, "radical" if role == "radical" else role, env)
                    liste = self.formes[role].setdefault(f, [])
                    if all(x.entree_id != eid for x in liste):
                        liste.append(m)
        self.longueurs = {role: sorted({len(f) for f in d}, reverse=True) for role, d in self.formes.items()}
        ligne = conn.execute("SELECT valeur FROM projet WHERE cle='classes_phonologiques'").fetchone()
        self.classes = lire_classes(ligne[0] if ligne else "")
        self._environnements = {}

    def environnement(self, texte):
        if texte not in self._environnements:
            self._environnements[texte] = Environnement(texte, self.classes)
        return self._environnements[texte]

    def _respecte_environnements(self, mot, decomposition):
        position = 0
        for m in decomposition.morphemes:
            fin = position + len(m.forme)
            if m.environnement and not self.environnement(m.environnement).accepte(mot[:position], mot[fin:]):
                return False
            position = fin
        return True

    def analyser(self, mot):
        """Toutes les décompositions du mot, les plus simples d'abord."""
        mot = _nettoyer(mot)
        resultats = []

        def prefixes(debut, pris):
            # radical à partir de « debut »
            radical(debut, pris)
            if len([m for m in pris if m.role == "avant"]) >= MAX_AFFIXES:
                return
            for n in self.longueurs["avant"]:
                if debut + n < len(mot):  # un préfixe ne peut pas être le mot entier
                    for m in self.formes["avant"].get(mot[debut:debut + n], []):
                        prefixes(debut + n, pris + [m])

        def radical(debut, pris):
            for n in self.longueurs["radical"]:
                if debut + n <= len(mot):
                    for m in self.formes["radical"].get(mot[debut:debut + n], []):
                        suffixes(debut + n, pris + [m], 0)

        def suffixes(debut, pris, compte):
            if len(resultats) >= MAX_RESULTATS * 4:
                return
            if debut == len(mot):
                resultats.append(Decomposition(list(pris)))
                return
            if compte >= MAX_AFFIXES:
                return
            for n in self.longueurs["apres"]:
                if debut + n <= len(mot):
                    for m in self.formes["apres"].get(mot[debut:debut + n], []):
                        suffixes(debut + n, pris + [m], compte + 1)

        prefixes(0, [])
        # un allomorphe dont l'environnement (formel) n'est pas respecté est écarté
        resultats = [d for d in resultats if self._respecte_environnements(mot, d)]
        uniques = {}
        for d in resultats:
            uniques.setdefault(tuple((m.forme, m.entree_id) for m in d.morphemes), d)
        return sorted(uniques.values(), key=Decomposition.cle)[:MAX_RESULTATS]

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

Limites assumées : les infixes, circonfixes et les conditions d'environnement
des allomorphes ne sont pas encore appliqués (l'environnement est affiché).
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
        uniques = {}
        for d in resultats:
            uniques.setdefault(tuple((m.forme, m.entree_id) for m in d.morphemes), d)
        return sorted(uniques.values(), key=Decomposition.cle)[:MAX_RESULTATS]

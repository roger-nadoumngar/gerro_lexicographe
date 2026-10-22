"""Retirer le contenu venu d'une source (un dictionnaire imprimé importé, par exemple).

Les imports notent leur source : la ligne « Source : <nom> » dans les notes des entrées créées, et
la référence <nom> sur chaque exemple ajouté. Règles :
- tous les exemples qui portent cette référence sont retirés ;
- une entrée dont la note porte « Source : <nom> » est supprimée si elle n'a pas d'autre origine ;
  elle est gardée (seule la ligne de source est retirée de ses notes) si elle a une autre origine :
  une autre ligne d'origine dans ses notes (glossaire ou termes Paratext, collecte…), une image ou un
  son, une analyse de texte validée, ou un exemple d'une autre source ;
- ce qui n'est pas marqué (entrées venues d'un projet FLEx, saisies à la main) n'est jamais touché.
Le résultat est d'abord calculé (`plan`), montré, puis appliqué (`appliquer`)."""

import re
from dataclasses import dataclass, field

from . import lexique

_ORIGINES = re.compile(r"^(Glossaire Paratext|Rendu validé dans Paratext|Collecte|Source :)")


@dataclass
class Plan:
    source: str
    entrees_supprimees: list[int] = field(default_factory=list)
    entrees_gardees: list[int] = field(default_factory=list)     # gardées, la ligne de source retirée
    exemples: list[int] = field(default_factory=list)

    def resume(self, conn):
        def formes(ids):
            return ", ".join(r[0] for r in conn.execute(
                f"SELECT forme FROM entrees WHERE id IN ({','.join('?' * len(ids[:12]))})", ids[:12]))
        return (f"{len(self.exemples)} exemple(s) retiré(s) ; {len(self.entrees_supprimees)} entrée(s) supprimée(s)"
                f"{' (' + formes(self.entrees_supprimees) + '…)' if self.entrees_supprimees else ''} ; "
                f"{len(self.entrees_gardees)} entrée(s) gardée(s) car elles ont une autre origine"
                f"{' (' + formes(self.entrees_gardees) + '…)' if self.entrees_gardees else ''}.")


def lister(conn):
    """{source: (entrées marquées, exemples marqués)}."""
    sources = {}
    for (notes,) in conn.execute("SELECT notes FROM entrees WHERE notes LIKE '%Source : %'"):
        for ligne in notes.splitlines():
            if ligne.startswith("Source : "):
                nom = ligne[len("Source : "):].strip()
                e, x = sources.get(nom, (0, 0))
                sources[nom] = (e + 1, x)
    for nom, n in conn.execute("SELECT reference, COUNT(*) FROM exemples WHERE reference IS NOT NULL "
                               "AND reference NOT GLOB '[A-Z0-9][A-Z0-9][A-Z0-9] [0-9]*' GROUP BY reference"):
        e, x = sources.get(nom, (0, 0))
        sources[nom] = (e, x + n)
    return dict(sorted(sources.items(), key=lambda s: -sum(s[1])))


def plan(conn, source):
    p = Plan(source)
    ligne_source = f"Source : {source}"
    p.exemples = [r[0] for r in conn.execute("SELECT id FROM exemples WHERE reference=?", (source,))]
    retires = set(p.exemples)
    avec_media = {r[0] for r in conn.execute("SELECT DISTINCT entree_id FROM medias_liens")}
    analysees = {r[0] for r in conn.execute("SELECT DISTINCT entree_id FROM analyse_morphemes "
                                            "WHERE entree_id IS NOT NULL")}
    for eid, notes in conn.execute("SELECT id, notes FROM entrees WHERE notes LIKE ?", (f"%{ligne_source}%",)):
        lignes = [l for l in notes.splitlines() if l.strip()]
        if ligne_source not in lignes:
            continue
        autres_origines = [l for l in lignes if _ORIGINES.match(l) and l != ligne_source]
        autres_exemples = conn.execute(
            "SELECT x.id FROM exemples x JOIN sens s ON s.id = x.sens_id WHERE s.entree_id=?", (eid,)).fetchall()
        autres_exemples = [r[0] for r in autres_exemples if r[0] not in retires]
        if autres_origines or eid in avec_media or eid in analysees or autres_exemples:
            p.entrees_gardees.append(eid)
        else:
            p.entrees_supprimees.append(eid)
    return p


def appliquer(conn, p):
    ligne_source = f"Source : {p.source}"
    with conn:
        conn.executemany("DELETE FROM exemples WHERE id=?", [(i,) for i in p.exemples])
        for eid in p.entrees_gardees:
            notes = conn.execute("SELECT notes FROM entrees WHERE id=?", (eid,)).fetchone()[0] or ""
            reste = "\n".join(l for l in notes.splitlines() if l != ligne_source)
            conn.execute("UPDATE entrees SET notes=?, date_modification=? WHERE id=?",
                         (reste or None, lexique._maintenant(), eid))
    for eid in p.entrees_supprimees:
        lexique.supprimer_entree(conn, eid)
    return p

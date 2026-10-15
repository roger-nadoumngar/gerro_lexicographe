"""Doublons du lexique : repérage et fusion.

Règles :
- deux entrées sont des doublons possibles si elles ont la même forme (majuscules et forme de
  citation ignorées), le même type (mot / radical comptent ensemble) et au moins une glose commune
  (même glose, ou l'une est le début de l'autre). Même forme sans glose commune : ce sont des
  homographes, jamais proposés ;
- la fusion garde une entrée et y reporte tout ce qu'a l'autre : un sens dont la glose concorde
  reçoit les exemples, domaines, médias et analyses du sens retiré (sans doublons), les autres sens
  sont déplacés ; variantes, propriétés, médias, relations, composants, analyses interlinéaires et
  hypothèses passent sur l'entrée gardée ; la prononciation et la forme de citation manquantes sont
  reprises, les notes réunies, et le statut le plus avancé est gardé. Rien n'est perdu."""

from dataclasses import dataclass, field

from . import lexique
from .dico_imprime import cle_glose, gloses_concordent
from .texte import normaliser

RANG_STATUT = {"brouillon": 0, "à vérifier": 1, "validé": 2}
_MOTS = {"", "stem", "root", None}


@dataclass
class Groupe:
    forme: str
    entrees: list[int]
    gloses_communes: list[str] = field(default_factory=list)


def _cle_forme(forme):
    return normaliser(forme or "").strip().lower()


def _type(type_morph):
    return "mot" if type_morph in _MOTS else type_morph


def candidats(conn):
    """Groupes de doublons possibles, dans l'ordre alphabétique des formes."""
    par_cle = {}
    for eid, forme, type_morph in conn.execute("SELECT id, forme, type_morph FROM entrees ORDER BY id"):
        par_cle.setdefault((_cle_forme(forme), _type(type_morph)), []).append(eid)
    gloses = {}
    for eid, glose in conn.execute("SELECT entree_id, glose FROM sens"):
        if (glose or "").strip():
            gloses.setdefault(eid, []).append(glose)
    groupes = []
    for (forme, _), ids in par_cle.items():
        if len(ids) < 2:
            continue
        # composantes reliées par « au moins une glose commune »
        restants = list(ids)
        while restants:
            groupe = [restants.pop(0)]
            communes = set()
            change = True
            while change:
                change = False
                for autre in list(restants):
                    paires = [(g1, g2) for e in groupe for g1 in gloses.get(e, []) for g2 in gloses.get(autre, [])
                              if gloses_concordent(g1, g2)]
                    if paires:
                        groupe.append(autre)
                        restants.remove(autre)
                        communes.update(cle_glose(min(p, key=len)) for p in paires)
                        change = True
            if len(groupe) > 1:
                groupes.append(Groupe(forme, groupe, sorted(communes)))
    ordre = lexique.ordre_du_projet(conn)
    groupes.sort(key=lambda g: ordre.cle(g.forme))
    return groupes


def plus_complete(conn, ids):
    """L'entrée à garder par défaut : le plus d'exemples, puis de sens, puis le statut le plus avancé,
    puis la plus ancienne."""
    def poids(eid):
        e = lexique.lire_entree(conn, eid)
        return (sum(len(s.exemples) for s in e.sens), len(e.sens), RANG_STATUT.get(e.statut, 0), -eid)
    return max(ids, key=poids)


def fusionner(conn, garder_id, retirer_id):
    """Reporte tout de `retirer_id` sur `garder_id`, puis supprime `retirer_id`."""
    if garder_id == retirer_id:
        raise ValueError("Une entrée ne peut pas être fusionnée avec elle-même.")
    garder = lexique.lire_entree(conn, garder_id)
    retirer = lexique.lire_entree(conn, retirer_id)
    if garder is None or retirer is None:
        raise ValueError("Entrée introuvable.")
    with conn:
        # 1. sens : concordants réunis, les autres déplacés
        ordre = max((s_ordre for (s_ordre,) in conn.execute("SELECT ordre FROM sens WHERE entree_id=?",
                                                            (garder_id,))), default=0)
        for s in retirer.sens:
            cible = next((g for g in garder.sens if s.glose and g.glose and gloses_concordent(g.glose, s.glose)),
                         None)
            if cible is None:
                ordre += 1
                conn.execute("UPDATE sens SET entree_id=?, ordre=? WHERE id=?", (garder_id, ordre, s.id))
                continue
            deja = {normaliser(x.vernaculaire).strip() for x in cible.exemples}
            for x in s.exemples:
                if normaliser(x.vernaculaire).strip() not in deja:
                    conn.execute("UPDATE exemples SET sens_id=? WHERE id=?", (cible.id, x.id))
                    deja.add(normaliser(x.vernaculaire).strip())
            conn.execute("INSERT OR IGNORE INTO sens_domaines (sens_id, domaine_guid) "
                         "SELECT ?, domaine_guid FROM sens_domaines WHERE sens_id=?", (cible.id, s.id))
            for table in ("medias_liens", "analyse_morphemes"):
                conn.execute(f"UPDATE {table} SET sens_id=? WHERE sens_id=?", (cible.id, s.id))
            if not cible.definition and s.definition:
                conn.execute("UPDATE sens SET definition=? WHERE id=?", (s.definition, cible.id))
            if cible.categorie_id is None and s.categorie_id is not None:
                conn.execute("UPDATE sens SET categorie_id=? WHERE id=?", (s.categorie_id, cible.id))
            if len(s.glose) > len(cible.glose) and cle_glose(s.glose).startswith(cle_glose(cible.glose)):
                conn.execute("UPDATE sens SET glose=? WHERE id=?", (s.glose, cible.id))   # glose plus complète
            conn.execute("DELETE FROM sens WHERE id=?", (s.id,))

        # 2. ce qui dépend de l'entrée
        for table in ("variantes", "medias_liens", "analyse_morphemes", "hypotheses"):
            conn.execute(f"UPDATE {table} SET entree_id=? WHERE entree_id=?", (garder_id, retirer_id))
        conn.execute("INSERT OR IGNORE INTO proprietes (entree_id, nom, valeur) "
                     "SELECT ?, nom, valeur FROM proprietes WHERE entree_id=? AND nom NOT IN "
                     "(SELECT nom FROM proprietes WHERE entree_id=?)", (garder_id, retirer_id, garder_id))
        for source, cible, typ in conn.execute("SELECT source_id, cible_id, type FROM relations "
                                               "WHERE source_id=? OR cible_id=?", (retirer_id, retirer_id)).fetchall():
            source = garder_id if source == retirer_id else source
            cible = garder_id if cible == retirer_id else cible
            if source != cible:
                conn.execute("INSERT OR IGNORE INTO relations (source_id, cible_id, type) VALUES (?, ?, ?)",
                             (source, cible, typ))
        for entree, composant, rang in conn.execute("SELECT entree_id, composant_id, ordre FROM composants "
                                                    "WHERE entree_id=? OR composant_id=?",
                                                    (retirer_id, retirer_id)).fetchall():
            entree = garder_id if entree == retirer_id else entree
            composant = garder_id if composant == retirer_id else composant
            if entree != composant and not conn.execute("SELECT 1 FROM composants WHERE entree_id=? AND "
                                                        "composant_id=?", (entree, composant)).fetchone():
                conn.execute("INSERT INTO composants (entree_id, composant_id, ordre) VALUES (?, ?, ?)",
                             (entree, composant, rang))

        # 3. champs de l'entrée
        notes = list(dict.fromkeys(l for l in (garder.notes + "\n" + retirer.notes).splitlines() if l.strip()))
        statut = max((garder.statut, retirer.statut), key=lambda s: RANG_STATUT.get(s, 0))
        conn.execute("""UPDATE entrees SET prononciation=COALESCE(NULLIF(prononciation, ''), ?),
                        forme_citation=COALESCE(NULLIF(forme_citation, ''), ?), notes=?, statut=?,
                        date_modification=? WHERE id=?""",
                     (retirer.prononciation or None, retirer.forme_citation or None, "\n".join(notes) or None,
                      statut, lexique._maintenant(), garder_id))
        conn.execute("DELETE FROM entrees WHERE id=?", (retirer_id,))
    return garder_id


def fusionner_groupe(conn, groupe, garder_id=None):
    garder_id = garder_id or plus_complete(conn, groupe.entrees)
    for eid in groupe.entrees:
        if eid != garder_id:
            fusionner(conn, garder_id, eid)
    return garder_id

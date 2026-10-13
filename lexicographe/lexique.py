"""Lexique : entrées, sens, exemples, relations, propriétés, catégories.

Modèle inspiré de FLEx : une entrée (forme vernaculaire) porte un ou
plusieurs sens ; chaque sens a sa glose, sa définition, sa catégorie
grammaticale, son domaine sémantique et ses exemples.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from .texte import normaliser

TYPES_RELATIONS = [
    "synonyme", "antonyme", "terme générique (hyperonyme)", "terme spécifique (hyponyme)",
    "partie de (méronyme)", "même champ lexical", "voir aussi",
]


@dataclass
class Exemple:
    vernaculaire: str = ""
    traduction: str = ""
    reference: str = ""
    id: int | None = None


@dataclass
class Sens:
    glose: str = ""
    definition: str = ""
    categorie_id: int | None = None
    domaine: str = ""
    exemples: list[Exemple] = field(default_factory=list)
    id: int | None = None


@dataclass
class Entree:
    forme: str = ""
    notes: str = ""
    sens: list[Sens] = field(default_factory=list)
    proprietes: dict[str, str] = field(default_factory=dict)
    id: int | None = None
    guid: str = ""
    date_creation: str = ""
    date_modification: str = ""


def _maintenant():
    return datetime.now().isoformat(timespec="seconds")


def _vide(valeur):
    valeur = (valeur or "").strip()
    return valeur or None


# -- catégories ------------------------------------------------------------------

def categories(conn):
    """[(id, nom, abreviation, parent_id)] triées par nom."""
    return conn.execute("SELECT id, nom, abreviation, parent_id FROM categories ORDER BY nom").fetchall()


def ajouter_categorie(conn, nom, abreviation="", parent_id=None):
    nom = normaliser(nom).strip()
    if not nom:
        raise ValueError("Le nom de la catégorie est vide.")
    with conn:
        cur = conn.execute("INSERT INTO categories (nom, abreviation, parent_id) VALUES (?, ?, ?)",
                           (nom, _vide(abreviation), parent_id))
    return cur.lastrowid


def renommer_categorie(conn, categorie_id, nom, abreviation=""):
    with conn:
        conn.execute("UPDATE categories SET nom=?, abreviation=? WHERE id=?",
                     (normaliser(nom).strip(), _vide(abreviation), categorie_id))


def supprimer_categorie(conn, categorie_id):
    """Les sens qui l'utilisaient restent, sans catégorie."""
    with conn:
        conn.execute("DELETE FROM categories WHERE id=?", (categorie_id,))


def nom_categorie(conn, categorie_id):
    if categorie_id is None:
        return ""
    ligne = conn.execute("SELECT nom FROM categories WHERE id=?", (categorie_id,)).fetchone()
    return ligne[0] if ligne else ""


# -- entrées ---------------------------------------------------------------------

def lire_entree(conn, entree_id):
    ligne = conn.execute("""SELECT id, guid, forme, notes, date_creation, date_modification
                            FROM entrees WHERE id=?""", (entree_id,)).fetchone()
    if not ligne:
        return None
    entree = Entree(id=ligne[0], guid=ligne[1], forme=ligne[2], notes=ligne[3] or "",
                    date_creation=ligne[4] or "", date_modification=ligne[5] or "")
    for sid, glose, definition, cat, domaine in conn.execute(
            """SELECT id, glose, definition, categorie_id, domaine FROM sens
               WHERE entree_id=? ORDER BY ordre, id""", (entree_id,)).fetchall():
        sens = Sens(id=sid, glose=glose or "", definition=definition or "", categorie_id=cat,
                    domaine=domaine or "")
        sens.exemples = [Exemple(id=e[0], vernaculaire=e[1] or "", traduction=e[2] or "", reference=e[3] or "")
                         for e in conn.execute("""SELECT id, vernaculaire, traduction, reference
                                                  FROM exemples WHERE sens_id=? ORDER BY id""", (sid,))]
        entree.sens.append(sens)
    entree.proprietes = dict(conn.execute(
        "SELECT nom, valeur FROM proprietes WHERE entree_id=? ORDER BY nom", (entree_id,)).fetchall())
    return entree


def enregistrer_entree(conn, entree):
    """Crée ou met à jour l'entrée avec tous ses sens et exemples. Retourne son id."""
    forme = normaliser(entree.forme).strip()
    if not forme:
        raise ValueError("La forme de l'entrée est vide.")
    maintenant = _maintenant()
    with conn:
        if entree.id is None:
            entree.guid = entree.guid or str(uuid.uuid4())
            entree.date_creation = entree.date_creation or maintenant
            entree.id = conn.execute(
                """INSERT INTO entrees (guid, forme, notes, date_creation, date_modification)
                   VALUES (?, ?, ?, ?, ?)""",
                (entree.guid, forme, _vide(entree.notes), entree.date_creation, maintenant)).lastrowid
        else:
            conn.execute("UPDATE entrees SET forme=?, notes=?, date_modification=? WHERE id=?",
                         (forme, _vide(entree.notes), maintenant, entree.id))
        entree.forme = forme
        entree.date_modification = maintenant

        gardes = [s.id for s in entree.sens if s.id is not None]
        anciens = [r[0] for r in conn.execute("SELECT id FROM sens WHERE entree_id=?", (entree.id,))]
        for sid in anciens:
            if sid not in gardes:
                conn.execute("DELETE FROM sens WHERE id=?", (sid,))
        for ordre, sens in enumerate(entree.sens, start=1):
            valeurs = (_vide(normaliser(sens.glose)), _vide(normaliser(sens.definition)),
                       sens.categorie_id, _vide(sens.domaine))
            if sens.id is None:
                sens.id = conn.execute(
                    """INSERT INTO sens (entree_id, ordre, glose, definition, categorie_id, domaine)
                       VALUES (?, ?, ?, ?, ?, ?)""", (entree.id, ordre) + valeurs).lastrowid
            else:
                conn.execute("""UPDATE sens SET ordre=?, glose=?, definition=?, categorie_id=?, domaine=?
                                WHERE id=? AND entree_id=?""", (ordre,) + valeurs + (sens.id, entree.id))
            conn.execute("DELETE FROM exemples WHERE sens_id=?", (sens.id,))
            for ex in sens.exemples:
                if not (ex.vernaculaire.strip() or ex.traduction.strip()):
                    continue
                ex.id = conn.execute(
                    "INSERT INTO exemples (sens_id, vernaculaire, traduction, reference) VALUES (?, ?, ?, ?)",
                    (sens.id, _vide(normaliser(ex.vernaculaire)), _vide(normaliser(ex.traduction)),
                     _vide(ex.reference))).lastrowid

        conn.execute("DELETE FROM proprietes WHERE entree_id=?", (entree.id,))
        conn.executemany("INSERT INTO proprietes (entree_id, nom, valeur) VALUES (?, ?, ?)",
                         [(entree.id, n.strip(), v) for n, v in entree.proprietes.items() if n.strip() and v])
    return entree.id


def supprimer_entree(conn, entree_id):
    with conn:
        conn.execute("UPDATE hypotheses SET statut='en_attente', entree_id=NULL, date_decision=NULL "
                     "WHERE entree_id=?", (entree_id,))
        conn.execute("DELETE FROM entrees WHERE id=?", (entree_id,))


def lister_entrees(conn, recherche=""):
    """[(id, forme, gloses, catégories, domaines)] triées par forme ; la recherche
    porte sur la forme et les gloses."""
    lignes = conn.execute("""
        SELECT e.id, e.forme,
               GROUP_CONCAT(COALESCE(s.glose, ''), ' ; '),
               GROUP_CONCAT(COALESCE(c.nom, ''), ' ; '),
               GROUP_CONCAT(COALESCE(s.domaine, ''), ' ; ')
        FROM entrees e
        LEFT JOIN sens s ON s.entree_id = e.id
        LEFT JOIN categories c ON c.id = s.categorie_id
        GROUP BY e.id
        ORDER BY e.forme COLLATE NOCASE, e.id""").fetchall()
    recherche = normaliser(recherche).strip().lower()
    resultat = []
    for eid, forme, gloses, cats, domaines in lignes:
        gloses = _nettoyer_liste(gloses)
        if recherche and recherche not in forme.lower() and recherche not in gloses.lower():
            continue
        resultat.append((eid, forme, gloses, _nettoyer_liste(cats), _nettoyer_liste(domaines)))
    return resultat


def _nettoyer_liste(texte):
    vus = []
    for morceau in (texte or "").split(" ; "):
        if morceau and morceau not in vus:
            vus.append(morceau)
    return " ; ".join(vus)


def chercher_par_forme(conn, forme):
    return [r[0] for r in conn.execute("SELECT id FROM entrees WHERE forme=? ORDER BY id",
                                       (normaliser(forme).strip(),))]


# -- relations -------------------------------------------------------------------

def relations(conn, entree_id):
    """[(id, type, cible_id, forme cible)]"""
    return conn.execute("""SELECT r.id, r.type, r.cible_id, e.forme FROM relations r
                           JOIN entrees e ON e.id = r.cible_id
                           WHERE r.source_id=? ORDER BY r.type, e.forme""", (entree_id,)).fetchall()


def ajouter_relation(conn, source_id, cible_id, type_relation):
    """Retourne False si la relation existait déjà."""
    if source_id == cible_id:
        raise ValueError("Une entrée ne peut pas être reliée à elle-même.")
    with conn:
        cur = conn.execute("INSERT OR IGNORE INTO relations (source_id, cible_id, type) VALUES (?, ?, ?)",
                           (source_id, cible_id, type_relation))
    return cur.rowcount == 1


def supprimer_relation(conn, relation_id):
    with conn:
        conn.execute("DELETE FROM relations WHERE id=?", (relation_id,))


# -- statistiques ----------------------------------------------------------------

def statistiques(conn):
    def compter(sql):
        return conn.execute(sql).fetchone()[0]
    return {
        "phrases": compter("SELECT COUNT(*) FROM phrases"),
        "phrases_paralleles": compter("SELECT COUNT(*) FROM phrases WHERE vernaculaire IS NOT NULL "
                                      "AND analyse IS NOT NULL"),
        "entrees": compter("SELECT COUNT(*) FROM entrees"),
        "sens": compter("SELECT COUNT(*) FROM sens"),
        "en_attente": compter("SELECT COUNT(*) FROM hypotheses WHERE statut='en_attente'"),
        "rejetees": compter("SELECT COUNT(*) FROM hypotheses WHERE statut='rejete'"),
    }

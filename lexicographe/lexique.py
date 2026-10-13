"""Lexique : entrées, sens, exemples, variantes, composants, relations,
propriétés, catégories.

Modèle inspiré de FLEx : une entrée (forme vernaculaire) a une forme de
citation, une prononciation, un type morphologique, des variantes et
allomorphes, éventuellement des composants (forme complexe), et un ou
plusieurs sens ; chaque sens a sa glose, ses formes d'index inverse, sa
définition, sa catégorie, ses domaines sémantiques et ses exemples.
"""

import re
import uuid
from collections import namedtuple
from dataclasses import dataclass, field
from datetime import datetime

from .texte import OrdreAlphabetique, normaliser

TYPES_RELATIONS = [
    "synonyme", "antonyme", "terme générique (hyperonyme)", "terme spécifique (hyponyme)",
    "partie de (méronyme)", "même champ lexical", "voir aussi",
]

# types morphologiques : clé = nom FLEx (exports LIFT), valeur = libellé affiché
TYPES_MORPH = {
    "stem": "radical", "root": "racine", "bound root": "racine liée", "bound stem": "radical lié",
    "prefix": "préfixe", "suffix": "suffixe", "infix": "infixe", "circumfix": "circonfixe",
    "clitic": "clitique", "proclitic": "proclitique", "enclitic": "enclitique",
    "particle": "particule", "phrase": "locution", "discontiguous phrase": "locution discontinue",
}

STATUTS = ["brouillon", "à vérifier", "validé"]

TYPES_VARIANTES = ["variante libre", "variante dialectale", "variante orthographique", "forme irrégulière",
                   "allomorphe"]

TYPES_FORMES_COMPLEXES = ["composé", "dérivé", "redoublement", "expression idiomatique", "locution verbale",
                          "contraction"]


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
    domaine: str = ""            # étiquette libre des versions précédentes (à reclasser)
    inverse: str = ""            # formes de l'index inverse, séparées par « ; » (vide = la glose)
    domaines: list[str] = field(default_factory=list)   # guids des domaines sémantiques officiels
    exemples: list[Exemple] = field(default_factory=list)
    id: int | None = None


@dataclass
class Variante:
    forme: str = ""
    type: str = "variante libre"
    environnement: str = ""      # contexte d'apparition (surtout pour les allomorphes)
    note: str = ""
    id: int | None = None


@dataclass
class Entree:
    forme: str = ""
    forme_citation: str = ""
    prononciation: str = ""
    type_morph: str = ""
    statut: str = "brouillon"
    type_forme_complexe: str = ""
    composants: list[int] = field(default_factory=list)   # ids des entrées composantes, dans l'ordre
    notes: str = ""
    sens: list[Sens] = field(default_factory=list)
    variantes: list[Variante] = field(default_factory=list)
    proprietes: dict[str, str] = field(default_factory=dict)
    id: int | None = None
    guid: str = ""
    date_creation: str = ""
    date_modification: str = ""

    @property
    def tete(self):
        """Forme affichée en vedette : la forme de citation si elle existe."""
        return self.forme_citation or self.forme


def _maintenant():
    return datetime.now().isoformat(timespec="seconds")


def _vide(valeur):
    valeur = normaliser(valeur or "").strip()
    return valeur or None


def formes_inverses(sens):
    """Formes de l'index inverse d'un sens : le champ dédié, sinon la glose,
    découpés sur « ; » et « , »."""
    source = sens.inverse if isinstance(sens, Sens) else (sens or "")
    if isinstance(sens, Sens) and not source.strip():
        source = sens.glose
    return [m.strip() for m in re.split(r"[;,]", source or "") if m.strip()]


# -- catégories ------------------------------------------------------------------

def categories(conn):
    """[(id, nom, abreviation, parent_id)] triées par nom."""
    return conn.execute("SELECT id, nom, abreviation, parent_id FROM categories ORDER BY nom").fetchall()


def categories_arbre(conn):
    """[(id, nom, abreviation, profondeur)] : chaque catégorie suivie de ses sous-catégories."""
    toutes = categories(conn)
    enfants = {}
    for c in toutes:
        enfants.setdefault(c[3], []).append(c)
    resultat = []

    def parcourir(parent, profondeur, vus):
        for cid, nom, abrev, _ in enfants.get(parent, []):
            if cid in vus:
                continue
            resultat.append((cid, nom, abrev, profondeur))
            parcourir(cid, profondeur + 1, vus | {cid})

    parcourir(None, 0, frozenset())
    # catégories dont le parent n'existe plus
    places = {r[0] for r in resultat}
    resultat.extend((cid, nom, abrev, 0) for cid, nom, abrev, _ in toutes if cid not in places)
    return resultat


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


def deplacer_categorie(conn, categorie_id, parent_id):
    """Change le parent d'une catégorie (None = racine) ; refuse les cycles."""
    p = parent_id
    while p is not None:
        if p == categorie_id:
            raise ValueError("Une catégorie ne peut pas être placée sous elle-même.")
        ligne = conn.execute("SELECT parent_id FROM categories WHERE id=?", (p,)).fetchone()
        p = ligne[0] if ligne else None
    with conn:
        conn.execute("UPDATE categories SET parent_id=? WHERE id=?", (parent_id, categorie_id))


def supprimer_categorie(conn, categorie_id):
    """Les sens qui l'utilisaient restent, sans catégorie ; les sous-catégories remontent."""
    with conn:
        parent = conn.execute("SELECT parent_id FROM categories WHERE id=?", (categorie_id,)).fetchone()
        conn.execute("UPDATE categories SET parent_id=? WHERE parent_id=?",
                     (parent[0] if parent else None, categorie_id))
        conn.execute("DELETE FROM categories WHERE id=?", (categorie_id,))


def nom_categorie(conn, categorie_id):
    if categorie_id is None:
        return ""
    ligne = conn.execute("SELECT nom FROM categories WHERE id=?", (categorie_id,)).fetchone()
    return ligne[0] if ligne else ""


def categorie_par_nom(conn, nom, creer=False):
    nom = normaliser(nom).strip()
    if not nom:
        return None
    ligne = conn.execute("SELECT id FROM categories WHERE nom=?", (nom,)).fetchone()
    if ligne:
        return ligne[0]
    return ajouter_categorie(conn, nom) if creer else None


# -- entrées ---------------------------------------------------------------------

def lire_entree(conn, entree_id):
    ligne = conn.execute("""SELECT id, guid, forme, notes, date_creation, date_modification, forme_citation,
                                   prononciation, type_morph, statut, type_forme_complexe
                            FROM entrees WHERE id=?""", (entree_id,)).fetchone()
    if not ligne:
        return None
    entree = Entree(id=ligne[0], guid=ligne[1], forme=ligne[2], notes=ligne[3] or "",
                    date_creation=ligne[4] or "", date_modification=ligne[5] or "",
                    forme_citation=ligne[6] or "", prononciation=ligne[7] or "", type_morph=ligne[8] or "",
                    statut=ligne[9] or "brouillon", type_forme_complexe=ligne[10] or "")
    for sid, glose, definition, cat, domaine, inverse in conn.execute(
            """SELECT id, glose, definition, categorie_id, domaine, inverse FROM sens
               WHERE entree_id=? ORDER BY ordre, id""", (entree_id,)).fetchall():
        sens = Sens(id=sid, glose=glose or "", definition=definition or "", categorie_id=cat,
                    domaine=domaine or "", inverse=inverse or "")
        sens.exemples = [Exemple(id=e[0], vernaculaire=e[1] or "", traduction=e[2] or "", reference=e[3] or "")
                         for e in conn.execute("""SELECT id, vernaculaire, traduction, reference
                                                  FROM exemples WHERE sens_id=? ORDER BY id""", (sid,))]
        sens.domaines = [r[0] for r in conn.execute(
            """SELECT sd.domaine_guid FROM sens_domaines sd JOIN domaines d ON d.guid = sd.domaine_guid
               WHERE sd.sens_id=? ORDER BY d.code""", (sid,))]
        entree.sens.append(sens)
    entree.variantes = [Variante(id=v[0], forme=v[1], type=v[2], environnement=v[3] or "", note=v[4] or "")
                        for v in conn.execute("""SELECT id, forme, type, environnement, note FROM variantes
                                                 WHERE entree_id=? ORDER BY id""", (entree_id,))]
    entree.composants = [r[0] for r in conn.execute(
        "SELECT composant_id FROM composants WHERE entree_id=? ORDER BY ordre, id", (entree_id,))]
    entree.proprietes = dict(conn.execute(
        "SELECT nom, valeur FROM proprietes WHERE entree_id=? ORDER BY nom", (entree_id,)).fetchall())
    return entree


def enregistrer_entree(conn, entree):
    """Crée ou met à jour l'entrée et tout ce qui en dépend. Retourne son id."""
    forme = normaliser(entree.forme).strip()
    if not forme:
        raise ValueError("La forme de l'entrée est vide.")
    if entree.statut not in STATUTS:
        raise ValueError(f"Statut inconnu : {entree.statut}")
    if entree.id is not None and entree.id in entree.composants:
        raise ValueError("Une entrée ne peut pas être son propre composant.")
    maintenant = _maintenant()
    champs = (forme, _vide(entree.notes), _vide(entree.forme_citation), _vide(entree.prononciation),
              entree.type_morph or None, entree.statut, _vide(entree.type_forme_complexe))
    with conn:
        if entree.id is None:
            entree.guid = entree.guid or str(uuid.uuid4())
            entree.date_creation = entree.date_creation or maintenant
            entree.id = conn.execute(
                """INSERT INTO entrees (forme, notes, forme_citation, prononciation, type_morph, statut,
                                        type_forme_complexe, guid, date_creation, date_modification)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                champs + (entree.guid, entree.date_creation, maintenant)).lastrowid
        else:
            conn.execute("""UPDATE entrees SET forme=?, notes=?, forme_citation=?, prononciation=?, type_morph=?,
                                   statut=?, type_forme_complexe=?, date_modification=? WHERE id=?""",
                         champs + (maintenant, entree.id))
        entree.forme = forme
        entree.date_modification = maintenant

        gardes = {s.id for s in entree.sens if s.id is not None}
        for (sid,) in conn.execute("SELECT id FROM sens WHERE entree_id=?", (entree.id,)).fetchall():
            if sid not in gardes:
                conn.execute("DELETE FROM sens WHERE id=?", (sid,))
        for ordre, sens in enumerate(entree.sens, start=1):
            valeurs = (_vide(sens.glose), _vide(sens.definition), sens.categorie_id, _vide(sens.domaine),
                       _vide(sens.inverse))
            if sens.id is None:
                sens.id = conn.execute(
                    """INSERT INTO sens (entree_id, ordre, glose, definition, categorie_id, domaine, inverse)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""", (entree.id, ordre) + valeurs).lastrowid
            else:
                conn.execute("""UPDATE sens SET ordre=?, glose=?, definition=?, categorie_id=?, domaine=?,
                                inverse=? WHERE id=? AND entree_id=?""", (ordre,) + valeurs + (sens.id, entree.id))
            conn.execute("DELETE FROM exemples WHERE sens_id=?", (sens.id,))
            for ex in sens.exemples:
                if not (ex.vernaculaire.strip() or ex.traduction.strip()):
                    continue
                ex.id = conn.execute(
                    "INSERT INTO exemples (sens_id, vernaculaire, traduction, reference) VALUES (?, ?, ?, ?)",
                    (sens.id, _vide(ex.vernaculaire), _vide(ex.traduction), _vide(ex.reference))).lastrowid
            conn.execute("DELETE FROM sens_domaines WHERE sens_id=?", (sens.id,))
            conn.executemany("INSERT OR IGNORE INTO sens_domaines (sens_id, domaine_guid) VALUES (?, ?)",
                             [(sens.id, g) for g in dict.fromkeys(sens.domaines)])

        conn.execute("DELETE FROM variantes WHERE entree_id=?", (entree.id,))
        for v in entree.variantes:
            if v.forme.strip():
                v.id = conn.execute(
                    "INSERT INTO variantes (entree_id, forme, type, environnement, note) VALUES (?, ?, ?, ?, ?)",
                    (entree.id, normaliser(v.forme).strip(), v.type or "variante libre", _vide(v.environnement),
                     _vide(v.note))).lastrowid

        conn.execute("DELETE FROM composants WHERE entree_id=?", (entree.id,))
        conn.executemany("INSERT INTO composants (entree_id, composant_id, ordre) VALUES (?, ?, ?)",
                         [(entree.id, cid, i) for i, cid in enumerate(entree.composants, start=1)])

        conn.execute("DELETE FROM proprietes WHERE entree_id=?", (entree.id,))
        conn.executemany("INSERT INTO proprietes (entree_id, nom, valeur) VALUES (?, ?, ?)",
                         [(entree.id, n.strip(), v) for n, v in entree.proprietes.items() if n.strip() and v])
    return entree.id


def supprimer_entree(conn, entree_id):
    with conn:
        conn.execute("UPDATE hypotheses SET statut='en_attente', entree_id=NULL, date_decision=NULL "
                     "WHERE entree_id=?", (entree_id,))
        conn.execute("DELETE FROM entrees WHERE id=?", (entree_id,))


# -- listes, filtres, homographes ----------------------------------------------------

LigneEntree = namedtuple("LigneEntree", "id forme gloses categories domaines statut homographe tete type_morph")


def ordre_du_projet(conn):
    ligne = conn.execute("SELECT valeur FROM projet WHERE cle='alphabet_vern'").fetchone()
    return OrdreAlphabetique(ligne[0] if ligne else "")


def lister_entrees(conn, recherche="", statut=None, categorie_id=None, domaine_code=None, type_morph=None):
    """Entrées triées selon l'alphabet du projet, avec numéro d'homographe.
    La recherche porte sur la forme, la forme de citation, les variantes et les gloses ;
    `domaine_code` inclut les sous-domaines (« 1.1 » trouve aussi « 1.1.3 »)."""
    lignes = conn.execute("""
        SELECT e.id, e.forme, e.forme_citation, e.statut, e.type_morph,
               (SELECT GROUP_CONCAT(glose, ' ; ') FROM (SELECT glose FROM sens WHERE entree_id=e.id
                                                        AND glose IS NOT NULL ORDER BY ordre, id)),
               (SELECT GROUP_CONCAT(DISTINCT c.nom) FROM sens s JOIN categories c ON c.id=s.categorie_id
                WHERE s.entree_id=e.id),
               (SELECT GROUP_CONCAT(DISTINCT d.code) FROM sens s JOIN sens_domaines sd ON sd.sens_id=s.id
                JOIN domaines d ON d.guid=sd.domaine_guid WHERE s.entree_id=e.id),
               (SELECT GROUP_CONCAT(forme, ' ') FROM variantes WHERE entree_id=e.id)
        FROM entrees e""").fetchall()
    ids_categorie = None
    if categorie_id is not None:
        ids_categorie = {r[0] for r in conn.execute(
            "SELECT DISTINCT entree_id FROM sens WHERE categorie_id=?", (categorie_id,))}
    recherche = normaliser(recherche).strip().lower()
    ordre = ordre_du_projet(conn)

    resultat = []
    for eid, forme, citation, st, tm, gloses, cats, codes, variantes in lignes:
        tete = citation or forme
        if statut and st != statut:
            continue
        if type_morph and (tm or "") != type_morph:
            continue
        if ids_categorie is not None and eid not in ids_categorie:
            continue
        codes = sorted((codes or "").split(",")) if codes else []
        if domaine_code and not any(c == domaine_code or c.startswith(domaine_code + ".") for c in codes):
            continue
        if recherche and not any(recherche in (t or "").lower() for t in (forme, citation, gloses, variantes)):
            continue
        resultat.append([eid, forme, gloses or "", (cats or "").replace(",", ", "), ", ".join(codes),
                         st, 0, tete, tm or ""])

    resultat.sort(key=lambda r: (ordre.cle(r[7]), r[0]))
    numeros = homographes(conn)
    return [LigneEntree(*r[:6], numeros.get(r[0], 0), *r[7:]) for r in resultat]


def homographes(conn):
    """{id: numéro} pour les entrées qui partagent leur forme vedette (1, 2, … par ordre de création)."""
    groupes = {}
    for eid, forme, citation in conn.execute("SELECT id, forme, forme_citation FROM entrees ORDER BY id"):
        groupes.setdefault(normaliser(citation or forme).lower(), []).append(eid)
    return {eid: i for ids in groupes.values() if len(ids) > 1 for i, eid in enumerate(ids, start=1)}


EXPOSANTS = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def vedette(tete, numero):
    """« ala » ou « ala² » pour un homographe."""
    return f"{tete}{str(numero).translate(EXPOSANTS)}" if numero else tete


def chercher_par_forme(conn, forme):
    forme = normaliser(forme).strip()
    return [r[0] for r in conn.execute("SELECT id FROM entrees WHERE forme=? OR forme_citation=? ORDER BY id",
                                       (forme, forme))]


def libelle_entree(conn, entree_id):
    """« forme² — glose » pour les listes de choix."""
    ligne = conn.execute("""SELECT e.forme, e.forme_citation,
                                   (SELECT glose FROM sens WHERE entree_id=e.id ORDER BY ordre, id LIMIT 1)
                            FROM entrees e WHERE e.id=?""", (entree_id,)).fetchone()
    if not ligne:
        return ""
    texte = vedette(ligne[1] or ligne[0], homographes(conn).get(entree_id, 0))
    return f"{texte} — {ligne[2]}" if ligne[2] else texte


def formes_complexes_de(conn, entree_id):
    """[(id, forme)] des entrées dont celle-ci est un composant."""
    return conn.execute("""SELECT e.id, e.forme FROM composants c JOIN entrees e ON e.id = c.entree_id
                           WHERE c.composant_id=? ORDER BY e.forme""", (entree_id,)).fetchall()


# -- modifications en masse ------------------------------------------------------------

def modifier_en_masse(conn, entree_ids, statut=None, categorie_id=None, ajouter_domaine=None):
    """Applique un statut (entrées), une catégorie (tous leurs sens) ou ajoute un domaine
    (tous leurs sens) à plusieurs entrées. Retourne le nombre d'entrées modifiées."""
    ids = list(dict.fromkeys(entree_ids))
    if not ids:
        return 0
    if statut is not None and statut not in STATUTS:
        raise ValueError(f"Statut inconnu : {statut}")
    marques = ",".join("?" * len(ids))
    with conn:
        if statut is not None:
            conn.execute(f"UPDATE entrees SET statut=? WHERE id IN ({marques})", [statut] + ids)
        if categorie_id is not None:
            conn.execute(f"UPDATE sens SET categorie_id=? WHERE entree_id IN ({marques})", [categorie_id] + ids)
        if ajouter_domaine is not None:
            conn.execute(f"""INSERT OR IGNORE INTO sens_domaines (sens_id, domaine_guid)
                             SELECT id, ? FROM sens WHERE entree_id IN ({marques})""", [ajouter_domaine] + ids)
        conn.execute(f"UPDATE entrees SET date_modification=? WHERE id IN ({marques})", [_maintenant()] + ids)
    return len(ids)


# -- index inverse ---------------------------------------------------------------------

def index_inverse(conn, recherche=""):
    """[(forme inverse, [(entree_id, vedette, glose, catégorie)])] trié alphabétiquement
    (langue d'analyse)."""
    numeros = homographes(conn)
    index = {}
    for eid, forme, citation, glose, inverse, cat in conn.execute(
            """SELECT e.id, e.forme, e.forme_citation, s.glose, s.inverse, c.nom FROM sens s
               JOIN entrees e ON e.id = s.entree_id LEFT JOIN categories c ON c.id = s.categorie_id"""):
        for mot in formes_inverses(Sens(glose=glose or "", inverse=inverse or "")):
            index.setdefault(mot, []).append((eid, vedette(citation or forme, numeros.get(eid, 0)),
                                              glose or "", cat or ""))
    recherche = normaliser(recherche).strip().lower()
    ordre = OrdreAlphabetique("")
    return sorted(((m, sorted(v, key=lambda x: ordre.cle(x[1]))) for m, v in index.items()
                   if not recherche or recherche in m.lower()), key=lambda x: ordre.cle(x[0]))


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


# -- médias ------------------------------------------------------------------------------

def medias_de(conn, entree_id):
    """[(lien_id, media_id, rôle, sens_id, nom_fichier, chemin, note)]"""
    return conn.execute("""SELECT l.id, m.id, l.role, l.sens_id, m.nom_fichier, m.chemin, m.note
                           FROM medias_liens l JOIN medias m ON m.id = l.media_id
                           WHERE l.entree_id=? ORDER BY l.role, l.id""", (entree_id,)).fetchall()


def lier_media(conn, entree_id, chemin, role, note="", sens_id=None):
    """Enregistre un fichier déjà copié dans le dossier du projet et le lie à l'entrée."""
    import os
    with conn:
        media_id = conn.execute("INSERT INTO medias (nom_fichier, chemin, note, date_ajout) VALUES (?, ?, ?, ?)",
                                (os.path.basename(chemin), chemin, note or None, _maintenant())).lastrowid
        conn.execute("INSERT INTO medias_liens (media_id, entree_id, sens_id, role) VALUES (?, ?, ?, ?)",
                     (media_id, entree_id, sens_id, role))
    return media_id


def delier_media(conn, lien_id):
    """Retire le lien ; le fichier reste dans le dossier du projet."""
    with conn:
        conn.execute("DELETE FROM medias_liens WHERE id=?", (lien_id,))


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
        "a_verifier": compter("SELECT COUNT(*) FROM entrees WHERE statut='à vérifier'"),
        "sans_domaine": compter("""SELECT COUNT(*) FROM sens s WHERE NOT EXISTS
                                   (SELECT 1 FROM sens_domaines sd WHERE sd.sens_id = s.id)"""),
    }

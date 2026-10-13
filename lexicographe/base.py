"""Schéma SQLite versionné.

Chaque migration est numérotée et s'applique une seule fois, dans une
transaction : le numéro de version est stocké dans PRAGMA user_version.
Une base de la version 0.1 (tables verses / words…) est convertie par la
migration 1 sans perte de données.
"""

import json
import sqlite3
import uuid
from datetime import datetime

from .texte import normaliser


def connecter(chemin):
    conn = sqlite3.connect(chemin)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def version(conn):
    return conn.execute("PRAGMA user_version").fetchone()[0]


def _executer(conn, script):
    for instruction in script.split(";"):
        if instruction.strip():
            conn.execute(instruction)


def _tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


SCHEMA_1 = """
CREATE TABLE projet (
    cle TEXT PRIMARY KEY,
    valeur TEXT
);
CREATE TABLE phrases (
    ref TEXT PRIMARY KEY,
    vernaculaire TEXT,
    analyse TEXT,
    source TEXT
);
CREATE TABLE categories (
    id INTEGER PRIMARY KEY,
    nom TEXT NOT NULL UNIQUE,
    abreviation TEXT,
    parent_id INTEGER REFERENCES categories(id) ON DELETE SET NULL
);
CREATE TABLE entrees (
    id INTEGER PRIMARY KEY,
    guid TEXT NOT NULL UNIQUE,
    forme TEXT NOT NULL,
    notes TEXT,
    date_creation TEXT,
    date_modification TEXT
);
CREATE INDEX entrees_forme ON entrees(forme);
CREATE TABLE sens (
    id INTEGER PRIMARY KEY,
    entree_id INTEGER NOT NULL REFERENCES entrees(id) ON DELETE CASCADE,
    ordre INTEGER NOT NULL DEFAULT 1,
    glose TEXT,
    definition TEXT,
    categorie_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    domaine TEXT
);
CREATE INDEX sens_entree ON sens(entree_id);
CREATE TABLE exemples (
    id INTEGER PRIMARY KEY,
    sens_id INTEGER NOT NULL REFERENCES sens(id) ON DELETE CASCADE,
    vernaculaire TEXT,
    traduction TEXT,
    reference TEXT
);
CREATE TABLE relations (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES entrees(id) ON DELETE CASCADE,
    cible_id INTEGER NOT NULL REFERENCES entrees(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    UNIQUE (source_id, cible_id, type)
);
CREATE TABLE proprietes (
    entree_id INTEGER NOT NULL REFERENCES entrees(id) ON DELETE CASCADE,
    nom TEXT NOT NULL,
    valeur TEXT,
    PRIMARY KEY (entree_id, nom)
);
CREATE TABLE hypotheses (
    forme TEXT PRIMARY KEY,
    frequence INTEGER DEFAULT 0,
    candidat TEXT,
    score REAL DEFAULT 0,
    cooccurrences INTEGER DEFAULT 0,
    autres_candidats TEXT DEFAULT '[]',
    statut TEXT NOT NULL DEFAULT 'en_attente',
    entree_id INTEGER REFERENCES entrees(id) ON DELETE SET NULL,
    date_decision TEXT
);
CREATE TABLE contradictions (
    id INTEGER PRIMARY KEY,
    forme TEXT NOT NULL,
    ancienne TEXT,
    nouvelle TEXT,
    date TEXT,
    resolu INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE medias (
    id INTEGER PRIMARY KEY,
    nom_fichier TEXT,
    chemin TEXT,
    note TEXT,
    date_ajout TEXT
)
"""

CATEGORIES_PAR_DEFAUT = [
    ("nom", "n"), ("verbe", "v"), ("adjectif", "adj"), ("adverbe", "adv"), ("pronom", "pro"),
    ("nom propre", "np"), ("particule", "part"), ("idéophone", "idéo"), ("autre", "autre"),
]


def _migration_1(conn):
    anciennes = _tables(conn)
    ancien_format = "words" in anciennes
    if ancien_format:
        # les tables relations et contradictions de la v0.1 portent le même nom que les nouvelles
        for nom in ("verses", "words", "audio_files", "relations", "contradictions"):
            if nom in anciennes:
                conn.execute(f"ALTER TABLE {nom} RENAME TO _v01_{nom}")
    _executer(conn, SCHEMA_1)
    conn.executemany("INSERT OR IGNORE INTO categories (nom, abreviation) VALUES (?, ?)", CATEGORIES_PAR_DEFAUT)
    if ancien_format:
        _convertir_v01(conn, _tables(conn))


def _colonnes(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _convertir_v01(conn, tables):
    maintenant = datetime.now().isoformat(timespec="seconds")

    if "_v01_verses" in tables:
        conn.execute("""INSERT OR IGNORE INTO phrases (ref, vernaculaire, analyse, source)
                        SELECT ref, ngambay, francais, source FROM _v01_verses""")

    cols = _colonnes(conn, "_v01_words")

    def col(nom):
        return nom if nom in cols else "NULL"

    mots = conn.execute(f"""SELECT mot_ngambay, frequence, candidat_francais, score_confiance,
                                   co_occurrences, autres_candidats, statut, traduction_validee,
                                   {col('categorie')}, {col('genre')}, {col('nombre')},
                                   {col('domaine_semantique')}, {col('exemple_phrase')},
                                   {col('definition')}, {col('notes')}, date_validation
                            FROM _v01_words
                            ORDER BY CASE statut WHEN 'valide' THEN 0 WHEN 'rejete' THEN 1 ELSE 2 END""").fetchall()
    entree_par_mot = {}
    for (mot, freq, candidat, score, cooc, autres, statut, trad, cat, genre, nombre,
         domaine, exemple, definition, notes, date_val) in mots:
        forme = normaliser(mot)
        entree_id = None
        if statut == "valide":
            date = date_val or maintenant
            cur = conn.execute("""INSERT INTO entrees (guid, forme, notes, date_creation, date_modification)
                                  VALUES (?, ?, ?, ?, ?)""", (str(uuid.uuid4()), forme, notes, date, date))
            entree_id = cur.lastrowid
            entree_par_mot[mot] = entree_id
            cat_id = None
            if cat:
                conn.execute("INSERT OR IGNORE INTO categories (nom) VALUES (?)", (cat,))
                cat_id = conn.execute("SELECT id FROM categories WHERE nom=?", (cat,)).fetchone()[0]
            sens_id = conn.execute("""INSERT INTO sens (entree_id, ordre, glose, definition, categorie_id, domaine)
                                      VALUES (?, 1, ?, ?, ?, ?)""",
                                   (entree_id, trad, definition, cat_id, domaine)).lastrowid
            if exemple:
                # l'exemple automatique de la v0.1 était « vernaculaire\n→ traduction »
                vern, _, trad_ex = exemple.partition("\n→ ")
                conn.execute("INSERT INTO exemples (sens_id, vernaculaire, traduction) VALUES (?, ?, ?)",
                             (sens_id, vern.strip(), trad_ex.strip() or None))
            # genre et nombre venaient du mot français (pivot) : conservés comme propriétés
            # de l'entrée, pour que le linguiste décide s'ils décrivent bien la langue
            for nom, valeur in (("genre (traduction)", genre), ("nombre (traduction)", nombre)):
                if valeur:
                    conn.execute("INSERT INTO proprietes (entree_id, nom, valeur) VALUES (?, ?, ?)",
                                 (entree_id, nom, valeur))
        conn.execute("""INSERT OR IGNORE INTO hypotheses
                        (forme, frequence, candidat, score, cooccurrences, autres_candidats,
                         statut, entree_id, date_decision)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                     (forme, freq or 0, candidat, score or 0, cooc or 0, autres or "[]", statut,
                      entree_id, date_val if statut != "en_attente" else None))

    if "_v01_relations" in tables:
        for source, cible, typ in conn.execute(
                "SELECT mot_source, mot_cible, type_relation FROM _v01_relations").fetchall():
            src, dst = entree_par_mot.get(source), entree_par_mot.get(cible)
            if src and dst:
                conn.execute("INSERT OR IGNORE INTO relations (source_id, cible_id, type) VALUES (?, ?, ?)",
                             (src, dst, typ))
            elif src:
                # cible saisie librement et absente du lexique : rien n'est perdu
                conn.execute("""UPDATE entrees SET notes = COALESCE(notes || char(10), '') || ?
                                WHERE id=?""", (f"Relation non reliée : {typ} → {cible}", src))

    if "_v01_contradictions" in tables:
        conn.execute("""INSERT INTO contradictions (forme, ancienne, nouvelle, date, resolu)
                        SELECT mot_ngambay, ancienne_traduction, nouvelle_traduction, date, resolu
                        FROM _v01_contradictions""")
    if "_v01_audio_files" in tables:
        conn.execute("""INSERT INTO medias (nom_fichier, chemin, note, date_ajout)
                        SELECT nom_fichier, chemin_local, note, date_ajout FROM _v01_audio_files""")

    for nom in ("verses", "words", "audio_files", "relations", "contradictions"):
        conn.execute(f"DROP TABLE IF EXISTS _v01_{nom}")
    conn.execute("INSERT OR REPLACE INTO projet (cle, valeur) VALUES ('importe_depuis_v01', ?)",
                 (json.dumps({"date": maintenant}),))


MIGRATIONS = [
    (1, _migration_1),
]
VERSION_SCHEMA = MIGRATIONS[-1][0]


def migrer(conn):
    """Amène la base à la dernière version du schéma."""
    actuelle = version(conn)
    if actuelle > VERSION_SCHEMA:
        raise RuntimeError(
            f"Ce projet a été enregistré par une version plus récente du logiciel "
            f"(schéma {actuelle}, ce logiciel connaît le schéma {VERSION_SCHEMA}). "
            f"Mets le logiciel à jour pour l'ouvrir.")
    conn.commit()
    isolation = conn.isolation_level
    conn.isolation_level = None  # transactions gérées explicitement ci-dessous
    try:
        for numero, migration in MIGRATIONS:
            if numero <= actuelle:
                continue
            conn.execute("PRAGMA foreign_keys = OFF")  # tables reconstruites pendant la migration
            try:
                conn.execute("BEGIN")
                migration(conn)
                conn.execute(f"PRAGMA user_version = {numero}")
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            finally:
                conn.execute("PRAGMA foreign_keys = ON")
    finally:
        conn.isolation_level = isolation

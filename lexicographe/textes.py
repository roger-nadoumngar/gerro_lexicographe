"""Textes du corpus.

Une phrase appartient au texte désigné par le premier mot de sa référence :
« RUT 1:1 » → texte RUT (livre biblique), « T003 12 » → texte importé T003,
« MANUEL … » → phrases saisies à la main. Les métadonnées (titre, genre,
locuteur…) sont stockées par code de texte.
"""

import re
from dataclasses import dataclass

from . import usfm
from .texte import normaliser

NOMS_LIVRES = {
    "GEN": "Genèse", "EXO": "Exode", "LEV": "Lévitique", "NUM": "Nombres", "DEU": "Deutéronome",
    "JOS": "Josué", "JDG": "Juges", "RUT": "Ruth", "1SA": "1 Samuel", "2SA": "2 Samuel", "JOB": "Job",
    "PSA": "Psaumes", "PRO": "Proverbes", "ISA": "Ésaïe", "JON": "Jonas", "MAT": "Matthieu", "MRK": "Marc",
    "LUK": "Luc", "JHN": "Jean", "ACT": "Actes", "ROM": "Romains", "REV": "Apocalypse",
}
GENRES = ["récit", "conte", "conversation", "procédure", "exhortation", "chant", "proverbe", "prière",
          "texte biblique", "autre"]


@dataclass
class Texte:
    code: str
    titre: str = ""
    genre: str = ""
    locuteur: str = ""
    lieu: str = ""
    date: str = ""
    notes: str = ""
    phrases: int = 0


def code_texte(ref):
    return (ref or "").split(" ", 1)[0]


def _titre_par_defaut(code):
    if code == "MANUEL":
        return "Phrases saisies"
    if code in NOMS_LIVRES:
        return NOMS_LIVRES[code]
    return code


def lister(conn):
    """Textes présents dans le corpus, dans l'ordre canonique puis par code."""
    comptes = {}
    for (ref,) in conn.execute("SELECT ref FROM phrases"):
        code = code_texte(ref)
        comptes[code] = comptes.get(code, 0) + 1
    meta = {r[0]: r for r in conn.execute("SELECT code, titre, genre, locuteur, lieu, date, notes FROM textes")}
    resultat = []
    for code, n in comptes.items():
        m = meta.get(code)
        t = Texte(code=code, phrases=n, titre=(m[1] if m and m[1] else _titre_par_defaut(code)))
        if m:
            t.genre, t.locuteur, t.lieu, t.date, t.notes = (x or "" for x in m[2:])
        elif code in usfm.LIVRES:
            t.genre = "texte biblique"
        resultat.append(t)

    def cle(t):
        rang = usfm.LIVRES.index(t.code) if t.code in usfm.LIVRES else None
        return (0, rang, "") if rang is not None else (1 if t.code != "MANUEL" else 2, 0, t.code)
    return sorted(resultat, key=cle)


def enregistrer_meta(conn, texte):
    with conn:
        conn.execute("""INSERT INTO textes (code, titre, genre, locuteur, lieu, date, notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(code) DO UPDATE SET titre=excluded.titre, genre=excluded.genre,
                           locuteur=excluded.locuteur, lieu=excluded.lieu, date=excluded.date, notes=excluded.notes""",
                     (texte.code, texte.titre, texte.genre, texte.locuteur, texte.lieu, texte.date, texte.notes))


def phrases(conn, code):
    """[(ref, vernaculaire, analyse)] du texte, dans l'ordre."""
    lignes = conn.execute("SELECT ref, vernaculaire, analyse FROM phrases WHERE ref = ? OR ref LIKE ?",
                          (code, code + " %")).fetchall()
    return sorted(lignes, key=lambda l: usfm.cle_reference(l[0]))


def decouper_en_phrases(texte):
    """Découpe un texte brut en phrases : fin de ligne vide (paragraphe), ou ponctuation
    finale (. ! ? …) suivie d'un espace. Les retours à la ligne simples sont conservés
    comme fins de phrase (transcriptions ligne par ligne)."""
    texte = normaliser(texte).replace("\r\n", "\n").replace("\r", "\n")
    phrases_ = []
    for ligne in texte.split("\n"):
        ligne = ligne.strip()
        if not ligne:
            continue
        morceaux = re.split(r"(?<=[.!?…])\s+", ligne)
        phrases_.extend(m.strip() for m in morceaux if m.strip())
    return phrases_


def nouveau_code(conn):
    existants = {code_texte(r[0]) for r in conn.execute("SELECT ref FROM phrases")}
    existants |= {r[0] for r in conn.execute("SELECT code FROM textes")}
    n = 1
    while f"T{n:03d}" in existants:
        n += 1
    return f"T{n:03d}"


def importer_texte(projet, meta, texte_vern, texte_trad=""):
    """Ajoute un texte au corpus. Si une traduction est fournie, elle doit avoir le même
    nombre de phrases (sinon ValueError : on ne devine pas l'alignement).
    Retourne le code du texte."""
    vern = decouper_en_phrases(texte_vern)
    trad = decouper_en_phrases(texte_trad) if texte_trad and texte_trad.strip() else []
    if not vern:
        raise ValueError("Le texte est vide.")
    if trad and len(trad) != len(vern):
        raise ValueError(f"Le texte compte {len(vern)} phrase(s) et la traduction {len(trad)} : "
                         "aligne-les ligne à ligne (une phrase par ligne) pour qu'elles correspondent.")
    conn = projet.conn
    meta.code = meta.code or nouveau_code(conn)
    with conn:
        conn.executemany("INSERT INTO phrases (ref, vernaculaire, analyse, source) VALUES (?, ?, ?, ?)",
                         [(f"{meta.code} {i}", v, trad[i - 1] if trad else None, f"texte {meta.code}")
                          for i, v in enumerate(vern, start=1)])
    enregistrer_meta(conn, meta)
    return meta.code

"""Contrôles des données : lettres d'un autre alphabet qui imitent des lettres latines.

Une source peut écrire « ӯ » avec le у cyrillique (U+0443) au lieu du y latin : à l'œil c'est la
même lettre, mais pour l'ordinateur ce n'en est pas une (tri, recherche, concordance, clavier…).

Règle : dans un mot qui contient au moins une lettre latine, chaque lettre cyrillique ou grecque
de la table SOSIES est remplacée par son sosie latin (les signes combinants, comme le macron de
« ӯ », sont gardés). Un mot sans lettre latine n'est pas touché : il est peut-être vraiment écrit
dans cet alphabet."""

import re
import unicodedata
from dataclasses import dataclass

from .texte import normaliser

SOSIES = {
    # cyrillique
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j",
    "ѕ": "s", "ԁ": "d", "һ": "h", "ԛ": "q", "ԝ": "w", "ӏ": "l",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C",
    "Т": "T", "У": "Y", "Х": "X", "І": "I", "Ј": "J", "Ѕ": "S",
    # grec
    "ο": "o", "α": "a", "ι": "i", "κ": "k", "ν": "v", "ρ": "p", "υ": "u", "ε": "ɛ", "Ο": "O",
    "Α": "A", "Β": "B", "Ε": "E", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N", "Ρ": "P",
    "Τ": "T", "Χ": "X", "Υ": "Y", "Ζ": "Z",
}

# filtre rapide : seuls les textes avec au moins un caractère grec ou cyrillique sont examinés
_AUTRE_ALPHABET = re.compile("[Ͱ-ϿЀ-ԯ]")

# champs en langue documentée : (table, colonne)
CHAMPS = [("entrees", "forme"), ("entrees", "forme_citation"), ("variantes", "forme"),
          ("exemples", "vernaculaire"), ("phrases", "vernaculaire")]


def _latin(ch):
    return ch.isalpha() and "LATIN" in unicodedata.name(ch, "")


def corriger_texte(texte):
    """Texte corrigé selon la règle (identique s'il n'y a rien à corriger)."""
    if not texte or not _AUTRE_ALPHABET.search(texte):
        return texte

    def mot(m):
        m = m.group(0)
        decompose = unicodedata.normalize("NFD", m)
        if not any(_latin(ch) for ch in decompose) or not any(ch in SOSIES for ch in decompose):
            return m
        return unicodedata.normalize("NFC", "".join(SOSIES.get(ch, ch) for ch in decompose))
    return normaliser(re.sub(r"\S+", mot, texte))


@dataclass
class Occurrence:
    table: str
    colonne: str
    ligne_id: int
    avant: str
    apres: str


def trouver(conn):
    occurrences = []
    for table, colonne in CHAMPS:
        for ligne_id, valeur in conn.execute(f"SELECT rowid, {colonne} FROM {table} WHERE {colonne} IS NOT NULL"):
            corrige = corriger_texte(valeur)
            if corrige != valeur:
                occurrences.append(Occurrence(table, colonne, ligne_id, valeur, corrige))
    return occurrences


def corriger(conn, occurrences=None):
    """Applique les corrections ; retourne leur nombre."""
    occurrences = trouver(conn) if occurrences is None else occurrences
    from .lexique import _maintenant
    maintenant = _maintenant()
    with conn:
        for o in occurrences:
            conn.execute(f"UPDATE {o.table} SET {o.colonne}=? WHERE rowid=?", (o.apres, o.ligne_id))
            if o.table == "entrees":   # la fusion entre postes voit la modification
                conn.execute("UPDATE entrees SET date_modification=? WHERE id=?", (maintenant, o.ligne_id))
    return len(occurrences)

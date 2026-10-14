"""Corpus d'exemple : Ruth et Job en ngambay et en français (Segond 1910). Il sert aux tests et n'est pas
livré avec le logiciel, qui reste neutre pour toutes les langues."""

import json

from .chemins import ressource
from .texte import normaliser

CORPUS_INTEGRES = {
    "ngambay_ruth_job": ("corpus/ngambay_verses.json", "corpus/french_verses.json"),
}
SOURCE = "corpus_initial"


def disponible(nom):
    """Le corpus d'exemple n'est pas livré avec le logiciel (seulement avec les tests) :
    il n'est proposé que si ses fichiers sont présents."""
    if nom not in CORPUS_INTEGRES:
        return False
    try:
        return all(ressource(chemin) for chemin in CORPUS_INTEGRES[nom])
    except FileNotFoundError:
        return False


def synchroniser(projet):
    """Ajoute au projet les versets du corpus intégré qui lui manquent et applique
    les corrections du corpus. Les versets importés ou saisis par l'utilisateur
    (autre source) ne sont jamais réécrits. Retourne le nombre de versets chargés."""
    nom = projet.reglage("corpus_integre")
    if not disponible(nom):
        return 0
    chemin_v, chemin_a = CORPUS_INTEGRES[nom]
    with open(ressource(chemin_v), encoding="utf-8") as f:
        vern = json.load(f)
    with open(ressource(chemin_a), encoding="utf-8") as f:
        analyse = json.load(f)
    communes = [ref for ref in vern if ref in analyse]
    with projet.conn:
        projet.conn.executemany(
            """INSERT INTO phrases (ref, vernaculaire, analyse, source) VALUES (?, ?, ?, ?)
               ON CONFLICT(ref) DO UPDATE SET
                  vernaculaire=CASE WHEN phrases.source=? THEN excluded.vernaculaire
                                    ELSE COALESCE(phrases.vernaculaire, excluded.vernaculaire) END,
                  analyse=CASE WHEN phrases.source=? THEN excluded.analyse
                               ELSE COALESCE(phrases.analyse, excluded.analyse) END""",
            [(ref, normaliser(vern[ref]), normaliser(analyse[ref]), SOURCE, SOURCE, SOURCE) for ref in communes])
    return len(communes)

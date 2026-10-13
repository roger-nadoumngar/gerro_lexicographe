"""Corpus d'exemple intégré : Ruth et Job en ngambay et en français (Segond 1910)."""

import json

from .chemins import ressource
from .texte import normaliser

CORPUS_INTEGRES = {
    "ngambay_ruth_job": ("corpus/ngambay_verses.json", "corpus/french_verses.json"),
}
SOURCE = "corpus_initial"


def synchroniser(projet):
    """Ajoute au projet les versets du corpus intégré qui lui manquent et applique
    les corrections du corpus. Les versets importés ou saisis par l'utilisateur
    (autre source) ne sont jamais réécrits. Retourne le nombre de versets chargés."""
    nom = projet.reglage("corpus_integre")
    if nom not in CORPUS_INTEGRES:
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

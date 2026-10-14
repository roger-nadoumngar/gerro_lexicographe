import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Qt sans écran (offscreen) ne trouve pas les polices du système : sans elles, rien n'est dessiné
# (PDF vides, tailles de texte nulles). On lui indique celles de Windows quand elles existent.
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

from lexicographe.projet import Projet  # noqa: E402

# le corpus d'exemple (Ruth et Job, ngambay–français) n'est pas livré avec le logiciel : les tests
# le trouvent dans tests/donnees
DONNEES_TEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "donnees")


@pytest.fixture(autouse=True)
def corpus_de_test(monkeypatch):
    monkeypatch.setattr("lexicographe.corpus.ressource", lambda *parties: os.path.join(DONNEES_TEST, *parties))


@pytest.fixture
def projet(tmp_path):
    p = Projet.creer(str(tmp_path / "test.lexique"), nom="Test", langue_vern_code="sba",
                     langue_vern_nom="ngambay")
    yield p
    p.fermer()


SCHEMA_V01 = """
CREATE TABLE verses (ref TEXT PRIMARY KEY, ngambay TEXT, francais TEXT, source TEXT DEFAULT 'corpus');
CREATE TABLE words (mot_ngambay TEXT PRIMARY KEY, frequence INTEGER DEFAULT 0, candidat_francais TEXT,
    score_confiance REAL DEFAULT 0, co_occurrences INTEGER DEFAULT 0, autres_candidats TEXT DEFAULT '[]',
    statut TEXT DEFAULT 'en_attente', traduction_validee TEXT, categorie TEXT, date_validation TEXT,
    genre TEXT, nombre TEXT, domaine_semantique TEXT, exemple_phrase TEXT, definition TEXT, notes TEXT);
CREATE TABLE audio_files (id INTEGER PRIMARY KEY AUTOINCREMENT, nom_fichier TEXT, chemin_local TEXT,
    note TEXT, date_ajout TEXT);
CREATE TABLE relations (id INTEGER PRIMARY KEY AUTOINCREMENT, mot_source TEXT, mot_cible TEXT,
    type_relation TEXT, date TEXT);
CREATE TABLE contradictions (id INTEGER PRIMARY KEY AUTOINCREMENT, mot_ngambay TEXT,
    ancienne_traduction TEXT, nouvelle_traduction TEXT, ref_verset TEXT, date TEXT, resolu INTEGER DEFAULT 0);
"""


@pytest.fixture
def base_v01(tmp_path):
    """Base au format de la version 0.1 (app.py Tkinter)."""
    chemin = str(tmp_path / "lexique_ngambay.db")
    conn = sqlite3.connect(chemin)
    conn.executescript(SCHEMA_V01)
    conn.execute("INSERT INTO verses VALUES ('RUT 1:1', 'Ala ndɔ', 'Dieu jour', 'corpus_initial')")
    conn.executemany(
        "INSERT INTO words (mot_ngambay, frequence, candidat_francais, score_confiance, statut, "
        "traduction_validee, categorie, genre, nombre, domaine_semantique, exemple_phrase, definition, "
        "notes, date_validation) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [("ala", 5, "dieu", 0.8, "valide", "dieu", "nom", "masculin", "singulier", "religion / spirituel",
          "Ala ndɔ\n→ Dieu jour", "être suprême", "emprunt ?", "2026-09-03T11:49:34.123"),
         ("ndɔ", 3, "jour", 0.6, "valide", "jour", None, None, None, None, None, None, None, "2026-09-04T10:00:00"),
         # forme décomposée (o + accent combinant) : doit être normalisée
         ("kó", 2, "arbre", 0.4, "en_attente", None, None, None, None, None, None, None, None, None),
         ("bé", 1, "x", 0.1, "rejete", None, None, None, None, None, None, None, None, "2026-09-05T00:00:00")])
    conn.executemany("INSERT INTO relations (mot_source, mot_cible, type_relation, date) VALUES (?,?,?,?)",
                     [("ala", "ndɔ", "voir aussi", "x"), ("ala", "inconnu", "synonyme", "x")])
    conn.execute("INSERT INTO contradictions (mot_ngambay, ancienne_traduction, nouvelle_traduction, date) "
                 "VALUES ('ala', 'dieu', 'seigneur', '2026')")
    conn.commit()
    conn.close()
    return chemin

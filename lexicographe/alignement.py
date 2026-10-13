"""Hypothèses de traduction à partir de phrases parallèles.

Méthode (explicite et reproductible) : pour chaque mot vernaculaire v et
chaque mot plein de la langue d'analyse a, on compte les phrases où ils
apparaissent ensemble, puis on calcule le coefficient de Dice :

    Dice(v, a) = 2 × phrases(v et a) / (phrases(v) + phrases(a))

Le candidat proposé est celui qui a le meilleur score. Ce n'est qu'une
proposition : rien n'entre dans le lexique sans décision humaine, et
`preuves()` montre les phrases qui justifient chaque proposition.
"""

import json
from collections import defaultdict
from datetime import datetime

from . import lexique
from .texte import normaliser


def _paires(projet):
    return projet.conn.execute("""SELECT ref, vernaculaire, analyse FROM phrases
                                  WHERE vernaculaire IS NOT NULL AND analyse IS NOT NULL""").fetchall()


def recalculer(projet):
    """Recalcule toutes les hypothèses ; retourne le nombre de nouvelles contradictions."""
    conn = projet.conn
    tok_v, tok_a = projet.tokeniseur_vern, projet.tokeniseur_analyse
    cooc = defaultdict(lambda: defaultdict(int))
    freq_v, freq_a = defaultdict(int), defaultdict(int)

    for _, vern, analyse in _paires(projet):
        mots_v = set(tok_v.mots(vern))
        mots_a = set(tok_a.mots_pleins(analyse))
        for v in mots_v:
            freq_v[v] += 1
        for a in mots_a:
            freq_a[a] += 1
        for v in mots_v:
            for a in mots_a:
                cooc[v][a] += 1

    decidees = dict(conn.execute("SELECT forme, statut FROM hypotheses WHERE statut != 'en_attente'"))
    try:
        seuil = float(projet.reglage("seuil_contradiction") or 0.5)
    except ValueError:
        seuil = 0.5
    contradictions = []

    with conn:
        for v, freq in freq_v.items():
            candidats = sorted(((a, 2 * n / (freq + freq_a[a]), n) for a, n in cooc[v].items()),
                               key=lambda x: (-x[1], x[0]))  # égalité : ordre alphabétique, résultat stable
            if candidats:
                meilleur, score, n = candidats[0]
            else:
                meilleur, score, n = None, 0.0, 0
            autres = json.dumps([c[0] for c in candidats[1:6]], ensure_ascii=False)

            if v in decidees:
                conn.execute("""UPDATE hypotheses SET frequence=?, candidat=?, score=?, cooccurrences=?,
                                autres_candidats=? WHERE forme=?""",
                             (freq, meilleur, round(score, 3), n, autres, v))
                if decidees[v] == "valide" and meilleur and score > seuil:
                    gloses = _mots_des_gloses(projet, v)
                    if gloses and meilleur not in gloses:
                        contradictions.append((v, " / ".join(sorted(gloses)), meilleur))
            else:
                conn.execute("""INSERT INTO hypotheses
                                (forme, frequence, candidat, score, cooccurrences, autres_candidats, statut)
                                VALUES (?, ?, ?, ?, ?, ?, 'en_attente')
                                ON CONFLICT(forme) DO UPDATE SET frequence=excluded.frequence,
                                    candidat=excluded.candidat, score=excluded.score,
                                    cooccurrences=excluded.cooccurrences,
                                    autres_candidats=excluded.autres_candidats""",
                             (v, freq, meilleur, round(score, 3), n, autres))

        # hypothèses en attente qui ne correspondent plus à aucun mot du corpus
        # (règles de découpage modifiées, phrase supprimée…)
        perimees = [(f,) for (f,) in conn.execute("SELECT forme FROM hypotheses WHERE statut='en_attente'")
                    if f not in freq_v]
        conn.executemany("DELETE FROM hypotheses WHERE forme=?", perimees)

        nouvelles = 0
        for forme, ancienne, nouvelle in contradictions:
            # déjà signalée, ou déjà tranchée par l'utilisateur : on ne la repose pas
            if conn.execute("SELECT 1 FROM contradictions WHERE forme=? AND nouvelle=? LIMIT 1",
                            (forme, nouvelle)).fetchone():
                continue
            conn.execute("INSERT INTO contradictions (forme, ancienne, nouvelle, date) VALUES (?, ?, ?, ?)",
                         (forme, ancienne, nouvelle, datetime.now().isoformat(timespec="seconds")))
            nouvelles += 1
    return nouvelles


def _mots_des_gloses(projet, forme):
    """Mots pleins de toutes les gloses des entrées liées à cette forme."""
    mots = set()
    for (glose,) in projet.conn.execute(
            """SELECT s.glose FROM hypotheses h JOIN sens s ON s.entree_id = h.entree_id
               WHERE h.forme=? AND s.glose IS NOT NULL""", (forme,)):
        mots.update(projet.tokeniseur_analyse.mots_pleins(glose))
    return mots


def preuves(projet, forme, candidat, limite=50):
    """Phrases où la forme et le candidat apparaissent ensemble : la justification
    de la proposition. [(ref, vernaculaire, analyse)]"""
    tok_v, tok_a = projet.tokeniseur_vern, projet.tokeniseur_analyse
    resultat = []
    for ref, vern, analyse in _paires(projet):
        if forme in tok_v.mots(vern) and (not candidat or candidat in tok_a.mots(analyse)):
            resultat.append((ref, vern, analyse))
            if len(resultat) >= limite:
                break
    return resultat


def file_validation(projet, exclues=()):
    """Hypothèses en attente, les plus sûres d'abord."""
    lignes = projet.conn.execute("""SELECT forme, frequence, candidat, score, cooccurrences, autres_candidats
                                    FROM hypotheses WHERE statut='en_attente'
                                    ORDER BY score DESC, frequence DESC, forme""").fetchall()
    return [l for l in lignes if l[0] not in exclues]


def valider(projet, forme, entree):
    """Enregistre l'entrée (lexique.Entree) et marque l'hypothèse comme validée."""
    conn = projet.conn
    entree_id = lexique.enregistrer_entree(conn, entree)
    with conn:
        conn.execute("""UPDATE hypotheses SET statut='valide', entree_id=?, date_decision=?
                        WHERE forme=?""", (entree_id, datetime.now().isoformat(timespec="seconds"), forme))
    return entree_id


def rejeter(projet, forme):
    with projet.conn:
        projet.conn.execute("UPDATE hypotheses SET statut='rejete', date_decision=? WHERE forme=?",
                            (datetime.now().isoformat(timespec="seconds"), forme))


def remettre_en_attente(projet, forme):
    with projet.conn:
        projet.conn.execute("""UPDATE hypotheses SET statut='en_attente', date_decision=NULL
                               WHERE forme=? AND statut='rejete'""", (forme,))


def contradictions_ouvertes(projet):
    """[(id, forme, ancienne, nouvelle)]"""
    return projet.conn.execute("""SELECT id, forme, ancienne, nouvelle FROM contradictions
                                  WHERE resolu=0 ORDER BY date DESC, id DESC""").fetchall()


def resoudre_contradiction(projet, contradiction_id, adopter=False):
    """Clôt la contradiction. Si `adopter`, la nouvelle traduction devient la glose
    du premier sens de l'entrée liée."""
    conn = projet.conn
    ligne = conn.execute("SELECT forme, nouvelle FROM contradictions WHERE id=?", (contradiction_id,)).fetchone()
    if not ligne:
        return
    forme, nouvelle = ligne
    with conn:
        if adopter:
            entree_id = conn.execute("SELECT entree_id FROM hypotheses WHERE forme=?", (forme,)).fetchone()
            if entree_id and entree_id[0]:
                sens_id = conn.execute("SELECT id FROM sens WHERE entree_id=? ORDER BY ordre, id LIMIT 1",
                                       (entree_id[0],)).fetchone()
                if sens_id:
                    conn.execute("UPDATE sens SET glose=? WHERE id=?", (nouvelle, sens_id[0]))
                    conn.execute("UPDATE entrees SET date_modification=? WHERE id=?",
                                 (datetime.now().isoformat(timespec="seconds"), entree_id[0]))
        # une décision humaine clôt toutes les alertes ouvertes de ce mot
        conn.execute("UPDATE contradictions SET resolu=1 WHERE forme=? AND resolu=0", (forme,))


def ajouter_phrase(projet, vernaculaire, analyse, source="saisie_manuelle"):
    """Ajoute une paire de phrases au corpus ; retourne sa référence."""
    import uuid
    ref = f"MANUEL {datetime.now().strftime('%Y%m%d%H%M%S')} {uuid.uuid4().hex[:8]}"
    with projet.conn:
        projet.conn.execute("INSERT INTO phrases (ref, vernaculaire, analyse, source) VALUES (?, ?, ?, ?)",
                            (ref, normaliser(vernaculaire).strip(), normaliser(analyse).strip(), source))
    return ref

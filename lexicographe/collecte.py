"""Collecte communautaire (inspiré de WeSay) : collecte guidée par domaine sémantique et
tâches de complément du lexique, une entrée à la fois.

Règles :
* un mot collecté devient une entrée « brouillon » classée dans le domaine de la question ;
  si une entrée de même forme existe déjà, le domaine est ajouté à son premier sens au lieu
  de créer un doublon ;
* les tâches portent sur des manques vérifiables : sens sans glose, sens sans exemple,
  sens sans domaine, entrée sans enregistrement ; on ne modifie que le champ de la tâche.
"""

import json
from dataclasses import dataclass

from . import domaines, lexique
from .lexique import Entree, Exemple, Sens
from .texte import normaliser

TACHES = {
    "glose": ("Ajouter le sens des mots", "Mots dont un sens n'a pas encore de traduction."),
    "exemple": ("Ajouter des exemples", "Sens qui n'ont pas encore de phrase d'exemple."),
    "domaine": ("Classer dans les domaines", "Sens qui ne sont classés dans aucun domaine sémantique."),
    "audio": ("Enregistrer la prononciation", "Mots qui n'ont pas encore d'enregistrement."),
}

_REQUETES = {
    "glose": """SELECT DISTINCT e.id FROM entrees e JOIN sens s ON s.entree_id = e.id
                WHERE COALESCE(TRIM(s.glose), '') = ''""",
    "exemple": """SELECT DISTINCT e.id FROM entrees e JOIN sens s ON s.entree_id = e.id
                  WHERE COALESCE(TRIM(s.glose), '') != ''
                    AND NOT EXISTS (SELECT 1 FROM exemples x WHERE x.sens_id = s.id)""",
    "domaine": """SELECT DISTINCT e.id FROM entrees e JOIN sens s ON s.entree_id = e.id
                  WHERE NOT EXISTS (SELECT 1 FROM sens_domaines sd WHERE sd.sens_id = s.id)""",
    "audio": """SELECT e.id FROM entrees e WHERE NOT EXISTS
                (SELECT 1 FROM medias_liens l WHERE l.entree_id = e.id AND l.role = 'prononciation')""",
}


def a_faire(conn, tache):
    """Ids des entrées concernées par la tâche, dans l'ordre alphabétique du projet."""
    ids = {r[0] for r in conn.execute(_REQUETES[tache])}
    return [l.id for l in lexique.lister_entrees(conn) if l.id in ids]


def compter(conn):
    return {t: len({r[0] for r in conn.execute(_REQUETES[t])}) for t in TACHES}


def sens_concerne(entree, tache, conn=None):
    """Premier sens de l'entrée qui manque de ce que la tâche demande (None pour l'audio)."""
    for s in entree.sens:
        if tache == "glose" and not s.glose.strip():
            return s
        if tache == "exemple" and s.glose.strip() and not s.exemples:
            return s
        if tache == "domaine" and not s.domaines:
            return s
    return None


def completer(conn, entree_id, tache, valeur):
    """Enregistre la réponse d'une tâche : glose (texte), exemple ((phrase, traduction)) ou
    domaine (guid). Retourne True si quelque chose a été enregistré."""
    entree = lexique.lire_entree(conn, entree_id)
    s = sens_concerne(entree, tache)
    if s is None:
        return False
    if tache == "glose":
        if not (valeur or "").strip():
            return False
        s.glose = valeur.strip()
    elif tache == "exemple":
        phrase, traduction = valeur
        if not (phrase or "").strip():
            return False
        s.exemples.append(Exemple(phrase.strip(), (traduction or "").strip()))
    elif tache == "domaine":
        if not valeur:
            return False
        s.domaines.append(valeur)
    else:
        raise ValueError(tache)
    lexique.enregistrer_entree(conn, entree)
    return True


# -- collecte par domaine ---------------------------------------------------------------------

@dataclass
class Question:
    guid: str
    code: str
    nom: str
    description: str
    numero: int            # rang de la question dans le domaine (0, 1, …)
    total: int             # nombre de questions du domaine
    texte: str
    mots_exemples: str


def questions(conn, langue="fr"):
    """Toutes les questions d'élicitation, domaine après domaine (ordre des codes).
    Un domaine sans question donne une question générique."""
    resultat = []
    for guid, code, nom, _ in domaines.arbre(conn, langue):
        d = domaines.details(conn, guid, langue)
        qs = d["questions"] or [{"question": f"Quels mots se rapportent à « {nom} » ?", "mots": ""}]
        for i, q in enumerate(qs):
            resultat.append(Question(guid, code, nom, d["description"], i, len(qs), q["question"], q["mots"]))
    return resultat


def ajouter_mot(conn, domaine_guid, forme, glose=""):
    """Mot donné en réponse à une question du domaine. Retourne (id de l'entrée, créée ?)."""
    forme = normaliser(forme).strip()
    if not forme:
        raise ValueError("Le mot est vide.")
    # sans tenir compte des majuscules : « Dɔ » tapé par un locuteur rejoint l'entrée « dɔ »
    cible = forme.lower()
    existantes = [eid for eid, f, c in conn.execute("SELECT id, forme, forme_citation FROM entrees ORDER BY id")
                  if normaliser(f).lower() == cible or normaliser(c or "").lower() == cible]
    for eid in existantes:
        entree = lexique.lire_entree(conn, eid)
        sens = entree.sens[0] if entree.sens else None
        if sens is None:
            entree.sens.append(Sens(glose=glose, domaines=[domaine_guid]))
        else:
            if domaine_guid not in sens.domaines:
                sens.domaines.append(domaine_guid)
            if glose and not sens.glose:
                sens.glose = glose
        lexique.enregistrer_entree(conn, entree)
        return eid, False
    eid = lexique.enregistrer_entree(conn, Entree(forme=forme, statut="brouillon",
                                                  sens=[Sens(glose=normaliser(glose).strip(),
                                                             domaines=[domaine_guid])]))
    return eid, True


def mots_du_domaine(conn, guid):
    return domaines.sens_du_domaine(conn, guid)


def position_enregistree(projet):
    try:
        return json.loads(projet.reglage("collecte_position") or "{}")
    except ValueError:
        return {}


def enregistrer_position(projet, guid, numero):
    """Reprise de la collecte là où elle s'est arrêtée."""
    projet.definir_reglages({"collecte_position": json.dumps({"guid": guid, "numero": numero})})

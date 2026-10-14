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


# -- collecte à partir d'une liste de mots (comme la liste de mots de WeSay) ------------------
#
# Règles :
# * une liste est une suite de mots de la langue d'analyse, éventuellement rangés par groupe
#   (« Mammifères », « Oiseaux »…) ; elle est gardée dans le projet ;
# * un mot de la liste est « trouvé » quand une entrée a un sens dont la glose, découpée aux
#   virgules et points-virgules (hors parenthèses), contient exactement ce mot ;
# * répondre crée une entrée brouillon dont la glose est le mot de la liste ; si une entrée de même
#   forme existe, la glose lui est ajoutée comme nouveau sens au lieu de créer un doublon.

@dataclass
class ElementListe:
    mot: str
    groupe: str = ""


def segments_glose(glose):
    """« bovin; boeuf, vache » → {"bovin", "boeuf", "vache"} ; le contenu des parenthèses et
    crochets est ignoré (« piquer (scorpion, fourmi) » ne contient pas « fourmi »)."""
    import re
    from .dico_imprime import cle_glose
    texte = re.sub(r"\([^)]*\)", " ", cle_glose(glose))
    return {" ".join(s.split()) for s in re.split(r"[;,]", texte) if s.strip()}


def lire_liste(chemin):
    """Mots d'une liste Word (.docx : lignes « 1⇥eau⇥… » ou tableaux « N° | Nom commun | … »,
    titres « 1. Mammifères (25) » pris comme groupes) ou texte (.txt, .csv : une ligne par mot,
    colonnes séparées par tabulation, point-virgule ou virgule ; un numéro en tête est ignoré)."""
    import os
    import re
    titre_groupe = re.compile(r"^\d+\.\s+(.+?)\s*\(\d+\)\s*$")
    elements, groupe = [], ""

    def ajouter_ligne(colonnes):
        colonnes = [normaliser(c).strip() for c in colonnes]
        colonnes = [c for c in colonnes if c]
        if colonnes and re.fullmatch(r"[\d.]+|N°|No|ID", colonnes[0], re.I):
            colonnes = colonnes[1:]
        if not colonnes or colonnes[0].lower() in ("français", "francais", "nom commun", "mot", "english"):
            return
        elements.append(ElementListe(colonnes[0], groupe))

    if os.path.splitext(chemin)[1].lower() == ".docx":
        import docx
        from docx.table import Table
        from docx.text.paragraph import Paragraph
        document = docx.Document(chemin)
        for bloc in document.element.body.iterchildren():
            if bloc.tag.endswith("}p"):
                texte = Paragraph(bloc, document).text
                m = titre_groupe.match(texte.strip())
                if m:
                    groupe = m.group(1)
                elif "\t" in texte and re.match(r"\s*\d+\s*\t", texte):
                    ajouter_ligne(texte.split("\t"))
            elif bloc.tag.endswith("}tbl"):
                for rangee in Table(bloc, document).rows:
                    ajouter_ligne([c.text for c in rangee.cells])
    else:
        with open(chemin, encoding="utf-8-sig", errors="replace") as f:
            for ligne in f:
                if ligne.strip():
                    m = titre_groupe.match(ligne.strip())
                    if m:
                        groupe = m.group(1)
                        continue
                    separateur = "\t" if "\t" in ligne else ";" if ";" in ligne else ","
                    ajouter_ligne(ligne.rstrip("\n").split(separateur))
    # une liste ne contient pas deux fois le même mot
    vus, uniques = set(), []
    for e in elements:
        if e.mot.lower() not in vus:
            vus.add(e.mot.lower())
            uniques.append(e)
    return uniques


def listes(projet):
    try:
        brut = json.loads(projet.reglage("listes_collecte") or "{}")
    except ValueError:
        return {}
    return {nom: [ElementListe(*e) for e in elements] for nom, elements in brut.items()}


def enregistrer_liste(projet, nom, elements):
    toutes = listes(projet)
    toutes[nom] = elements
    projet.definir_reglages({"listes_collecte": json.dumps(
        {n: [[e.mot, e.groupe] for e in els] for n, els in toutes.items()}, ensure_ascii=False)})


def supprimer_liste(projet, nom):
    toutes = listes(projet)
    toutes.pop(nom, None)
    projet.definir_reglages({"listes_collecte": json.dumps(
        {n: [[e.mot, e.groupe] for e in els] for n, els in toutes.items()}, ensure_ascii=False)})


def index_des_gloses(conn):
    """{segment de glose: [(id de l'entrée, forme)]} pour savoir vite quels mots sont trouvés."""
    index = {}
    for eid, forme, glose in conn.execute(
            "SELECT e.id, e.forme, s.glose FROM entrees e JOIN sens s ON s.entree_id = e.id ORDER BY e.id"):
        for seg in segments_glose(glose):
            if (eid, forme) not in index.setdefault(seg, []):
                index[seg].append((eid, forme))
    return index


def trouves(conn, mot, index=None):
    from .dico_imprime import cle_glose
    index = index if index is not None else index_des_gloses(conn)
    return index.get(cle_glose(mot), [])


def avancement(conn, elements):
    index = index_des_gloses(conn)
    return sum(1 for e in elements if trouves(conn, e.mot, index))


def repondre_liste(conn, element, forme, nom_liste=""):
    """La forme donnée pour un mot de la liste. Retourne (id de l'entrée, créée ?)."""
    forme = normaliser(forme).strip()
    if not forme:
        raise ValueError("Le mot est vide.")
    glose = normaliser(element.mot).strip()
    cible = forme.lower()
    for eid, f, c in conn.execute("SELECT id, forme, forme_citation FROM entrees ORDER BY id").fetchall():
        if normaliser(f).lower() == cible or normaliser(c or "").lower() == cible:
            entree = lexique.lire_entree(conn, eid)
            if not any(glose.lower() in {x.lower() for x in segments_glose(s.glose)} for s in entree.sens):
                vide = next((s for s in entree.sens if not s.glose.strip()), None)
                if vide:
                    vide.glose = glose
                else:
                    entree.sens.append(Sens(glose=glose))
                lexique.enregistrer_entree(conn, entree)
            return eid, False
    note = f"Collecte : liste « {nom_liste} »" + (f", {element.groupe}" if element.groupe else "") if nom_liste else ""
    eid = lexique.enregistrer_entree(conn, Entree(forme=forme, statut="brouillon", notes=note,
                                                  sens=[Sens(glose=glose)]))
    return eid, True


def position_liste(projet, nom):
    try:
        return int(json.loads(projet.reglage("listes_collecte_position") or "{}").get(nom, 0))
    except (ValueError, TypeError):
        return 0


def enregistrer_position_liste(projet, nom, index):
    try:
        positions = json.loads(projet.reglage("listes_collecte_position") or "{}")
    except ValueError:
        positions = {}
    positions[nom] = index
    projet.definir_reglages({"listes_collecte_position": json.dumps(positions, ensure_ascii=False)})

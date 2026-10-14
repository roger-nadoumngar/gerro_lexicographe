"""Domaines sémantiques (liste de SIL, environ 1 800 domaines hiérarchisés).

La liste est lue depuis une installation de FLEx (fichiers SemDom.xml ou
LocalizedLists-xx.zip) ou depuis un fichier choisi par l'utilisateur ; elle est
ensuite copiée dans le projet, qui reste ainsi autonome. Chaque domaine garde
son identifiant (guid) officiel : les exports LIFT restent compatibles avec FLEx.
"""

import glob
import json
import os
import zipfile
import xml.etree.ElementTree as ET

from .texte import normaliser

DOSSIERS_FLEX = [
    r"C:\Program Files\SIL\FieldWorks 9\Templates",
    r"C:\Program Files (x86)\SIL\FieldWorks 9\Templates",
    r"C:\Program Files\SIL\FieldWorks 8\Templates",
    "/usr/share/fieldworks/Templates",
    "/usr/lib/fieldworks/Templates",
]


def sources_flex(langue="fr"):
    """Fichiers de domaines trouvés dans les installations de FLEx, le plus adapté
    à la langue d'analyse en premier."""
    trouves = []
    for dossier in DOSSIERS_FLEX:
        if not os.path.isdir(dossier):
            continue
        localise = os.path.join(dossier, f"LocalizedLists-{langue}.zip")
        if os.path.isfile(localise):
            trouves.append(localise)
        semdom = os.path.join(dossier, "SemDom.xml")
        if os.path.isfile(semdom):
            trouves.append(semdom)
        trouves.extend(sorted(set(glob.glob(os.path.join(dossier, "LocalizedLists-*.zip"))) - set(trouves)))
    return trouves


def _ouvrir_xml(chemin):
    if chemin.lower().endswith(".zip"):
        with zipfile.ZipFile(chemin) as z:
            nom = next(n for n in z.namelist() if n.lower().endswith(".xml"))
            with z.open(nom) as f:
                return ET.parse(f).getroot()
    return ET.parse(chemin).getroot()


def _textes(element, balise):
    """{ws: texte} pour <balise><AUni ws=…> ou <balise><AStr ws=…><Run>…"""
    resultat = {}
    if element is None:
        return resultat
    bloc = element.find(balise)
    if bloc is None:
        return resultat
    for enfant in bloc:
        ws = enfant.get("ws")
        texte = "".join(enfant.itertext()).strip()
        if ws and texte:
            resultat[ws] = normaliser(texte)
    return resultat


def lire_liste(chemin):
    """Lit un fichier de domaines au format FLEx. Retourne une liste de dicts
    {guid, code, parent, noms, descriptions, questions}, parents avant enfants."""
    racine = _ouvrir_xml(chemin)
    # SemDom.xml : <SemanticDomainList><CmPossibilityList><Possibilities>…
    # LocalizedLists : <List field="SemanticDomainList"><Possibilities>…
    liste = None
    for candidat in racine.iter():
        if candidat.tag == "SemanticDomainList" or (candidat.tag == "List"
                                                     and candidat.get("field") == "SemanticDomainList"):
            liste = candidat
            break
    if liste is None:
        raise ValueError("Ce fichier ne contient pas de liste de domaines sémantiques.")
    possibilites = next(liste.iter("Possibilities"), None)
    if possibilites is None:
        raise ValueError("La liste de domaines est vide.")

    domaines = []

    def parcourir(conteneur, parent):
        for el in conteneur.findall("CmSemanticDomain"):
            guid = (el.get("guid") or "").lower()
            code = _textes(el, "Abbreviation")
            code = code.get("en") or next(iter(code.values()), "")
            questions = []
            bloc_questions = el.find("Questions")  # pas iter() : il descendrait dans les sous-domaines
            for q in (bloc_questions.findall("CmDomainQ") if bloc_questions is not None else []):
                questions.append({"question": _textes(q, "Question"), "mots": _textes(q, "ExampleWords"),
                                  "phrases": _textes(q, "ExampleSentences")})
            domaines.append({"guid": guid, "code": code, "parent": parent, "noms": _textes(el, "Name"),
                             "descriptions": _textes(el, "Description"), "questions": questions})
            sous = el.find("SubPossibilities")
            if sous is not None:
                parcourir(sous, guid)

    parcourir(possibilites, None)
    if not domaines:
        raise ValueError("La liste de domaines est vide.")
    return domaines


def importer(conn, domaines):
    """Copie (ou met à jour) la liste dans le projet ; les liens existants des sens
    vers les domaines sont conservés. Retourne le nombre de domaines."""
    with conn:
        conn.executemany(
            """INSERT INTO domaines (guid, code, parent_guid, noms, descriptions, questions)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(guid) DO UPDATE SET code=excluded.code, parent_guid=excluded.parent_guid,
                  noms=excluded.noms, descriptions=excluded.descriptions, questions=excluded.questions""",
            [(d["guid"], d["code"], d["parent"], json.dumps(d["noms"], ensure_ascii=False),
              json.dumps(d["descriptions"], ensure_ascii=False), json.dumps(d["questions"], ensure_ascii=False))
             for d in domaines])
    return len(domaines)


LISTE_INTEGREE = ("domaines", "semdom-fr-en.json.gz")
ATTRIBUTION = "Domaines sémantiques : SIL Global (semdom.org), licence CC BY-SA 4.0"


def liste_integree():
    """Liste livrée avec le logiciel (français et anglais), ou [] si elle manque."""
    import gzip
    from .chemins import ressource
    try:
        with gzip.open(ressource(*LISTE_INTEGREE), "rt", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, OSError, ValueError):
        return []


def charger_par_defaut(conn, langue="fr"):
    """Donne au projet une liste de domaines s'il n'en a pas : celle livrée avec le logiciel,
    sinon celle d'une installation de FLEx. Retourne la source utilisée, ou None."""
    if conn.execute("SELECT 1 FROM domaines LIMIT 1").fetchone():
        return None
    liste = liste_integree()
    if liste:
        importer(conn, liste)
        return "liste intégrée"
    return charger_depuis_flex(conn, langue)


def charger_depuis_flex(conn, langue="fr"):
    """Importe la liste trouvée dans FLEx si le projet n'en a pas encore.
    Retourne le chemin utilisé, ou None."""
    if conn.execute("SELECT 1 FROM domaines LIMIT 1").fetchone():
        return None
    for chemin in sources_flex(langue):
        try:
            importer(conn, lire_liste(chemin))
            return chemin
        except (OSError, ValueError, ET.ParseError, zipfile.BadZipFile, StopIteration):
            continue
    return None


def nombre(conn):
    return conn.execute("SELECT COUNT(*) FROM domaines").fetchone()[0]


def nom(noms_json, langue="fr"):
    noms = json.loads(noms_json) if isinstance(noms_json, str) else noms_json
    return noms.get(langue) or noms.get("en") or next(iter(noms.values()), "")


def cle_code(code):
    """« 1.10 » après « 1.9 »."""
    return tuple(int(p) if p.isdigit() else 0 for p in code.split("."))


def arbre(conn, langue="fr"):
    """[(guid, code, nom, parent_guid)] dans l'ordre hiérarchique des codes."""
    lignes = conn.execute("SELECT guid, code, noms, parent_guid FROM domaines").fetchall()
    return sorted(((g, c, nom(n, langue), p) for g, c, n, p in lignes), key=lambda x: cle_code(x[1]))


def details(conn, guid, langue="fr"):
    ligne = conn.execute("SELECT code, noms, descriptions, questions FROM domaines WHERE guid=?",
                         (guid,)).fetchone()
    if not ligne:
        return None
    code, noms, descriptions, questions = ligne
    descriptions = json.loads(descriptions)
    return {"guid": guid, "code": code, "nom": nom(noms, langue),
            "description": descriptions.get(langue) or descriptions.get("en", ""),
            "questions": [{"question": q["question"].get(langue) or q["question"].get("en", ""),
                           "mots": q["mots"].get(langue) or q["mots"].get("en", "")}
                          for q in json.loads(questions)]}


def libelle(conn, guid, langue="fr"):
    ligne = conn.execute("SELECT code, noms FROM domaines WHERE guid=?", (guid,)).fetchone()
    return f"{ligne[0]} {nom(ligne[1], langue)}" if ligne else ""


def chercher(conn, texte, langue="fr", limite=200):
    """Domaines dont le code, le nom ou les mots-exemples contiennent le texte."""
    texte = normaliser(texte).strip().lower()
    resultat = []
    for guid, code, noms, questions in conn.execute("SELECT guid, code, noms, questions FROM domaines"):
        n = nom(noms, langue)
        if (code.startswith(texte) or texte in n.lower()
                or any(texte in (q["mots"].get(langue) or q["mots"].get("en", "")).lower()
                       for q in json.loads(questions))):
            resultat.append((guid, code, n))
    resultat.sort(key=lambda x: cle_code(x[1]))
    return resultat[:limite]


def par_code(conn, code):
    ligne = conn.execute("SELECT guid FROM domaines WHERE code=?", (code,)).fetchone()
    return ligne[0] if ligne else None


def sens_du_domaine(conn, guid):
    """[(entree_id, forme, glose)] des sens classés dans ce domaine."""
    return conn.execute("""SELECT e.id, e.forme, s.glose FROM sens_domaines sd
                           JOIN sens s ON s.id = sd.sens_id JOIN entrees e ON e.id = s.entree_id
                           WHERE sd.domaine_guid=? ORDER BY e.forme""", (guid,)).fetchall()

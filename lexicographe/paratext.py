"""Lecture des projets Paratext, en lecture seule.

Le projet Paratext n'est jamais modifié : ses fichiers sont seulement lus.
* Livres : fichiers USFM du projet, versets rangés dans le corpus du côté choisi
  (langue documentée ou langue d'analyse). Deux projets importés de chaque côté
  donnent un corpus parallèle, verset par verset.
* Glossaire (Lexicon.xml) : mots et morphèmes glosés dans l'outil interlinéaire
  de Paratext, ajoutés au lexique (sens manquants ajoutés aux entrées existantes).
* Rendus des termes bibliques (TermRenderings.xml) : seuls les rendus validés
  (pas les rendus « devinés ») deviennent des entrées, avec la glose et la
  catégorie du terme.
"""

import glob
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from . import lexique, usfm
from .lexique import Entree, Sens
from .texte import normaliser

DOSSIERS_PARATEXT = [r"C:\My Paratext 9 Projects", r"C:\My Paratext 8 Projects"]
DOSSIER_INSTALLATION = [r"C:\Program Files\Paratext 9", r"C:\Program Files (x86)\Paratext 9"]

VERSIFICATIONS = {"1": "originale", "2": "Septante", "3": "Vulgate", "4": "anglaise", "5": "russe protestante",
                  "6": "russe orthodoxe"}
TYPES_LEXEMES = {"Word": "", "Stem": "stem", "Prefix": "prefix", "Suffix": "suffix", "Infix": "infix",
                 "Phrase": "phrase"}
CATEGORIES_TERMES = {"PN": "nom propre", "FA": "nom", "FL": "nom", "RE": "nom", "BE": "nom", "RI": "nom"}


@dataclass
class ProjetParatext:
    nom: str
    dossier: str
    langue: str = ""
    code: str = ""
    nom_complet: str = ""
    versification: str = ""
    suffixe: str = ""
    livres: list[str] = field(default_factory=list)


def dossier_projets_paratext():
    try:
        import winreg
        for cle in (r"SOFTWARE\Paratext\8", r"SOFTWARE\WOW6432Node\Paratext\8"):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, cle) as k:
                    valeur, _ = winreg.QueryValueEx(k, "Settings_Directory")
                    if valeur and os.path.isdir(valeur):
                        return valeur
            except OSError:
                continue
    except ImportError:
        pass
    return next((d for d in DOSSIERS_PARATEXT if os.path.isdir(d)), DOSSIERS_PARATEXT[0])


def _reglages(chemin):
    try:
        racine = ET.parse(chemin).getroot()
    except (ET.ParseError, OSError):
        return None
    return {el.tag: (el.text or "").strip() for el in racine}


def lire_projet(dossier):
    """ProjetParatext d'un dossier, ou None si ce n'est pas un projet Paratext."""
    r = _reglages(os.path.join(dossier, "Settings.xml"))
    if r is None:
        return None
    p = ProjetParatext(nom=r.get("Name") or os.path.basename(dossier), dossier=dossier,
                       langue=r.get("Language", ""), code=(r.get("LanguageIsoCode", "") or "").split(":")[0],
                       nom_complet=r.get("FullName", ""), versification=r.get("Versification", ""),
                       suffixe=r.get("FileNamePostPart", ""))
    p.livres = sorted(fichiers_livres(p), key=lambda c: usfm.LIVRES.index(c) if c in usfm.LIVRES else 999)
    return p


def lister_projets(dossier=None):
    dossier = dossier or dossier_projets_paratext()
    if not os.path.isdir(dossier):
        return []
    projets = []
    for nom in sorted(os.listdir(dossier), key=str.lower):
        chemin = os.path.join(dossier, nom)
        if os.path.isfile(os.path.join(chemin, "Settings.xml")):
            p = lire_projet(chemin)
            if p:
                projets.append(p)
    return projets


def fichiers_livres(projet):
    """{code du livre: chemin} ; le code est lu dans la ligne \\id de chaque fichier."""
    motif = "*" + projet.suffixe if projet.suffixe else "*.SFM"
    resultat = {}
    for chemin in glob.glob(os.path.join(projet.dossier, motif)):
        if not os.path.isfile(chemin) or chemin.upper().endswith(".BAK"):
            continue
        try:
            with open(chemin, encoding="utf-8-sig", errors="replace") as f:
                debut = f.read(300)
        except OSError:
            continue
        m = re.search(r"\\id\s+(\w{3})", debut)
        if m:
            resultat[m.group(1).upper()] = chemin
    return resultat


# -- import des livres -------------------------------------------------------------------

@dataclass
class Rapport:
    livres: int = 0
    versets: int = 0
    nouveaux: int = 0
    completes: int = 0
    entrees: int = 0
    sens: int = 0
    termes: int = 0
    avertissements: list[str] = field(default_factory=list)

    def resume(self):
        lignes = []
        if self.livres:
            lignes.append(f"{self.livres} livre(s), {self.versets} versets ({self.nouveaux} nouveaux, "
                          f"{self.completes} complétés).")
        if self.entrees or self.sens or self.termes:
            lignes.append(f"Lexique : {self.entrees} entrée(s) créée(s), {self.sens} sens ajouté(s) "
                          f"(dont {self.termes} rendu(s) de termes bibliques).")
        if not lignes:
            lignes.append("Rien à importer.")
        if self.avertissements:
            lignes.append("Avertissements :")
            lignes.extend("  • " + a for a in self.avertissements[:30])
        return "\n".join(lignes)


def versification_du_corpus(projet_lex):
    return projet_lex.reglage("versification_paratext")


def importer_livres(projet_lex, projet_pt, livres, cote, rapport=None):
    """Range les versets des livres choisis dans le corpus, du côté `cote`
    ('vernaculaire' ou 'analyse')."""
    r = rapport or Rapport()
    fichiers = fichiers_livres(projet_pt)
    precedente = projet_lex.reglage("versification_paratext")
    if precedente and projet_pt.versification and precedente != projet_pt.versification:
        r.avertissements.append(
            f"Versification {VERSIFICATIONS.get(projet_pt.versification, projet_pt.versification)} différente de "
            f"celle déjà importée ({VERSIFICATIONS.get(precedente, precedente)}) : certains numéros de versets "
            "peuvent ne pas correspondre entre les deux langues.")
    vides = []
    with projet_lex.en_lot():
        for code in livres:
            chemin = fichiers.get(code)
            if not chemin:
                r.avertissements.append(f"Livre {code} absent du projet {projet_pt.nom}.")
                continue
            versets, _ = usfm.lire_usfm(chemin, code)
            if not versets:
                vides.append(code)
                continue
            nouveaux, completes = usfm.importer(projet_lex, versets, cote, f"Paratext {projet_pt.nom}")
            r.livres += 1
            r.versets += len(versets)
            r.nouveaux += nouveaux
            r.completes += completes
    if vides:
        r.avertissements.append(f"{len(vides)} livre(s) sans texte dans {projet_pt.nom} (seulement des numéros de "
                                f"versets) : {', '.join(vides[:12])}{'…' if len(vides) > 12 else ''}.")
    if projet_pt.versification and not precedente:
        projet_lex.definir_reglages({"versification_paratext": projet_pt.versification})
    return r


# -- glossaire et termes bibliques ------------------------------------------------------------

def _ajouter_sens(conn, forme, glose, type_morph="", categorie_id=None, definition="", note="", exemple=None,
                  statut="à vérifier", r=None):
    """Ajoute le sens à l'entrée de même forme (et même type) s'il n'y est pas déjà ;
    crée l'entrée sinon. Retourne True si quelque chose a été ajouté."""
    forme = normaliser(forme).strip()
    glose = normaliser(glose).strip()
    if not forme or not glose:
        return False
    for eid in lexique.chercher_par_forme(conn, forme):
        e = lexique.lire_entree(conn, eid)
        if (e.type_morph or "") != (type_morph or ""):
            continue
        if any(s.glose.strip().lower() == glose.lower() for s in e.sens):
            return False
        vide = next((s for s in e.sens if not s.glose and not s.definition), None)
        nouveau = vide or Sens()
        nouveau.glose, nouveau.definition = glose, nouveau.definition or definition
        nouveau.categorie_id = nouveau.categorie_id or categorie_id
        if exemple and not nouveau.exemples:
            nouveau.exemples = [exemple]
        if vide is None:
            e.sens.append(nouveau)
        if note and note not in e.notes:
            e.notes = "\n".join(x for x in (e.notes, note) if x)
        lexique.enregistrer_entree(conn, e)
        if r:
            r.sens += 1
        return True
    lexique.enregistrer_entree(conn, Entree(forme=forme, type_morph=type_morph, statut=statut, notes=note,
                                            sens=[Sens(glose=glose, definition=definition, categorie_id=categorie_id,
                                                       exemples=[exemple] if exemple else [])]))
    if r:
        r.entrees += 1
        r.sens += 1
    return True


def importer_glossaire(projet_lex, projet_pt, rapport=None):
    """Mots et morphèmes du glossaire interlinéaire de Paratext (Lexicon.xml)."""
    r = rapport or Rapport()
    chemin = os.path.join(projet_pt.dossier, "Lexicon.xml")
    if not os.path.isfile(chemin):
        r.avertissements.append(f"Pas de glossaire (Lexicon.xml) dans {projet_pt.nom}.")
        return r
    langue = projet_lex.reglage("langue_analyse_code") or "fr"
    racine = ET.parse(chemin).getroot()
    with projet_lex.en_lot():
        for item in racine.iter("item"):
            lexeme = item.find("Lexeme")
            if lexeme is None or not lexeme.get("Form"):
                continue
            type_morph = TYPES_LEXEMES.get(lexeme.get("Type", "Word"), "")
            forme = lexeme.get("Form")
            if type_morph in ("prefix",):
                forme += "-"
            elif type_morph in ("suffix",):
                forme = "-" + forme
            toutes = list(item.iter("Gloss"))
            # gloses dans la langue d'analyse du projet ; à défaut, celles qui existent
            for gl in [g for g in toutes if g.get("Language") == langue] or toutes:
                _ajouter_sens(projet_lex.conn, forme, gl.text or "", type_morph,
                              note=f"Glossaire Paratext ({projet_pt.nom})", r=r)
    return r


def _gloses_termes(projet_pt):
    """{id du terme: (glose, catégorie)} : liste du projet, gloses françaises de Paratext si disponibles."""
    gloses = {}
    liste = os.path.join(projet_pt.dossier, "ProjectBiblicalTerms.xml")
    if os.path.isfile(liste):
        for t in ET.parse(liste).getroot().iter("Term"):
            gloses[t.get("Id")] = ((t.findtext("Gloss") or "").strip(), (t.findtext("Category") or "").strip())
    for dossier in DOSSIER_INSTALLATION:
        fr = os.path.join(dossier, "Terms", "Lists", "BiblicalTermsFr.xml")
        if os.path.isfile(fr):
            for loc in ET.parse(fr).getroot().iter("Localization"):
                if loc.get("Id") in gloses and loc.get("Gloss"):
                    glose = loc.get("Gloss").split(" - ")[0].strip()
                    gloses[loc.get("Id")] = (glose, gloses[loc.get("Id")][1])
            break
    return gloses


def importer_termes(projet_lex, projet_pt, rapport=None):
    """Rendus validés des termes bibliques : une entrée (ou un sens) par rendu."""
    r = rapport or Rapport()
    chemin = os.path.join(projet_pt.dossier, "TermRenderings.xml")
    if not os.path.isfile(chemin):
        r.avertissements.append(f"Pas de rendus de termes bibliques dans {projet_pt.nom}.")
        return r
    gloses = _gloses_termes(projet_pt)
    conn = projet_lex.conn
    tok = projet_lex.tokeniseur_vern
    with projet_lex.en_lot():
        for t in ET.parse(chemin).getroot().iter("TermRendering"):
            texte = (t.findtext("Renderings") or "").strip()
            if not texte or t.get("Guess") == "true":
                continue
            glose, categorie = gloses.get(t.get("Id"), ("", ""))
            glose = glose or t.get("Id")
            cat_id = lexique.categorie_par_nom(conn, CATEGORIES_TERMES[categorie], creer=True) \
                if categorie in CATEGORIES_TERMES else None
            note = f"Rendu validé dans Paratext ({projet_pt.nom}) du terme biblique « {t.get('Id')} »."
            for rendu in texte.split("||"):
                # « * » est le joker de Paratext (« Betilehem* » couvre Betilehem, Betilehemje…)
                forme = rendu.replace("*", "").strip()
                if not forme or len(tok.mots(forme)) == 0:
                    continue
                type_morph = "phrase" if len(forme.split()) > 1 else ""
                if _ajouter_sens(conn, forme, glose, type_morph, cat_id, note=note, r=r):
                    r.termes += 1
    return r

"""Import direct d'un projet FLEx (fichier .fwdata), en lecture seule.

Le fichier FLEx n'est jamais modifié : il est seulement lu. Règles d'import :
* les identifiants (guid) de FLEx sont conservés : réimporter le même projet met
  à jour les entrées et les textes au lieu de les dupliquer ;
* langue documentée = première langue vernaculaire du projet FLEx, langue
  d'analyse = celle du projet si FLEx l'a, sinon la première langue d'analyse
  de FLEx ;
* les sous-sens deviennent des sens à la suite de leur sens parent (signalé
  dans les notes) ; les champs de notes de FLEx sont regroupés dans les notes
  avec leur intitulé ;
* une variante de FLEx (entrée séparée) reste une entrée, reliée à son entrée
  principale (« variante de ») et inscrite dans les variantes de celle-ci ;
* une analyse interlinéaire n'est reprise que si ses morphèmes reconstituent
  exactement le mot (sinon elle est signalée et laissée de côté).
"""

import os
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from . import interlineaire as il
from . import lexique, textes
from .lexique import Entree, Exemple, Sens, Variante
from .projet import copier_medias
from .texte import normaliser

DOSSIER_FLEX_DEFAUT = r"C:\ProgramData\SIL\FieldWorks\Projects"

CLASSES = {
    "LangProject", "LexDb", "LexEntry", "LexSense", "MoStemAllomorph", "MoAffixAllomorph", "MoStemMsa",
    "MoInflAffMsa", "MoDerivAffMsa", "MoUnclassifiedAffixMsa", "PartOfSpeech", "LexExampleSentence",
    "CmTranslation", "LexEntryRef", "MoMorphType", "LexEntryType", "LexPronunciation", "CmSemanticDomain",
    "LexRefType", "LexReference", "CmPicture", "CmFile", "CmMedia", "PhEnvironment", "CmPossibility",
    "Text", "StText", "StTxtPara", "Segment", "Note", "WfiWordform", "WfiAnalysis", "WfiMorphBundle",
    "WfiGloss", "PunctuationForm",
}

TYPES_MORPH_FLEX = set(lexique.TYPES_MORPH)

NOTES_SENS = [("GeneralNote", "Note"), ("UsageNote", "Usage"), ("EncyclopedicInfo", "Encyclopédie"),
              ("AnthroNote", "Anthropologie"), ("SemanticsNote", "Sémantique"), ("GrammarNote", "Grammaire"),
              ("PhonologyNote", "Phonologie"), ("DiscourseNote", "Discours"),
              ("SocioLinguisticsNote", "Sociolinguistique"), ("Restrictions", "Restrictions"),
              ("ScientificName", "Nom scientifique"), ("Source", "Source"), ("Bibliography", "Bibliographie")]
NOTES_ENTREE = [("Comment", "Note"), ("LiteralMeaning", "Sens littéral"), ("SummaryDefinition", "Définition résumée"),
                ("Restrictions", "Restrictions"), ("Bibliography", "Bibliographie")]

VARIANTES_FLEX = {"free variant": "variante libre", "dialectal variant": "variante dialectale",
                  "spelling variant": "variante orthographique", "irregularly inflected form": "forme irrégulière",
                  "plural": "forme irrégulière", "past": "forme irrégulière"}
COMPLEXES_FLEX = {"compound": "composé", "derivative": "dérivé", "idiom": "expression idiomatique",
                  "phrasal verb": "locution verbale", "contraction": "contraction", "reduplication": "redoublement"}
RELATIONS_FLEX = {"synonyms": "synonyme", "synonym": "synonyme", "antonym": "antonyme", "antonyms": "antonyme",
                  "compare": "voir aussi", "calendar": "même champ lexical", "part": "partie de (méronyme)",
                  "whole": "partie de (méronyme)", "generic": "terme générique (hyperonyme)",
                  "specific": "terme spécifique (hyponyme)"}
# FLEx : types de relations asymétriques ou arborescentes (le premier membre est la tête)
ASYMETRIQUES = {2, 3, 7, 8, 12, 13}


@dataclass
class ProjetFlex:
    nom: str
    chemin: str
    taille: int
    modifie: float
    ouvert_dans_flex: bool


def dossier_projets_flex():
    """Dossier des projets FLEx : celui déclaré dans le registre, sinon le dossier par défaut."""
    try:
        import winreg
        for racine in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for cle in (r"SOFTWARE\SIL\FieldWorks\9", r"SOFTWARE\WOW6432Node\SIL\FieldWorks\9"):
                try:
                    with winreg.OpenKey(racine, cle) as k:
                        valeur, _ = winreg.QueryValueEx(k, "ProjectsDir")
                        if valeur and os.path.isdir(valeur):
                            return valeur
                except OSError:
                    continue
    except ImportError:
        pass
    return DOSSIER_FLEX_DEFAUT


def lister_projets_flex(dossier=None):
    dossier = dossier or dossier_projets_flex()
    resultat = []
    if not os.path.isdir(dossier):
        return resultat
    for nom in sorted(os.listdir(dossier)):
        chemin = os.path.join(dossier, nom, nom + ".fwdata")
        if os.path.isfile(chemin):
            stat = os.stat(chemin)
            resultat.append(ProjetFlex(nom, chemin, stat.st_size, stat.st_mtime,
                                       os.path.exists(chemin + ".lock")))
    return resultat


# -- lecture du fichier ------------------------------------------------------------------

class DonneesFlex:
    """Objets utiles d'un fichier .fwdata, indexés par guid (minuscules)."""

    def __init__(self, chemin):
        self.chemin = chemin
        self.dossier = os.path.dirname(os.path.abspath(chemin))
        self.objets = {}
        self.par_classe = defaultdict(list)
        for _, el in ET.iterparse(chemin, events=("end",)):
            if el.tag != "rt":
                continue
            classe = el.get("class")
            if classe in CLASSES:
                guid = el.get("guid", "").lower()
                self.objets[guid] = el
                self.par_classe[classe].append(el)
            else:
                el.clear()
        projet = (self.par_classe.get("LangProject") or [None])[0]
        self.vern = self._liste_ws(projet, "CurVernWss")
        self.analyse = self._liste_ws(projet, "CurAnalysisWss")
        self.fichiers_lies = os.path.join(self.dossier, "LinkedFiles")
        if projet is not None:
            dossier = self.texte_uni(projet, "LinkedFilesRootDir")
            if dossier:
                self.fichiers_lies = dossier.replace("%proj%", self.dossier)

    @staticmethod
    def _liste_ws(el, champ):
        if el is None:
            return []
        bloc = el.find(champ)
        uni = bloc.find("Uni") if bloc is not None else None
        return (uni.text or "").split() if uni is not None else []

    def get(self, guid):
        return self.objets.get((guid or "").lower())

    @staticmethod
    def refs(el, champ):
        bloc = el.find(champ) if el is not None else None
        return [o.get("guid", "").lower() for o in bloc.findall("objsur")] if bloc is not None else []

    def ref(self, el, champ):
        r = self.refs(el, champ)
        return r[0] if r else None

    @staticmethod
    def multi(el, champ):
        """{ws: texte} d'un champ multilingue (AUni ou AStr)."""
        resultat = {}
        bloc = el.find(champ) if el is not None else None
        if bloc is None:
            return resultat
        for enfant in bloc:
            if enfant.tag in ("AUni", "AStr"):
                texte = "".join(enfant.itertext()).strip()
                if texte:
                    resultat[enfant.get("ws", "")] = normaliser(texte)
        return resultat

    @staticmethod
    def texte_str(el, champ, brut=False):
        """Texte d'un champ Str (contenu de paragraphe), toutes langues confondues.
        `brut` : sans normalisation Unicode (les positions des segments FLEx s'y rapportent)."""
        bloc = el.find(champ) if el is not None else None
        if bloc is None:
            return ""
        s = bloc.find("Str")
        texte = "".join(s.itertext()) if s is not None else ""
        return texte if brut else normaliser(texte)

    @staticmethod
    def texte_uni(el, champ):
        bloc = el.find(champ) if el is not None else None
        uni = bloc.find("Uni") if bloc is not None else None
        return normaliser(uni.text or "") if uni is not None else ""

    @staticmethod
    def val(el, champ):
        bloc = el.find(champ) if el is not None else None
        return bloc.get("val") if bloc is not None else None

    def choisir(self, textes_ws, preferees):
        for ws in preferees:
            if ws in textes_ws:
                return textes_ws[ws]
        return next(iter(textes_ws.values()), "")

    def nom(self, el, preferees=("fr", "en")):
        return self.choisir(self.multi(el, "Name"), list(preferees))


# -- import ----------------------------------------------------------------------------------

@dataclass
class Rapport:
    creees: int = 0
    mises_a_jour: int = 0
    sens: int = 0
    categories: int = 0
    domaines: int = 0
    variantes: int = 0
    composants: int = 0
    relations: int = 0
    medias: int = 0
    textes: int = 0
    phrases: int = 0
    analyses: int = 0
    formes_sous_jacentes: int = 0
    langue_vern: str = ""
    langue_analyse: str = ""
    avertissements: list[str] = field(default_factory=list)

    def resume(self):
        lignes = [f"Lexique : {self.creees} entrée(s) créée(s), {self.mises_a_jour} mise(s) à jour, {self.sens} sens.",
                  f"{self.categories} catégorie(s), {self.domaines} domaine(s) ajouté(s), {self.variantes} variante(s), "
                  f"{self.composants} composant(s), {self.relations} relation(s), {self.medias} fichier(s) audio/image.",
                  f"Textes : {self.textes} texte(s), {self.phrases} phrase(s), {self.analyses} analyse(s) de mots"
                  + (f" (dont {self.formes_sous_jacentes} notée(s) en formes sous-jacentes)."
                     if self.formes_sous_jacentes else "."),
                  f"Langue documentée : {self.langue_vern} ; langue d'analyse : {self.langue_analyse}."]
        if self.avertissements:
            lignes.append("Avertissements :")
            lignes.extend("  • " + a for a in self.avertissements[:30])
            if len(self.avertissements) > 30:
                lignes.append(f"  … et {len(self.avertissements) - 30} autre(s).")
        return "\n".join(lignes)


def langues(chemin):
    """(code vernaculaire, code d'analyse) du projet FLEx, pour créer un projet."""
    d = DonneesFlex(chemin)
    vern = (d.vern or ["und"])[0].split("-")[0]
    analyse = (d.analyse or ["fr"])[0].split("-")[0]
    return vern, analyse


def importer(projet, chemin, statut="à vérifier", avec_textes=True):
    """Importe le projet FLEx dans le projet. Retourne un Rapport."""
    if statut not in lexique.STATUTS:
        raise ValueError(statut)
    with projet.en_lot():
        return _importer(projet, chemin, statut, avec_textes)


def _importer(projet, chemin, statut, avec_textes):
    d = DonneesFlex(chemin)
    conn = projet.conn
    r = Rapport()
    if os.path.exists(chemin + ".lock"):
        r.avertissements.append("FLEx semble ouvert sur ce projet : les modifications non enregistrées dans FLEx "
                                "ne sont pas dans le fichier lu.")
    code_vern = projet.reglage("langue_vern_code")
    vern = [ws for ws in d.vern if ws.split("-")[0] == code_vern] or d.vern
    vern = vern + [ws for ws in d.vern if ws not in vern]
    code_a = projet.reglage("langue_analyse_code")
    analyse = [ws for ws in d.analyse if ws.split("-")[0] == code_a] + [ws for ws in d.analyse
                                                                      if ws.split("-")[0] != code_a]
    analyse = analyse or ["fr", "en"]
    r.langue_vern, r.langue_analyse = (vern or ["?"])[0], analyse[0]
    if code_vern and d.vern and not any(ws.split("-")[0] == code_vern for ws in d.vern):
        r.avertissements.append(f"Le projet FLEx est en « {d.vern[0]} », ce projet en « {code_vern} ».")
    if code_a and d.analyse and analyse[0].split("-")[0] != code_a:
        r.avertissements.append(f"Aucune langue d'analyse « {code_a} » dans FLEx : textes d'analyse pris en « {analyse[0]} ».")

    def vtexte(el, champ):
        return d.choisir(d.multi(el, champ), vern)

    def atexte(el, champ):
        return d.choisir(d.multi(el, champ), analyse)

    # catégories (avec leur hiérarchie)
    categories = {}

    def categorie(guid):
        if not guid or guid in categories:
            return categories.get(guid)
        pos = d.get(guid)
        if pos is None or pos.get("class") != "PartOfSpeech":
            return None
        parent = pos.get("ownerguid", "").lower()
        parent_id = categorie(parent) if d.get(parent) is not None and d.get(parent).get("class") == "PartOfSpeech" else None
        nom = d.choisir(d.multi(pos, "Name"), analyse + ["en"]) or "?"
        abrev = d.choisir(d.multi(pos, "Abbreviation"), analyse + ["en"])
        existant = lexique.categorie_par_nom(conn, nom)
        if existant is None:
            existant = lexique.ajouter_categorie(conn, nom, abrev, parent_id)
            r.categories += 1
        categories[guid] = existant
        return existant

    def categorie_de_msa(guid):
        msa = d.get(guid)
        if msa is None:
            return None
        for champ in ("PartOfSpeech", "FromPartOfSpeech", "ToPartOfSpeech"):
            pos = d.ref(msa, champ)
            if pos:
                return categorie(pos)
        return None

    # domaines sémantiques : ceux du projet FLEx qui manquent (les listes FLEx partagent les guids officiels)
    existants = {g for (g,) in conn.execute("SELECT guid FROM domaines")}
    nouveaux = []
    for dom in d.par_classe.get("CmSemanticDomain", []):
        guid = dom.get("guid", "").lower()
        if guid in existants:
            continue
        parent = dom.get("ownerguid", "").lower()
        parent = parent if d.get(parent) is not None and d.get(parent).get("class") == "CmSemanticDomain" else None
        code = d.choisir(d.multi(dom, "Abbreviation"), ["en"] + analyse)
        nouveaux.append((guid, code, parent, d.multi(dom, "Name"), d.multi(dom, "Description")))
    if nouveaux:
        import json
        # FLEx range les objets par guid : les parents doivent être insérés avant leurs sous-domaines
        nouveaux.sort(key=lambda x: (x[1].count("."), x[1]))
        with conn:
            conn.executemany("""INSERT OR IGNORE INTO domaines (guid, code, parent_guid, noms, descriptions, questions)
                                VALUES (?, ?, ?, ?, ?, '[]')""",
                             [(g, c, p, json.dumps(n, ensure_ascii=False), json.dumps(ds, ensure_ascii=False))
                              for g, c, p, n, ds in nouveaux])
        r.domaines = len(nouveaux)
    domaines_connus = {g for (g,) in conn.execute("SELECT guid FROM domaines")}

    def type_morph(allomorphe):
        mt = d.get(d.ref(allomorphe, "MorphType"))
        nom = d.choisir(d.multi(mt, "Name"), ["en"]).lower() if mt is not None else ""
        return nom if nom in TYPES_MORPH_FLEX else ""

    def notes_de(el, champs):
        morceaux = []
        for champ, libelle in champs:
            t = atexte(el, champ) or vtexte(el, champ)
            if t:
                morceaux.append(f"{libelle} : {t}")
        return morceaux

    def sens_de(guid, chemin_sens, notes):
        s_el = d.get(guid)
        if s_el is None:
            return []
        sens = Sens(glose=atexte(s_el, "Gloss"), definition=atexte(s_el, "Definition"),
                    categorie_id=categorie_de_msa(d.ref(s_el, "MorphoSyntaxAnalysis")))
        sens.domaines = [g for g in d.refs(s_el, "SemanticDomains") if g in domaines_connus]
        for ex_guid in d.refs(s_el, "Examples"):
            ex = d.get(ex_guid)
            if ex is None:
                continue
            traduction = ""
            for tr in d.refs(ex, "Translations"):
                traduction = atexte(d.get(tr), "Translation")
                if traduction:
                    break
            sens.exemples.append(Exemple(vtexte(ex, "Example"), traduction, d.texte_uni(ex, "Reference")))
        sens.flex_guid = guid
        sens.flex_images = d.refs(s_el, "Pictures")
        for note in notes_de(s_el, NOTES_SENS):
            notes.append(f"Sens {chemin_sens} — {note}")
        resultat = [sens]
        for i, sous in enumerate(d.refs(s_el, "Senses"), start=1):
            sous_sens = sens_de(sous, f"{chemin_sens}.{i}", notes)
            if sous_sens:
                notes.append(f"Sens {chemin_sens}.{i} : sous-sens de {chemin_sens} dans FLEx.")
            resultat.extend(sous_sens)
        return resultat

    # -- 1er passage : les entrées ---------------------------------------------------------
    guids = dict(conn.execute("SELECT guid, id FROM entrees"))
    entree_par_guid, sens_par_guid, forme_par_entree, medias = {}, {}, {}, []
    for e_el in d.par_classe.get("LexEntry", []):
        guid = e_el.get("guid", "").lower()
        allo = d.get(d.ref(e_el, "LexemeForm"))
        forme = vtexte(allo, "Form") if allo is not None else ""
        citation = vtexte(e_el, "CitationForm")
        if not forme:
            forme = citation
        if not forme:
            r.avertissements.append(f"Entrée FLEx sans forme ignorée ({guid}).")
            continue
        notes = notes_de(e_el, NOTES_ENTREE)
        entree = Entree(forme=forme, forme_citation=citation if citation != forme else "", guid=guid, statut=statut,
                        type_morph=type_morph(allo) if allo is not None else "")
        dates = d.val(e_el, "DateCreated")
        if dates:
            entree.date_creation = dates.replace(" ", "T").split(".")[0]
        prononciations = []
        for p in d.refs(e_el, "Pronunciations"):
            p_el = d.get(p)
            t = d.choisir(d.multi(p_el, "Form"), [ws for ws in d.vern if "fonipa" in ws] + vern)
            if t:
                prononciations.append(t)
            for m in d.refs(p_el, "MediaFiles"):
                fichier = d.get(d.ref(d.get(m), "MediaFile"))
                if fichier is not None:
                    medias.append((guid, None, d.texte_uni(fichier, "InternalPath"), "prononciation"))
        entree.prononciation = prononciations[0] if prononciations else ""
        for a in d.refs(e_el, "AlternateForms"):
            a_el = d.get(a)
            af = vtexte(a_el, "Form") if a_el is not None else ""
            if af:
                envs = [d.texte_str(d.get(env), "StringRepresentation") for env in d.refs(a_el, "PhoneEnv")]
                entree.variantes.append(Variante(af, "allomorphe", environnement=" ; ".join(e for e in envs if e)))
        for i, s in enumerate(d.refs(e_el, "Senses"), start=1):
            entree.sens.extend(sens_de(s, str(i), notes))
        if not entree.sens:
            entree.sens.append(Sens())
        entree.notes = "\n".join(notes)
        existant = guids.get(guid)
        if existant:
            entree.id = existant
            ancien = lexique.lire_entree(conn, existant)
            entree.statut, entree.date_creation = ancien.statut, ancien.date_creation
            # garder les identifiants des sens : les analyses interlinéaires qui s'y rattachent restent liées
            for nouveau, vieux in zip(entree.sens, ancien.sens):
                nouveau.id = vieux.id
        try:
            eid = lexique.enregistrer_entree(conn, entree)
        except ValueError as e:
            r.avertissements.append(f"« {forme} » : {e}")
            continue
        if existant:
            r.mises_a_jour += 1
        else:
            r.creees += 1
        r.sens += len(entree.sens)
        entree_par_guid[guid] = eid
        forme_par_entree[eid] = forme
        for s in entree.sens:
            if getattr(s, "flex_guid", None):    # le sens vide ajouté à une entrée sans sens n'en a pas
                sens_par_guid[s.flex_guid] = (eid, s.id)
            for image in getattr(s, "flex_images", []):
                fichier = d.get(d.ref(d.get(image), "PictureFile"))
                if fichier is not None:
                    medias.append((guid, s.id, d.texte_uni(fichier, "InternalPath"), "image"))

    def entree_de(guid):
        """Entrée désignée par un guid d'entrée ou de sens."""
        if guid in entree_par_guid:
            return entree_par_guid[guid]
        if guid in sens_par_guid:
            return sens_par_guid[guid][0]
        return None

    # -- 2e passage : variantes, formes complexes, relations, médias -------------------------------
    variantes_a_ajouter = defaultdict(list)
    composants = {}
    for ref in d.par_classe.get("LexEntryRef", []):
        proprietaire = entree_par_guid.get(ref.get("ownerguid", "").lower())
        cibles = [entree_de(g) for g in d.refs(ref, "ComponentLexemes")]
        cibles = [c for c in cibles if c and c != proprietaire]
        if not proprietaire or not cibles:
            continue
        if d.val(ref, "RefType") == "1":   # forme complexe
            types = [d.nom(d.get(t), ["en"]).lower() for t in d.refs(ref, "ComplexEntryTypes")]
            libelle = next((COMPLEXES_FLEX.get(t, t) for t in types if t), "")
            composants[proprietaire] = (cibles, libelle)
        else:                               # variante
            types = [d.nom(d.get(t), ["en"]).lower() for t in d.refs(ref, "VariantEntryTypes")]
            type_v = next((VARIANTES_FLEX[t] for t in types if t in VARIANTES_FLEX), "variante libre")
            for principale in cibles:
                variantes_a_ajouter[principale].append(Variante(forme_par_entree[proprietaire], type_v))
                if lexique.ajouter_relation(conn, proprietaire, principale, "variante de"):
                    r.relations += 1
    for eid in set(variantes_a_ajouter) | set(composants):
        entree = lexique.lire_entree(conn, eid)
        connues = {(v.forme, v.type) for v in entree.variantes}
        for v in variantes_a_ajouter.get(eid, []):
            if (v.forme, v.type) not in connues:
                entree.variantes.append(v)
                connues.add((v.forme, v.type))
                r.variantes += 1
        if eid in composants:
            entree.composants, entree.type_forme_complexe = composants[eid][0], composants[eid][1] or entree.type_forme_complexe
            r.composants += len(entree.composants)
        lexique.enregistrer_entree(conn, entree)

    for lr in d.par_classe.get("LexReference", []):
        type_el = d.get(lr.get("ownerguid", ""))
        if type_el is None:
            continue
        nom = d.nom(type_el, ["en"]) or "relation"
        nom_inverse = d.choisir(d.multi(type_el, "ReverseName"), ["en"]) or nom
        membres = [entree_de(g) for g in d.refs(lr, "Targets")]
        membres = [m for m in dict.fromkeys(membres) if m]
        if len(membres) < 2:
            continue
        mapping = int(d.val(type_el, "MappingType") or 0)
        if mapping in ASYMETRIQUES:
            tete, autres = membres[0], membres[1:]
            paires = [(tete, a, nom) for a in autres] + [(a, tete, nom_inverse) for a in autres]
        else:
            paires = [(a, b, nom) for a in membres for b in membres if a != b]
        for a, b, typ in paires:
            if lexique.ajouter_relation(conn, a, b, RELATIONS_FLEX.get(typ.lower(), typ)):
                r.relations += 1

    for guid, sens_id, chemin_relatif, role in medias:
        if not chemin_relatif:
            continue
        candidats = [chemin_relatif] if os.path.isabs(chemin_relatif) else [
            os.path.join(d.fichiers_lies, chemin_relatif), os.path.join(d.dossier, chemin_relatif)]
        fichier = next((c for c in candidats if os.path.isfile(c)), None)
        if not fichier:
            r.avertissements.append(f"Fichier introuvable : {chemin_relatif}")
            continue
        eid = entree_par_guid.get(guid)
        if eid and not any(m[4] == os.path.basename(fichier) for m in lexique.medias_de(conn, eid)):
            lexique.lier_media(conn, eid, copier_medias(projet, fichier), role, "importé de FLEx", sens_id)
            r.medias += 1

    if avec_textes:
        _importer_textes(projet, d, vern, analyse, sens_par_guid, entree_par_guid, r)
    return r


def _importer_textes(projet, d, vern, analyse, sens_par_guid, entree_par_guid, r):
    conn = projet.conn
    tokeniseur = projet.tokeniseur_vern
    marqueurs = {notes.rsplit("(FLEx ", 1)[1].split(")", 1)[0]: code
                 for code, notes in conn.execute("SELECT code, notes FROM textes WHERE notes LIKE '%(FLEx %'")}
    occurrences = []       # (ref, position, forme, guid d'analyse FLEx)
    for t_el in d.par_classe.get("Text", []):
        guid = t_el.get("guid", "").lower()
        st = d.get(d.ref(t_el, "Contents"))
        if st is None:
            continue
        phrases_texte = []
        for p in d.refs(st, "Paragraphs"):
            para = d.get(p)
            if para is None:
                continue
            contenu = d.texte_str(para, "Contents", brut=True)
            segments = [d.get(s) for s in d.refs(para, "Segments")]
            segments = [s for s in segments if s is not None]
            debuts = [int(d.val(s, "BeginOffset") or 0) for s in segments]
            if not segments and contenu.strip():
                phrases_texte.append((normaliser(contenu).strip(), "", "", "", []))
            for i, seg in enumerate(segments):
                fin = debuts[i + 1] if i + 1 < len(segments) else len(contenu)
                texte_seg = normaliser(contenu[debuts[i]:fin]).strip()
                if not texte_seg:
                    continue
                notes = [d.choisir(d.multi(d.get(n), "Content"), analyse) for n in d.refs(seg, "Notes")]
                analyses = []
                for a in d.refs(seg, "Analyses"):
                    objet = d.get(a)
                    if objet is not None and objet.get("class") != "PunctuationForm":
                        analyses.append(a)
                phrases_texte.append((texte_seg, d.choisir(d.multi(seg, "FreeTranslation"), analyse),
                                      d.choisir(d.multi(seg, "LiteralTranslation"), analyse),
                                      " ; ".join(n for n in notes if n), analyses))
        if not phrases_texte:
            continue
        code = marqueurs.get(guid) or textes.nouveau_code(conn)
        titre = d.choisir(d.multi(t_el, "Name"), analyse + vern) or code
        genres = [d.nom(d.get(g), analyse + ["en"]) for g in d.refs(t_el, "Genres")]
        meta = textes.Texte(code=code, titre=titre, genre=", ".join(g for g in genres if g),
                            date=(d.val(t_el, "DateCreated") or "").split(" ")[0],
                            notes=f"Importé de FLEx ({os.path.basename(d.chemin)}) (FLEx {guid})")
        with conn:
            conn.execute("DELETE FROM phrases WHERE ref LIKE ?", (code + " %",))
            for n, (texte_seg, libre, litterale, notes, analyses) in enumerate(phrases_texte, start=1):
                ref = f"{code} {n}"
                conn.execute("""INSERT INTO phrases (ref, vernaculaire, analyse, source, traduction_litterale, notes)
                                VALUES (?, ?, ?, ?, ?, ?)""",
                             (ref, texte_seg, libre or None, f"FLEx {code}", litterale or None, notes or None))
                mots = tokeniseur.mots(texte_seg)
                if len(mots) == len(analyses):  # alignement sûr seulement si le découpage coïncide
                    occurrences.extend((ref, pos, mots[pos], analyses[pos]) for pos in range(len(mots)))
        textes.enregistrer_meta(conn, meta)
        r.textes += 1
        r.phrases += len(phrases_texte)

    # analyses interlinéaires : la plus fréquente d'une forme devient l'analyse par défaut
    def analyse_flex(guid):
        objet = d.get(guid)
        if objet is None:
            return None
        glose = ""
        if objet.get("class") == "WfiGloss":
            glose = d.choisir(d.multi(objet, "Form"), analyse)
            objet = d.get(objet.get("ownerguid", ""))
        if objet is None or objet.get("class") != "WfiAnalysis":
            return None
        morphemes = []
        for b in d.refs(objet, "MorphBundles"):
            bundle = d.get(b)
            if bundle is None:
                return None
            forme = d.choisir(d.multi(bundle, "Form"), vern)
            morph = d.get(d.ref(bundle, "Morph"))
            if not forme and morph is not None:
                forme = d.choisir(d.multi(morph, "Form"), vern)
            sens_guid = d.ref(bundle, "Sense")
            eid, sid = sens_par_guid.get(sens_guid, (None, None))
            if eid is None and morph is not None:
                eid = entree_par_guid.get(morph.get("ownerguid", "").lower())
            if not forme:
                return None
            morphemes.append(il.MorphemeAnalyse(forme.strip("-=").lower(), eid, sid))
        return morphemes, glose

    cache = il._gloses_sens(conn)
    usages = defaultdict(Counter)
    for _, _, forme, guid in occurrences:
        usages[forme][guid] += 1
    ids = {}
    for forme, compte in usages.items():
        for guid, _ in compte.most_common():
            resultat = analyse_flex(guid)
            if not resultat or not resultat[0]:
                continue
            analyse_mot = il.Analyse(forme, resultat[0], resultat[1])
            # les analyses FLEx peuvent noter les morphèmes sous leur forme sous-jacente : elles sont reprises
            ids[(forme, guid)] = il.valider(conn, analyse_mot, cache, formes_sous_jacentes=True)
            r.analyses += 1
            if not il.reconstitue(analyse_mot):
                r.formes_sous_jacentes += 1
    defauts = {}
    for forme in usages:
        valides = il.analyses_de(conn, forme, cache)
        if valides:
            defauts[forme] = valides[0].id
    for ref, pos, forme, guid in occurrences:
        aid = ids.get((forme, guid))
        if aid and aid != defauts.get(forme):
            il.choisir_pour_occurrence(conn, ref, pos, aid)

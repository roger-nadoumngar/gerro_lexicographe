"""Import LIFT (FLEx, WeSay, autres outils SIL).

Règles d'import, explicites et rapportées à l'utilisateur :
* les entrées marquées supprimées (dateDeleted) sont ignorées ;
* une entrée dont le guid existe déjà dans le projet est mise à jour,
  les autres sont créées : réimporter le même fichier ne crée pas de doublons ;
* langue documentée = code du projet s'il figure dans le fichier, sinon la langue
  la plus fréquente des formes lexicales ; même règle pour la langue d'analyse ;
* tout trait non reconnu devient une propriété de l'entrée : rien n'est perdu.
"""

import os
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field

from . import domaines, lexique
from .lexique import Entree, Exemple, Sens, Variante
from .projet import copier_medias
from .texte import normaliser

TYPES_COMPOSANTS = {"_component-lexeme", "composition", "component-lexeme"}


@dataclass
class Rapport:
    creees: int = 0
    mises_a_jour: int = 0
    supprimees_ignorees: int = 0
    relations: int = 0
    medias: int = 0
    langue_vern: str = ""
    langue_analyse: str = ""
    avertissements: list[str] = field(default_factory=list)

    def resume(self):
        lignes = [f"{self.creees} entrée(s) créée(s), {self.mises_a_jour} mise(s) à jour.",
                  f"Langue documentée : {self.langue_vern} ; langue d'analyse : {self.langue_analyse}.",
                  f"{self.relations} relation(s) et composant(s), {self.medias} image(s)."]
        if self.supprimees_ignorees:
            lignes.append(f"{self.supprimees_ignorees} entrée(s) marquée(s) supprimée(s) ignorée(s).")
        if self.avertissements:
            lignes.append("Avertissements :")
            lignes.extend("  • " + a for a in self.avertissements[:30])
            if len(self.avertissements) > 30:
                lignes.append(f"  … et {len(self.avertissements) - 30} autre(s).")
        return "\n".join(lignes)


def _formes(element):
    """{lang: texte} des <form lang><text> directement sous l'élément."""
    resultat = {}
    if element is None:
        return resultat
    for form in element.findall("form"):
        texte = "".join(form.find("text").itertext()).strip() if form.find("text") is not None else ""
        if texte:
            resultat[form.get("lang", "")] = normaliser(texte)
    return resultat


def _choisir(formes, langue):
    if langue in formes:
        return formes[langue]
    return ""


def _langue_dominante(racine, chemin_balise, prefere):
    compteur = Counter()
    for el in racine.iterfind(chemin_balise):
        for form in el.findall("form"):
            lang = form.get("lang", "")
            if lang and not lang.endswith("-fonipa"):
                compteur[lang] += 1
    if prefere and prefere in compteur:
        return prefere
    return compteur.most_common(1)[0][0] if compteur else prefere


def importer(projet, chemin):
    """Importe un fichier LIFT dans le projet. Retourne un Rapport."""
    with projet.en_lot():
        return _importer(projet, chemin)


def _importer(projet, chemin):
    conn = projet.conn
    racine = ET.parse(chemin).getroot()
    if racine.tag != "lift":
        raise ValueError("Ce fichier n'est pas un fichier LIFT.")
    rapport = Rapport()
    lang_v = _langue_dominante(racine, "entry/lexical-unit", projet.reglage("langue_vern_code"))
    glose_langs = Counter(g.get("lang") for g in racine.iterfind("entry/sense/gloss"))
    analyse_projet = projet.reglage("langue_analyse_code")
    lang_a = analyse_projet if analyse_projet in glose_langs else (glose_langs.most_common(1)[0][0]
                                                                  if glose_langs else analyse_projet)
    rapport.langue_vern, rapport.langue_analyse = lang_v, lang_a
    if projet.reglage("langue_vern_code") and lang_v != projet.reglage("langue_vern_code"):
        rapport.avertissements.append(
            f"Le fichier est en « {lang_v} », le projet en « {projet.reglage('langue_vern_code')} ».")
    if analyse_projet and lang_a != analyse_projet:
        rapport.avertissements.append(
            f"Gloses importées depuis la langue « {lang_a} » (aucune glose en « {analyse_projet} »).")

    dossier_lift = os.path.dirname(os.path.abspath(chemin))
    guids = dict(conn.execute("SELECT guid, id FROM entrees"))
    ids_lift, formes_lift, relations_a_faire, images = {}, {}, [], []

    for el in racine.findall("entry"):
        if el.get("dateDeleted"):
            rapport.supprimees_ignorees += 1
            continue
        unite = _formes(el.find("lexical-unit"))
        forme = _choisir(unite, lang_v) or next((t for l, t in unite.items() if not l.endswith("-fonipa")), "")
        if not forme:
            rapport.avertissements.append(f"Entrée sans forme ignorée ({el.get('id', '?')}).")
            continue
        guid = (el.get("guid") or "").lower()
        entree = Entree(forme=forme, guid=guid, statut="à vérifier")
        existant = guids.get(guid) if guid else None
        if existant:
            ancien = lexique.lire_entree(conn, existant)
            entree.id, entree.date_creation = existant, ancien.date_creation
            entree.statut = ancien.statut  # gardé sauf si le fichier en indique un
        if el.get("dateCreated") and not entree.date_creation:
            entree.date_creation = el.get("dateCreated").rstrip("Z")

        entree.forme_citation = _choisir(_formes(el.find("citation")), lang_v)
        prononciations = [t for p in el.findall("pronunciation") for t in _formes(p).values()]
        prononciations += [t for l, t in unite.items() if l.endswith("-fonipa")]
        entree.prononciation = prononciations[0] if prononciations else ""

        for var in el.findall("variant"):
            vf = _formes(var)
            vforme = _choisir(vf, lang_v) or next(iter(vf.values()), "")
            traits = {t.get("name"): t.get("value", "") for t in var.findall("trait")}
            type_v = traits.get("type", "")
            if type_v not in lexique.TYPES_VARIANTES:
                type_v = "variante libre"
            if vforme:
                entree.variantes.append(Variante(forme=vforme, type=type_v,
                                                 environnement=traits.get("environnement", ""),
                                                 note=" ".join(_formes(var.find("note")).values())))

        for trait in el.findall("trait"):
            nom, valeur = trait.get("name", ""), trait.get("value", "")
            if nom == "morph-type" and valeur in lexique.TYPES_MORPH:
                entree.type_morph = valeur
            elif nom == "statut" and valeur in lexique.STATUTS:
                entree.statut = valeur
            elif nom and valeur:
                entree.proprietes[nom] = valeur

        notes = []
        for note in el.findall("note"):
            texte = _choisir(_formes(note), lang_a) or " ".join(_formes(note).values())
            if texte:
                notes.append(f"{note.get('type')} : {texte}" if note.get("type") else texte)

        for n, s_el in enumerate(el.findall("sense"), start=1):
            sens = Sens()
            gi = s_el.find("grammatical-info")
            if gi is not None and gi.get("value"):
                sens.categorie_id = lexique.categorie_par_nom(conn, gi.get("value"), creer=True)
            gloses = [normaliser("".join(g.find("text").itertext()).strip())
                      for g in s_el.findall("gloss") if g.get("lang") == lang_a and g.find("text") is not None]
            sens.glose = " ; ".join(g for g in gloses if g)
            sens.definition = _choisir(_formes(s_el.find("definition")), lang_a)
            if not sens.glose and sens.definition and len(sens.definition) <= 40:
                sens.glose = sens.definition
            for ex_el in s_el.findall("example"):
                ex_formes = _formes(ex_el)
                trad = _choisir(_formes(ex_el.find("translation")), lang_a)
                sens.exemples.append(Exemple(vernaculaire=_choisir(ex_formes, lang_v) or next(iter(ex_formes.values()), ""),
                                             traduction=trad, reference=ex_el.get("source", "")))
            inverses = [t for r in s_el.findall("reversal") for t in [_choisir(_formes(r), lang_a)] if t]
            if inverses and inverses != lexique.formes_inverses(sens.glose):
                sens.inverse = " ; ".join(inverses)
            for trait in s_el.findall("trait"):
                nom, valeur = trait.get("name", ""), trait.get("value", "")
                if nom in ("semantic-domain-ddp4", "semantic-domain"):
                    code = valeur.split(" ", 1)[0]
                    guid_dom = domaines.par_code(conn, code)
                    if guid_dom:
                        sens.domaines.append(guid_dom)
                    else:
                        sens.domaine = "; ".join(x for x in (sens.domaine, valeur) if x)
                elif nom == "domaine-libre":
                    sens.domaine = valeur
                elif nom and valeur:
                    entree.proprietes[f"{nom} (sens {n})"] = valeur
            for note in s_el.findall("note"):
                texte = _choisir(_formes(note), lang_a) or " ".join(_formes(note).values())
                if texte:
                    notes.append(f"Sens {n} : {texte}")
            for rel in s_el.findall("relation"):
                relations_a_faire.append((el, rel))
            for ill in s_el.findall("illustration"):
                images.append((el, n - 1, ill.get("href", "")))
            entree.sens.append(sens)
        if not entree.sens:
            entree.sens.append(Sens())
        entree.notes = "\n".join(notes)
        for rel in el.findall("relation"):
            relations_a_faire.append((el, rel))

        try:
            eid = lexique.enregistrer_entree(conn, entree)
        except ValueError as e:
            rapport.avertissements.append(f"« {forme} » : {e}")
            continue
        if existant:
            rapport.mises_a_jour += 1
        else:
            rapport.creees += 1
            if guid:
                guids[guid] = eid
        ids_lift[el.get("id") or forme] = eid
        formes_lift.setdefault(forme, eid)
        el.set("_eid", str(eid))

    # relations et composants, une fois toutes les entrées connues
    composants = {}
    for el, rel in relations_a_faire:
        source = int(el.get("_eid", 0) or 0)
        ref = rel.get("ref", "")
        cible = ids_lift.get(ref) or formes_lift.get(normaliser(ref)) or (guids.get(ref.rsplit("_", 1)[-1].lower())
                                                                          if "_" in ref else None)
        if not source or not cible:
            if source and ref:
                rapport.avertissements.append(f"Relation « {rel.get('type')} » vers « {ref} » introuvable.")
            continue
        typ = rel.get("type", "voir aussi")
        if typ in TYPES_COMPOSANTS:
            ordre = int(rel.get("order") or 0) if (rel.get("order") or "").isdigit() else 0
            type_cf = next((t.get("value") for t in rel.findall("trait") if t.get("name") == "complex-form-type"), "")
            composants.setdefault(source, {"liste": [], "type": type_cf})["liste"].append((ordre, cible))
        elif source != cible:
            if lexique.ajouter_relation(conn, source, cible, typ):
                rapport.relations += 1
    for source, info in composants.items():
        entree = lexique.lire_entree(conn, source)
        entree.composants = [c for _, c in sorted(info["liste"], key=lambda x: x[0]) if c != source]
        entree.type_forme_complexe = entree.type_forme_complexe or info["type"]
        lexique.enregistrer_entree(conn, entree)
        rapport.relations += len(entree.composants)

    for el, index_sens, href in images:
        source = int(el.get("_eid", 0) or 0)
        if not source or not href:
            continue
        candidats = [os.path.join(dossier_lift, href), os.path.join(dossier_lift, "pictures", href)]
        fichier = next((c for c in candidats if os.path.isfile(c)), None)
        if not fichier:
            rapport.avertissements.append(f"Image introuvable : {href}")
            continue
        entree = lexique.lire_entree(conn, source)
        sens_id = entree.sens[index_sens].id if index_sens < len(entree.sens) else None
        lexique.lier_media(conn, source, copier_medias(projet, fichier), "image", sens_id=sens_id)
        rapport.medias += 1
    return rapport


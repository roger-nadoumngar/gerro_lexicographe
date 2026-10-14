"""Exports du lexique : JSON, CSV, texte imprimable, LIFT 0.13 (FLEx, WeSay,
Dictionary App Builder)."""

import csv
import json
import xml.etree.ElementTree as ET
from collections import defaultdict

from . import APP_NAME, domaines, lexique


def entrees_completes(projet):
    """Toutes les entrées complètes, dans l'ordre alphabétique du projet, avec
    noms de catégories, libellés de domaines, vedette et numéro d'homographe."""
    conn = projet.conn
    noms_cat = {cid: nom for cid, nom, _, _ in lexique.categories(conn)}
    langue = projet.reglage("langue_analyse_code") or "fr"
    libelles = {g: (c, n) for g, c, n, _ in domaines.arbre(conn, langue)}
    resultat = []
    for ligne in lexique.lister_entrees(conn):
        entree = lexique.lire_entree(conn, ligne.id)
        entree.homographe = ligne.homographe
        entree.vedette = lexique.vedette(entree.tete, ligne.homographe)
        entree.categories = [noms_cat.get(s.categorie_id, "") for s in entree.sens]
        entree.libelles_domaines = [[libelles[g] for g in s.domaines if g in libelles] for s in entree.sens]
        resultat.append(entree)
    return resultat


def _relations_par_entree(conn):
    rels = defaultdict(list)
    for source, cible, typ in conn.execute("SELECT source_id, cible_id, type FROM relations ORDER BY type"):
        rels[source].append((cible, typ))
    return rels


def exporter_json(projet, chemin):
    entrees = entrees_completes(projet)
    par_id = {e.id: e for e in entrees}
    rels = _relations_par_entree(projet.conn)
    donnees = {
        "projet": projet.nom,
        "langue_vernaculaire": projet.reglage("langue_vern_code"),
        "langue_analyse": projet.reglage("langue_analyse_code"),
        "entrees": [{
            "guid": e.guid,
            "forme": e.forme,
            "forme_citation": e.forme_citation,
            "homographe": e.homographe,
            "prononciation": e.prononciation,
            "type_morphologique": lexique.TYPES_MORPH.get(e.type_morph, e.type_morph),
            "statut": e.statut,
            "variantes": [{"forme": v.forme, "type": v.type, "environnement": v.environnement, "note": v.note}
                          for v in e.variantes],
            "forme_complexe": ({"type": e.type_forme_complexe,
                                "composants": [par_id[c].vedette for c in e.composants if c in par_id]}
                               if e.composants or e.type_forme_complexe else None),
            "sens": [{"glose": s.glose, "index_inverse": lexique.formes_inverses(s), "definition": s.definition,
                      "categorie": cat, "domaines": [f"{c} {n}" for c, n in libs],
                      "exemples": [{"vernaculaire": x.vernaculaire, "traduction": x.traduction,
                                    "reference": x.reference} for x in s.exemples]}
                     for s, cat, libs in zip(e.sens, e.categories, e.libelles_domaines)],
            "notes": e.notes,
            "proprietes": e.proprietes,
            "relations": [{"type": t, "forme": par_id[c].vedette} for c, t in rels.get(e.id, []) if c in par_id],
            "date_modification": e.date_modification,
        } for e in entrees],
    }
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(donnees, f, ensure_ascii=False, indent=2)
    return len(entrees)


def exporter_csv(projet, chemin):
    """Une ligne par sens (format tableur)."""
    entrees = entrees_completes(projet)
    with open(chemin, "w", encoding="utf-8-sig", newline="") as f:  # BOM : accents corrects dans Excel
        w = csv.writer(f)
        w.writerow(["vedette", "forme", "prononciation", "statut", "sens", "glose", "categorie", "definition",
                    "domaines", "exemple", "traduction_exemple", "variantes", "notes"])
        for e in entrees:
            variantes = " ; ".join(f"{v.forme} ({v.type})" for v in e.variantes)
            for n, (s, cat, libs) in enumerate(zip(e.sens, e.categories, e.libelles_domaines), start=1):
                ex = s.exemples[0] if s.exemples else lexique.Exemple()
                premier = n == 1
                w.writerow([e.vedette, e.forme, e.prononciation if premier else "", e.statut if premier else "",
                            n, s.glose, cat, s.definition, " ; ".join(f"{c} {nm}" for c, nm in libs),
                            ex.vernaculaire, ex.traduction, variantes if premier else "",
                            e.notes if premier else ""])
    return len(entrees)


def exporter_texte(projet, chemin):
    entrees = entrees_completes(projet)
    par_id = {e.id: e for e in entrees}
    titre = f"DICTIONNAIRE {projet.reglage('langue_vern_nom').upper()} — {projet.reglage('langue_analyse_nom').upper()}"
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(titre + "\n" + "=" * len(titre) + "\n\n")
        for e in entrees:
            tete = e.vedette + (f" [{e.prononciation}]" if e.prononciation else "")
            if e.type_morph and e.type_morph != "stem":
                tete += f" ({lexique.TYPES_MORPH.get(e.type_morph, e.type_morph)})"
            f.write(tete + "\n")
            if e.composants:
                composants = " + ".join(par_id[c].vedette for c in e.composants if c in par_id)
                f.write(f"  {e.type_forme_complexe or 'forme complexe'} : {composants}\n")
            plusieurs = len(e.sens) > 1
            for n, (s, cat) in enumerate(zip(e.sens, e.categories), start=1):
                prefixe = f"  {n}. " if plusieurs else "  "
                details = ", ".join(x for x in (cat, s.domaine) if x)
                f.write(f"{prefixe}{f'({details}) ' if details else ''}{s.glose}\n")
                if s.definition:
                    f.write(f"      {s.definition}\n")
                for x in s.exemples:
                    f.write(f"      « {x.vernaculaire} »" + (f" — {x.traduction}" if x.traduction else "") + "\n")
            if e.variantes:
                f.write("  Variantes : " + " ; ".join(f"{v.forme} ({v.type})" for v in e.variantes) + "\n")
            if e.notes:
                f.write(f"  Notes : {e.notes}\n")
            f.write("\n")
    return len(entrees)


# -- LIFT --------------------------------------------------------------------------

def lift_id(entree):
    return f"{entree.forme}_{entree.guid}"


def _forme(parent, tag, lang, texte):
    el = ET.SubElement(parent, tag) if tag else parent
    form = ET.SubElement(el, "form", lang=lang)
    ET.SubElement(form, "text").text = texte
    return el


def _date_lift(date):
    return (date.split(".")[0] + "Z") if date else None


def construire_lift(projet, medias=None):
    """`medias` (facultatif) : {id d'entrée: [(rôle, id de sens, nom de fichier)]} — sons écrits dans
    <pronunciation><media>, images dans <sense><illustration>, chemins relatifs aux dossiers
    audio/ et pictures/ placés à côté du fichier LIFT (convention FLEx et Dictionary App Builder)."""
    medias = medias or {}
    lang_v = projet.reglage("langue_vern_code") or "und"
    lang_a = projet.reglage("langue_analyse_code") or "und"
    entrees = entrees_completes(projet)
    par_id = {e.id: e for e in entrees}
    rels = _relations_par_entree(projet.conn)

    racine = ET.Element("lift", version="0.13", producer=APP_NAME)
    for e in entrees:
        attrs = {"id": lift_id(e), "guid": e.guid}
        if e.homographe:
            attrs["order"] = str(e.homographe)
        if e.date_creation:
            attrs["dateCreated"] = _date_lift(e.date_creation)
        if e.date_modification:
            attrs["dateModified"] = _date_lift(e.date_modification)
        el = ET.SubElement(racine, "entry", attrs)
        _forme(el, "lexical-unit", lang_v, e.forme)
        if e.forme_citation:
            _forme(el, "citation", lang_v, e.forme_citation)
        sons = [f for role, _, f in medias.get(e.id, []) if role == "prononciation"]
        if e.prononciation or sons:
            # convention FLEx : la prononciation (API) est écrite dans le système d'écriture « langue-fonipa »
            pron = (_forme(el, "pronunciation", f"{lang_v}-fonipa", e.prononciation) if e.prononciation
                    else ET.SubElement(el, "pronunciation"))
            for son in sons:
                ET.SubElement(pron, "media", href=son)
        for v in e.variantes:
            var = _forme(ET.SubElement(el, "variant"), None, lang_v, v.forme)
            ET.SubElement(var, "trait", name="type", value=v.type)
            if v.environnement:
                ET.SubElement(var, "trait", name="environnement", value=v.environnement)
            if v.note:
                _forme(var, "note", lang_a, v.note)
        if e.type_morph:
            ET.SubElement(el, "trait", name="morph-type", value=e.type_morph)
        ET.SubElement(el, "trait", name="statut", value=e.statut)
        for nom, valeur in e.proprietes.items():
            ET.SubElement(el, "trait", name=nom, value=valeur)
        if e.notes:
            _forme(el, "note", lang_a, e.notes)
        # formes complexes : relation « _component-lexeme » vers chaque composant (convention FLEx)
        for i, cid in enumerate(e.composants, start=1):
            if cid in par_id:
                rel = ET.SubElement(el, "relation", type="_component-lexeme", ref=lift_id(par_id[cid]), order=str(i))
                if e.type_forme_complexe:
                    ET.SubElement(rel, "trait", name="complex-form-type", value=e.type_forme_complexe)
        for cible, typ in rels.get(e.id, []):
            if cible in par_id:
                ET.SubElement(el, "relation", type=typ, ref=lift_id(par_id[cible]))

        for n, (s, cat, libs) in enumerate(zip(e.sens, e.categories, e.libelles_domaines), start=1):
            sens = ET.SubElement(el, "sense", id=f"{lift_id(e)}_s{n}", order=str(n))
            if cat:
                ET.SubElement(sens, "grammatical-info", value=cat)
            if s.glose:
                g = ET.SubElement(sens, "gloss", lang=lang_a)
                ET.SubElement(g, "text").text = s.glose
            if s.definition:
                _forme(sens, "definition", lang_a, s.definition)
            for x in s.exemples:
                ex = ET.SubElement(sens, "example", **({"source": x.reference} if x.reference else {}))
                if x.vernaculaire:
                    _forme(ex, None, lang_v, x.vernaculaire)
                if x.traduction:
                    _forme(ex, "translation", lang_a, x.traduction)
            for code, nom in libs:
                ET.SubElement(sens, "trait", name="semantic-domain-ddp4", value=f"{code} {nom}")
            if s.domaine:
                ET.SubElement(sens, "trait", name="domaine-libre", value=s.domaine)
            for role, sens_id, image in medias.get(e.id, []):
                # une image liée à l'entrée sans sens précis va au premier sens
                if role == "image" and (sens_id == s.id or (sens_id is None and n == 1)):
                    ET.SubElement(sens, "illustration", href=image)
            for mot in lexique.formes_inverses(s):
                _forme(ET.SubElement(sens, "reversal", type=lang_a), None, lang_a, mot)
    ET.indent(racine)
    return ET.ElementTree(racine), len(entrees)


def exporter_lift(projet, chemin):
    arbre, n = construire_lift(projet)
    arbre.write(chemin, encoding="utf-8", xml_declaration=True)
    return n

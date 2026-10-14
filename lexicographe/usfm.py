"""Lecture des fichiers USFM / SFM (Paratext et autres outils SIL)."""

import os
import re

from .texte import normaliser


# ordre canonique des livres (codes USFM / Paratext)
LIVRES = ("GEN EXO LEV NUM DEU JOS JDG RUT 1SA 2SA 1KI 2KI 1CH 2CH EZR NEH EST JOB PSA PRO ECC SNG ISA JER "
          "LAM EZK DAN HOS JOL AMO OBA JON MIC NAM HAB ZEP HAG ZEC MAL MAT MRK LUK JHN ACT ROM 1CO 2CO GAL "
          "EPH PHP COL 1TH 2TH 1TI 2TI TIT PHM HEB JAS 1PE 2PE 1JN 2JN 3JN JUD REV").split()
_RANG_LIVRE = {code: i for i, code in enumerate(LIVRES)}


def cle_reference(ref):
    """Clé de tri : livres dans l'ordre canonique, chapitres et versets en nombres
    (« RUT 1:10 » après « RUT 1:9 »). Les autres références (saisies manuelles…)
    viennent après, dans l'ordre alphabétique."""
    m = re.fullmatch(r"(\w{3}) (\d+):(\d+)", ref or "")
    if m and m.group(1) in _RANG_LIVRE:
        return (0, _RANG_LIVRE[m.group(1)], int(m.group(2)), int(m.group(3)), "")
    # le code du texte passe avant les numéros : les phrases de deux textes ne s'entrelacent pas
    if m:
        return (1, m.group(1), int(m.group(2)), int(m.group(3)), "")
    m = re.fullmatch(r"(\S+) (\d+)", ref or "")   # textes importés : « T001 12 »
    if m:
        return (1, m.group(1), 0, int(m.group(2)), "")
    return (2, "", 0, 0, ref or "")


def lire_usfm(chemin, code_livre=None):
    """Extrait les versets d'un fichier USFM. Retourne ({ref: texte}, code_livre),
    les références ayant la forme « LIV chapitre:verset »."""
    with open(chemin, encoding="utf-8-sig", errors="replace") as f:
        texte = f.read()
    return analyser_usfm(texte, code_livre or _code_depuis_nom(chemin))


def _code_depuis_nom(chemin):
    return os.path.splitext(os.path.basename(chemin))[0][:3].upper()


def analyser_usfm(texte, code_par_defaut="XXX"):
    m = re.search(r"\\id\s+(\w+)", texte)
    code = m.group(1)[:3].upper() if m else code_par_defaut

    versets = {}
    chapitre = None
    verset = None
    morceaux = []

    def vider():
        nonlocal verset, morceaux
        if chapitre is not None and verset is not None:
            propre = nettoyer(" ".join(morceaux))
            if propre:
                versets[f"{code} {chapitre}:{verset}"] = propre
        verset, morceaux = None, []

    for ligne in texte.split("\n"):
        ligne = ligne.strip()
        m_c = re.match(r"\\c\s+(\d+)", ligne)
        m_v = re.match(r"\\v\s+(\d+)(?:-\d+)?\s*(.*)", ligne)
        if m_c:
            vider()
            chapitre = int(m_c.group(1))
        elif m_v:
            vider()
            verset = int(m_v.group(1))
            morceaux = [m_v.group(2)]
        elif ligne.startswith("\\"):
            parties = ligne.split(" ", 1)
            # titres et en-têtes n'appartiennent pas au verset ; les marqueurs de paragraphe ou de poésie, si
            if len(parties) > 1 and verset is not None and not re.match(r"\\(s\d?|ms\d?|mr|r|d|h|toc\d?|mt\d?|cl)\b", ligne):
                morceaux.append(parties[1])
        elif verset is not None and ligne:
            morceaux.append(ligne)
    vider()
    return versets, code


def nettoyer(texte):
    """Retire notes, renvois, figures et marqueurs pour ne garder que le texte lu."""
    texte = re.sub(r"\\x .*?\\x\*", "", texte)
    texte = re.sub(r"\\f .*?\\f\*", "", texte)
    texte = re.sub(r"\\fe .*?\\fe\*", "", texte)
    texte = re.sub(r"\\fig .*?\\fig\*", "", texte)
    texte = re.sub(r"\|[^\\]*?(?=\\\+?[a-z]+\d?\*)", "", texte)   # attributs : \w mot|lemma="…"\w*
    texte = re.sub(r"\\\+?[a-z]+\d?\*?", "", texte)
    texte = re.sub(r"\s+", " ", texte).strip()
    return normaliser(texte)


def analyser_usx(contenu):
    """Versets d'un livre au format USX (XML de la Digital Bible Library), USX 2 ou 3.
    Les notes, renvois et titres sont écartés. Retourne ({ref: texte}, code_livre)."""
    import xml.etree.ElementTree as ET
    racine = ET.fromstring(contenu)
    livre = racine.find("book")
    code = (livre.get("code") if livre is not None else "XXX").upper()
    versets, chapitre, verset, morceaux = {}, None, None, []

    def vider():
        nonlocal morceaux
        if chapitre is not None and verset is not None:
            texte = normaliser(re.sub(r"\s+", " ", "".join(morceaux)).strip())
            if texte:
                versets[f"{code} {chapitre}:{verset}"] = texte
        morceaux = []

    def parcourir(el, dans_titre=False):
        nonlocal chapitre, verset
        for enfant in el:
            balise = enfant.tag
            if balise == "chapter" and enfant.get("number"):
                vider()
                chapitre, verset = int(enfant.get("number")), None
            elif balise == "verse":
                if enfant.get("number"):
                    vider()
                    verset = int(re.match(r"\d+", enfant.get("number")).group())
                elif enfant.get("eid"):
                    vider()
                    verset = None
            elif balise in ("note", "figure"):
                pass   # notes et figures : pas dans le texte lu
            elif balise == "para" and (enfant.get("style") or "").rstrip("0123456789") in (
                    "s", "ms", "mr", "r", "d", "h", "toc", "mt", "cl", "ide", "rem"):
                pass   # titres et en-têtes
            else:
                if verset is not None and enfant.text:
                    morceaux.append(enfant.text)
                parcourir(enfant)
                if balise == "para" and verset is not None:
                    morceaux.append(" ")
            if enfant.tail and verset is not None:
                morceaux.append(enfant.tail)
    parcourir(racine)
    vider()
    return versets, code


def lire_bible(chemin):
    """Tous les livres d'un dossier ou d'une archive .zip (USFM .usfm/.sfm ou USX .usx), par
    exemple un paquet de la Digital Bible Library. Retourne {code du livre: {ref: texte}}."""
    import zipfile
    fichiers = []   # (nom, lecture du contenu)
    if os.path.isdir(chemin):
        for dossier, _, noms in os.walk(chemin):
            for nom in noms:
                plein = os.path.join(dossier, nom)
                fichiers.append((nom, lambda p=plein: open(p, "rb").read()))
    else:
        archive = zipfile.ZipFile(chemin)
        for nom in archive.namelist():
            fichiers.append((os.path.basename(nom), lambda n=nom: archive.read(n)))
    livres = {}
    for nom, lire in fichiers:
        extension = os.path.splitext(nom)[1].lower()
        if nom.upper().endswith(".BAK") or extension not in (".usfm", ".sfm", ".usx", ".ptx"):
            continue
        brut = lire().decode("utf-8-sig", errors="replace")
        versets, code = analyser_usx(brut) if extension == ".usx" else analyser_usfm(brut, _code_depuis_nom(nom))
        if versets:
            livres.setdefault(code, {}).update(versets)
    return livres


def importer(projet, versets, cote, source):
    """Range des versets dans le corpus du projet. `cote` : 'vernaculaire' ou 'analyse'.
    Retourne (nouveaux, complétés)."""
    if cote not in ("vernaculaire", "analyse"):
        raise ValueError(cote)
    nouveaux = completes = 0
    with projet.conn:
        for ref, texte in versets.items():
            if projet.conn.execute("SELECT 1 FROM phrases WHERE ref=?", (ref,)).fetchone():
                # la nouvelle source empêche le corpus intégré de réécrire ce verset
                projet.conn.execute(f"UPDATE phrases SET {cote}=?, source=? WHERE ref=?", (texte, source, ref))
                completes += 1
            else:
                projet.conn.execute(f"INSERT INTO phrases (ref, {cote}, source) VALUES (?, ?, ?)",
                                    (ref, texte, source))
                nouveaux += 1
    return nouveaux, completes

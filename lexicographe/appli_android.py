"""Application Android du dictionnaire, construite par Dictionary App Builder (SIL).

Étapes, toutes visibles dans le journal rendu :
1. le dictionnaire est exporté en LIFT avec ses images (comme pour l'export « Dictionary App Builder ») ;
2. Dictionary App Builder crée le projet d'application (`dab -new`) : le fichier de projet est donc
   toujours au format de la version installée ;
3. le projet est relié au LIFT (DAB ne sait pas le faire en ligne de commande) et les images sont
   copiées dans son dossier de données ;
4. Dictionary App Builder construit l'APK (`dab -load … -build`), signé avec le keystore donné.

Les réglages d'App Builder de l'utilisateur ne sont jamais modifiés : les dossiers (programme, JDK,
SDK Android, sortie) sont passés à chaque commande. Gerro Lexicographe ne garde pas les mots de passe et
les masque dans le journal ; Dictionary App Builder les enregistre chiffrés dans son projet, comme
lorsqu'on l'utilise directement."""

import glob
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

DOSSIERS_DAB = [r"C:\Program Files\SIL\Dictionary App Builder", r"C:\Program Files (x86)\SIL\Dictionary App Builder"]
CLASSE = "org.sil.app.builder.dictionary.DictionaryAppBuilder"
REGLAGES_APP_BUILDER = os.path.join(os.environ.get("APPDATA", ""), "SIL", "App Builder", "settings.xml")


def dossier_dab():
    return next((d for d in DOSSIERS_DAB if os.path.isfile(os.path.join(d, "bin", "dictionary-app-builder.jar"))),
                None)


def dossiers_construction():
    """JDK et SDK Android déclarés dans les réglages d'App Builder (lus seulement), sinon cherchés
    aux emplacements habituels."""
    trouves = {}
    try:
        racine = ET.parse(REGLAGES_APP_BUILDER).getroot()
        for el in racine.iter("folder"):
            if el.get("name") in ("jdk", "android.sdk") and (el.text or "").strip():
                trouves[el.get("name")] = el.text.strip()
    except (OSError, ET.ParseError):
        pass
    if not os.path.isdir(trouves.get("jdk", "")):
        jdks = sorted(glob.glob(r"C:\jdk\*")) + sorted(glob.glob(r"C:\Program Files\Zulu\*"))
        trouves["jdk"] = next((j for j in reversed(jdks) if os.path.isfile(os.path.join(j, "bin", "java.exe"))), "")
    if not os.path.isdir(trouves.get("android.sdk", "")):
        trouves["android.sdk"] = next((s for s in (r"C:\sdk", os.path.join(os.environ.get("LOCALAPPDATA", ""),
                                                                            "Android", "Sdk")) if os.path.isdir(s)), "")
    return trouves


def nom_de_paquet(code_langue, nom_projet):
    """org.gerro.<code>.dictionnaire : minuscules ASCII, chaque partie commence par une lettre."""
    def partie(texte, defaut):
        t = re.sub(r"[^a-z0-9_]", "", (texte or "").lower())
        return t if t and t[0].isalpha() else (defaut + t)
    return f"org.gerro.{partie(code_langue or nom_projet, 'l')}.dictionnaire"


@dataclass
class Options:
    nom_app: str
    paquet: str
    dossier_projets: str
    dossier_apk: str
    keystore: str
    alias: str
    mot_de_passe: str
    mot_de_passe_alias: str = ""
    apropos: str = ""
    icones: list[str] = field(default_factory=list)   # png 72×72 et 144×144 ; sinon icône produite
    langue_interface: str = "fr"


@dataclass
class Resultat:
    apk: str = ""
    projet_dab: str = ""
    journal: str = ""


def _executer(dab, arguments, secrets, delai=3600):
    java = os.path.join(dab, "runtime", "bin", "java.exe")
    if not os.path.isfile(java):
        java = shutil.which("java") or "java"
    commande = [java, "-cp", os.path.join(dab, "bin", "dictionary-app-builder.jar"), CLASSE] + arguments
    # DAB lance « buildapp.bat » dans son dossier de construction : cmd doit pouvoir chercher dans
    # le dossier courant, ce que cette variable (posée par certains environnements) interdit
    env = {k: v for k, v in os.environ.items() if k.lower() != "nodefaultcurrentdirectoryinexepath"}
    sortie = subprocess.run(commande, capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=delai, env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    texte = sortie.stdout + sortie.stderr
    for s in secrets:   # aucun mot de passe dans le journal montré
        if s:
            texte = texte.replace(s, "••••")
    return sortie.returncode, texte


def icones_par_defaut(texte, dossier, couleur="#1F5C55"):
    """Icônes 72×72 et 144×144 : deux lettres du nom sur fond uni (à remplacer par une vraie icône)."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])   # polices disponibles même hors de l'interface
    lettres = (texte or "Di")[:2]
    chemins = []
    for taille in (72, 144):
        image = QImage(taille, taille, QImage.Format_ARGB32)
        image.fill(QColor(couleur))
        peintre = QPainter(image)
        police = QFont("Segoe UI", max(8, int(taille * 0.40)))
        police.setBold(True)
        peintre.setFont(police)
        peintre.setPen(QColor("#F6EFD9"))
        peintre.drawText(image.rect(), Qt.AlignCenter, lettres)
        peintre.end()
        chemin = os.path.join(dossier, f"icone-{taille}.png")
        image.save(chemin)
        chemins.append(chemin)
    return chemins


def construire(projet, options, progression=None):
    """Construit l'APK ; retourne un Resultat avec le journal. Lève une erreur claire si un outil manque."""
    from . import publication
    from .projet import nom_fichier_sur

    def etape(message):
        if progression:
            progression(message)

    dab = dossier_dab()
    if not dab:
        raise RuntimeError("Dictionary App Builder n'est pas installé (https://software.sil.org/dictionaryappbuilder/).")
    construction = dossiers_construction()
    if not construction.get("jdk") or not construction.get("android.sdk"):
        raise RuntimeError("Le JDK ou le SDK Android est introuvable : ouvrez une fois Dictionary App Builder et "
                           "laissez-le les installer (Outils > Paramètres).")
    if not (options.keystore and os.path.isfile(options.keystore)):
        raise RuntimeError("Choisissez le fichier keystore qui signe vos applications.")
    secrets = [options.mot_de_passe, options.mot_de_passe_alias]
    journal = []
    nom = nom_fichier_sur(options.nom_app)
    projet_dab = os.path.join(options.dossier_projets, nom)
    fichier_projet = os.path.join(projet_dab, f"{nom}.appDef")
    donnees = os.path.join(projet_dab, f"{nom}_data")

    # 1. LIFT et images
    etape("Export du dictionnaire…")
    travail = os.path.join(options.dossier_projets, f"{nom}-sources")
    os.makedirs(travail, exist_ok=True)
    lift = publication.preparer_dab(projet, travail)

    # 2. projet DAB (créé une seule fois ; ensuite il est réutilisé, avec ses réglages faits dans DAB)
    os.makedirs(options.dossier_projets, exist_ok=True)
    if not os.path.isfile(fichier_projet):
        etape("Création du projet Dictionary App Builder…")
        code, texte = _executer(dab, ["-new", "-n", options.nom_app, "-p", options.paquet,
                                      "-fp", f"app.def={options.dossier_projets}"], secrets, 600)
        journal.append(texte)
        if not os.path.isfile(fichier_projet):
            raise RuntimeError("Dictionary App Builder n'a pas créé le projet :\n" + texte[-1500:])

    # 3. lien vers le LIFT, copie du LIFT et des images
    etape("Ajout du dictionnaire au projet…")
    os.makedirs(os.path.join(donnees, "lexicon"), exist_ok=True)
    illustrations = os.path.join(donnees, "images", "illustrations")
    os.makedirs(illustrations, exist_ok=True)
    nom_lift = os.path.basename(lift)
    shutil.copy2(lift, os.path.join(donnees, "lexicon", nom_lift))
    images = os.path.join(os.path.dirname(lift), "pictures")
    for f in os.listdir(images) if os.path.isdir(images) else []:
        shutil.copy2(os.path.join(images, f), os.path.join(illustrations, f))
    _relier_lift(fichier_projet, nom_lift, lift)
    _declarer_illustrations(fichier_projet, illustrations)

    # 4. construction
    etape("Construction de l'application (plusieurs minutes la première fois)…")
    os.makedirs(options.dossier_apk, exist_ok=True)
    icones = options.icones or icones_par_defaut(options.nom_app, travail)
    apropos = os.path.join(travail, "a-propos.txt")
    with open(apropos, "w", encoding="utf-8") as f:
        f.write(options.apropos or options.nom_app)
    def etat_sortie():
        return {f: os.path.getmtime(os.path.join(options.dossier_apk, f)) for f in os.listdir(options.dossier_apk)
                if f.lower().endswith((".apk", ".aab"))}
    avant = etat_sortie()
    arguments = ["-load", fichier_projet, "-l", options.langue_interface, "-ft", "show-illustrations=true",
                 "-a", apropos, "-ks", options.keystore, "-ksp", options.mot_de_passe, "-ka", options.alias,
                 "-kap", options.mot_de_passe_alias or options.mot_de_passe,
                 "-fp", f"app.builder={dab}", "-fp", f"jdk={construction['jdk']}",
                 "-fp", f"android.sdk={construction['android.sdk']}", "-fp", f"apk.output={options.dossier_apk}",
                 "-build"]
    for icone in icones:
        arguments[2:2] = ["-ic", icone]
    code, texte = _executer(dab, arguments, secrets)
    journal.append(texte)
    # seul un fichier nouveau ou réécrit pendant cette construction compte (pas un ancien APK)
    nouveaux = sorted((f for f, t in etat_sortie().items() if avant.get(f) != t),
                      key=lambda f: os.path.getmtime(os.path.join(options.dossier_apk, f)), reverse=True)
    resultat = Resultat(projet_dab=fichier_projet, journal="\n".join(journal))
    if code == 0 and nouveaux:
        resultat.apk = os.path.join(options.dossier_apk, nouveaux[0])
    return resultat


def _relier_lift(fichier_projet, nom_lift, source):
    with open(fichier_projet, encoding="utf-8") as f:
        texte = f.read()
    texte = re.sub(r'<lexicon-db type="lift">[^<]*</lexicon-db>(\s*<source>[^<]*</source>)?',
                   lambda m: f'<lexicon-db type="lift">{nom_lift}</lexicon-db>\n  <source>{_xml(source)}</source>',
                   texte, count=1)
    with open(fichier_projet, "w", encoding="utf-8") as f:
        f.write(texte)


def _declarer_illustrations(fichier_projet, dossier):
    """DAB n'emporte dans l'application que les images déclarées dans le projet, avec leur taille :
    la section <images type="illustration"> est réécrite d'après le dossier des illustrations."""
    from PySide6.QtGui import QImageReader
    lignes = []
    for nom in sorted(os.listdir(dossier)) if os.path.isdir(dossier) else []:
        taille = QImageReader(os.path.join(dossier, nom)).size()
        if taille.isValid():
            lignes.append(f'    <image width="{taille.width()}" height="{taille.height()}">{_xml(nom)}</image>')
    with open(fichier_projet, encoding="utf-8") as f:
        texte = f.read()
    texte = re.sub(r'\n?  <images type="illustration">.*?</images>\n', "\n", texte, flags=re.S)
    if lignes:
        bloc = '  <images type="illustration">\n' + "\n".join(lignes) + "\n  </images>\n"
        fin_lanceur = re.search(r'<images type="launcher">.*?</images>\n', texte, flags=re.S)
        position = fin_lanceur.end() if fin_lanceur else texte.rindex("</app-definition>")
        texte = texte[:position] + "\n" + bloc + texte[position:]
    with open(fichier_projet, "w", encoding="utf-8") as f:
        f.write(texte)
    return len(lignes)


def _xml(texte):
    return texte.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

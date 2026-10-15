"""Clavier Keyman calculé à partir des données du projet.

Règles :
- les lettres couvertes sont celles de l'alphabet déclaré et celles des formes du lexique
  (au moins SEUIL_LETTRE occurrences) qui ne sont pas sur un clavier français ou anglais ;
- chaque lettre spéciale se tape « lettre de base + ; » (b; → ɓ) ; quand deux lettres ont la même
  base, la seconde se tape avec « ;; » (e; → ə, e;; → ɛ), dans l'ordre de TABLE_BASES ; un « ; »
  de plus rend la lettre de base suivie de « ; » (pour écrire « b; » lui-même) ;
- chaque signe (ton, nasalité) présent dans l'alphabet, ou qui fait au moins PART_SIGNE des signes
  du lexique (et au moins SEUIL_SIGNE fois), se tape après la lettre : « = » puis le code du signe (=h haut, =m moyen, =b bas, =n nasal…) ;
  « == » donne « = » ;
- le clavier est « mnémonique » : ses règles portent sur les caractères tapés, il fonctionne donc
  avec un clavier AZERTY comme QWERTY (Keyman pour Windows, macOS, Linux).
Une lettre qui n'a pas de base connue est signalée, jamais inventée."""

import os
import re
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass, field

SEUIL_LETTRE = 10
SEUIL_SIGNE = 10
PART_SIGNE = 0.01   # 1 % : écarte les signes venus de quelques mots d'une autre orthographe

# lettre spéciale → lettre de base qui la tape (l'ordre fixe qui prend « ; » et qui prend « ;; »)
TABLE_BASES = [
    ("ɓ", "b"), ("β", "b"), ("ɗ", "d"), ("ɖ", "d"), ("ə", "e"), ("ɛ", "e"), ("ǝ", "e"),
    ("ɸ", "f"), ("ɣ", "g"), ("ɠ", "g"), ("ɦ", "h"), ("ɨ", "i"), ("ɩ", "i"), ("ƙ", "k"),
    ("ŋ", "n"), ("ɲ", "n"), ("ɔ", "o"), ("ɾ", "r"), ("ɽ", "r"), ("ʃ", "s"), ("ƭ", "t"),
    ("ʉ", "u"), ("ʊ", "u"), ("ʋ", "v"), ("ʌ", "v"), ("ƴ", "y"), ("ʒ", "z"), ("ʔ", "q"),
    # coup de glotte écrit comme une lettre : saltillo (kenga…) et apostrophe-lettre, tapés « '; »
    ("ꞌ", "'"), ("ʼ", "'"),
]

# signe combinant → (code tapé après « = », nom)
SIGNES = {
    "\u0301": ("h", "ton haut (aigu)"),
    "\u0304": ("m", "ton moyen (macron)"),
    "\u0300": ("b", "ton bas (grave)"),
    "\u0330": ("n", "nasalité (tilde souscrit)"),
    "\u0302": ("c", "ton descendant (circonflexe)"),
    "\u030c": ("v", "ton montant (caron)"),
    "\u0303": ("t", "tilde"),
    "\u0308": ("e", "tréma"),
    "\u030b": ("d", "double aigu"),
    "\u030f": ("g", "double grave"),
}

# caractères disponibles sans aide sur les claviers français et anglais
_CLAVIER_COURANT = set("abcdefghijklmnopqrstuvwxyzàâçéèêëîïôöùûüÿœæ'’-")


@dataclass
class Lettre:
    caractere: str
    base: str
    sequence: str
    majuscule: str = ""


@dataclass
class Signe:
    caractere: str
    code: str
    nom: str
    occurrences: int


@dataclass
class Inventaire:
    lettres: list[Lettre] = field(default_factory=list)
    signes: list[Signe] = field(default_factory=list)
    sans_base: list[str] = field(default_factory=list)


def inventaire(conn, alphabet=""):
    from collections import Counter
    lettres, signes = Counter(), Counter()
    textes = [r[0] or "" for r in conn.execute("SELECT forme FROM entrees")]
    declares = alphabet.split()
    signes_declares = {ch for g in declares for ch in unicodedata.normalize("NFD", g) if unicodedata.combining(ch)}
    for texte in textes + declares:
        declare = texte in declares   # ce qui est dans l'alphabet déclaré est toujours retenu
        for ch in unicodedata.normalize("NFD", texte):
            if unicodedata.combining(ch):
                if not declare:
                    signes[ch] += 1
            elif ch.isalpha():
                lettres[ch.lower()] += SEUIL_LETTRE if declare else 1
    resultat = Inventaire()
    bases = dict(TABLE_BASES)
    deja = {}
    for car, base in TABLE_BASES:
        if lettres.get(car, 0) >= SEUIL_LETTRE:
            rang = deja.get(base, 0) + 1
            deja[base] = rang
            resultat.lettres.append(Lettre(car, base, base + ";" * rang,
                                           car.upper() if car.upper() != car else ""))
    for car, n in sorted(lettres.items()):
        if n >= SEUIL_LETTRE and car not in _CLAVIER_COURANT and car not in bases and not car.isascii():
            resultat.sans_base.append(car)
    for ch in signes_declares:   # déclaré dans l'alphabet : retenu même s'il manque encore au lexique
        signes.setdefault(ch, 0)
    total = sum(n for ch, n in signes.items() if ch not in signes_declares)
    for ch, n in signes.most_common():
        if ch not in signes_declares and (n < SEUIL_SIGNE or n < PART_SIGNE * total):
            continue
        if ch in SIGNES:
            code, nom = SIGNES[ch]
            resultat.signes.append(Signe(ch, code, nom, n))
        else:
            resultat.sans_base.append(ch)
    return resultat


def identifiant(nom_langue):
    """Identifiant Keyman : minuscules ASCII, chiffres et _ ; ne commence pas par un chiffre."""
    base = unicodedata.normalize("NFD", nom_langue or "langue").encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "_", base).strip("_") or "langue"
    if base[0].isdigit():
        base = "k_" + base
    return f"gerro_{base}"


def _u(ch):
    return " ".join(f"U+{ord(c):04X}" for c in ch)


def construire_kmn(inv, nom_langue, ident, version="1.0"):
    lignes = [
        f"c Clavier {nom_langue} produit par Gerro Lexicographe à partir des données du projet.",
        "c Lettres : lettre de base + ;   Signes : après la lettre, = puis le code.",
        "",
        "store(&VERSION) '10.0'",
        f"store(&NAME) '{nom_langue} (Gerro)'",
        "store(&MNEMONICLAYOUT) '1'",
        "store(&TARGETS) 'windows macosx linux'",
        f"store(&KEYBOARDVERSION) '{version}'",
        "store(&COPYRIGHT) 'Gerro Lexicographe'",
        "",
        "begin Unicode > use(main)",
        "",
        "group(main) using keys",
        "",
        "c --- lettres spéciales ---",
    ]
    par_base = {}
    for l in inv.lettres:
        par_base.setdefault(l.base, []).append(l)
    for base, groupe in par_base.items():
        # une base sans majuscule (apostrophe) n'a qu'une suite : sinon deux règles identiques
        for casse in ("min", "maj") if base.upper() != base else ("min",):
            chaine = [base if casse == "min" else base.upper()] + [
                l.caractere if casse == "min" else (l.majuscule or l.caractere) for l in groupe]
            for avant, apres in zip(chaine, chaine[1:]):
                lignes.append(f"{_u(avant)} + ';' > {_u(apres)}")
            # un « ; » de plus : la lettre de base et « ; » (pour écrire « b; » lui-même)
            lignes.append(f"{_u(chaine[-1])} + ';' > {_u(chaine[0])} ';'")
    lignes += ["", "c --- signes : « = » puis le code ; « == » donne « = » ---",
               "+ '=' > '=' dk(signe)",
               "'=' dk(signe) + '=' > '='"]
    for s in inv.signes:
        for code in dict.fromkeys((s.code, s.code.upper())):
            lignes.append(f"'=' dk(signe) + '{code}' > {_u(s.caractere)}   c {s.nom}")
    return "\n".join(lignes) + "\n"


def aide_html(inv, nom_langue):
    lignes = "".join(f"<tr><td class='t'>{l.sequence}</td><td class='c'>{l.caractere}</td>"
                     f"<td class='t'>{l.base.upper()}{l.sequence[1:]}</td><td class='c'>{l.majuscule}</td></tr>"
                     for l in inv.lettres)
    signes = "".join(f"<tr><td class='t'>a={s.code}</td><td class='c'>{unicodedata.normalize('NFC', 'a' + s.caractere)}"
                     f"</td><td colspan='2'>{s.nom}</td></tr>" for s in inv.signes)
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Clavier {nom_langue}</title>
<style>body{{font-family:'Charis SIL','Segoe UI',sans-serif;margin:2em;max-width:42em}}
table{{border-collapse:collapse;margin:1em 0}}td,th{{border:1px solid #bbb;padding:.3em .8em}}
.c{{font-size:1.6em;text-align:center}}.t{{font-family:Consolas,monospace}}</style></head><body>
<h1>Clavier {nom_langue}</h1>
<p>Ce clavier fonctionne avec un clavier français (AZERTY) ou anglais (QWERTY). Choisissez-le dans
Keyman, puis tapez :</p>
<h2>Lettres</h2><table><tr><th>Tapez</th><th>Obtenu</th><th>Majuscule</th><th></th></tr>{lignes}</table>
<h2>Tons et signes</h2><p>Après la lettre, tapez <b>=</b> puis le code :</p>
<table><tr><th>Exemple</th><th>Obtenu</th><th colspan="2">Signe</th></tr>{signes}</table>
<p>Pour écrire « ; » après une de ces lettres, ou « = », tapez-les deux fois.</p>
<p><small>Produit par Gerro Lexicographe à partir de l'alphabet et du lexique du projet.</small></p>
</body></html>"""


def construire_kps(nom_langue, ident, version="1.0"):
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Package>
  <System>
    <KeymanDeveloperVersion>18.0</KeymanDeveloperVersion>
    <FileVersion>7.0</FileVersion>
  </System>
  <Options>
    <ReadMeFile>welcome.htm</ReadMeFile>
  </Options>
  <Info>
    <Name URL="">{nom_langue} (Gerro)</Name>
    <Version URL="">{version}</Version>
    <Copyright URL="">Gerro Lexicographe</Copyright>
  </Info>
  <Files>
    <File>
      <Name>{ident}.kmx</Name>
      <Description>Clavier {nom_langue}</Description>
      <CopyLocation>0</CopyLocation>
      <FileType>.kmx</FileType>
    </File>
    <File>
      <Name>welcome.htm</Name>
      <Description>Aide du clavier</Description>
      <CopyLocation>0</CopyLocation>
      <FileType>.htm</FileType>
    </File>
  </Files>
  <Keyboards>
    <Keyboard>
      <Name>{nom_langue} (Gerro)</Name>
      <ID>{ident}</ID>
      <Version>{version}</Version>
      <Languages>
        <Language ID="und">{nom_langue}</Language>
      </Languages>
    </Keyboard>
  </Keyboards>
</Package>
"""


def compilateur():
    """Chemin de kmc (Keyman Developer) s'il est installé."""
    for dossier in (r"C:\Program Files (x86)\Keyman\Keyman Developer", r"C:\Program Files\Keyman\Keyman Developer"):
        chemin = os.path.join(dossier, "kmc.cmd")
        if os.path.isfile(chemin):
            return chemin
    return shutil.which("kmc")


@dataclass
class Resultat:
    dossier: str
    kmn: str
    paquet: str = ""        # .kmp installable, si Keyman Developer a compilé
    aide: str = ""
    message: str = ""
    inventaire: Inventaire | None = None


def generer(projet, dossier):
    """Écrit le clavier (source .kmn, aide, paquet .kps) dans `dossier`, puis le compile en paquet
    installable .kmp si Keyman Developer est présent."""
    nom = projet.reglage("langue_vern_nom") or projet.nom or "langue"
    nom = nom[:1].upper() + nom[1:]
    ident = identifiant(nom)
    inv = inventaire(projet.conn, projet.reglage("alphabet_vern"))
    if not inv.lettres and not inv.signes:
        raise ValueError("Aucune lettre spéciale ni aucun signe dans ce projet : un clavier ordinaire suffit.")
    source = os.path.join(dossier, ident)
    os.makedirs(source, exist_ok=True)
    kmn = os.path.join(source, f"{ident}.kmn")
    with open(kmn, "w", encoding="utf-8-sig") as f:
        f.write(construire_kmn(inv, nom, ident))
    aide = os.path.join(source, "welcome.htm")
    with open(aide, "w", encoding="utf-8") as f:
        f.write(aide_html(inv, nom))
    kps = os.path.join(source, f"{ident}.kps")
    with open(kps, "w", encoding="utf-8") as f:
        f.write(construire_kps(nom, ident))
    resultat = Resultat(dossier=source, kmn=kmn, aide=aide, inventaire=inv)
    kmc = compilateur()
    if not kmc:
        resultat.message = ("Keyman Developer n'est pas installé : le clavier est prêt en source (.kmn) ; "
                            "il peut être compilé plus tard avec Keyman Developer.")
        return resultat
    try:
        for fichier in (kmn, kps):
            sortie = subprocess.run([kmc, "build", fichier], cwd=source, capture_output=True, text=True,
                                    timeout=180, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if sortie.returncode != 0:
                raise RuntimeError((sortie.stdout + sortie.stderr).strip()[-1500:])
    except (OSError, subprocess.SubprocessError, RuntimeError) as e:
        resultat.message = f"La compilation par Keyman Developer a échoué :\n{e}"
        return resultat
    paquet = os.path.join(source, f"{ident}.kmp")
    if os.path.isfile(paquet):
        resultat.paquet = paquet
    else:
        resultat.message = "Keyman Developer n'a pas produit de paquet .kmp."
    return resultat

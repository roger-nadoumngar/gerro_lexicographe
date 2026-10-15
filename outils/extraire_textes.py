"""Relève les textes français de l'interface dans le code (sans le modifier).

    python outils/extraire_textes.py            → écrit la liste des textes à traduire
    python outils/extraire_textes.py --manquants → n'affiche que ceux qui n'ont pas de traduction

Règles :
- interface (lexicographe/ui) : toutes les chaînes et f-strings, sauf docstrings, requêtes SQL, noms
  de style et chaînes sans lettre ;
- autres modules : seulement les textes montrés à l'utilisateur, c'est-à-dire les chaînes contenant
  des mots français (lettres accentuées ou espace) dans les fonctions `resume` et les exceptions
  levées, et les libellés des tables de constantes (TACHES, SIGNES…) ;
- une f-string devient un gabarit : chaque valeur insérée est notée {}.
Résultat : lexicographe/ressources/interface/textes.json (liste triée)."""

import ast
import glob
import json
import os
import re
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SORTIE = os.path.join(RACINE, "lexicographe", "ressources", "interface", "textes.json")
TRADUCTIONS = os.path.join(RACINE, "lexicographe", "ressources", "interface", "en.json")

_SQL = re.compile(r"^\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|PRAGMA|WITH|ALTER|DROP)\b", re.I)
# feuille de style : « sélecteur { propriété: valeur; } » ou « propriété: valeur; »
_STYLE = re.compile(r"^[#.\w\-][^{}]*\{[^}]*:[^}]*;|^Q\w+\s*[{#.:]|^[\w\-]+\s*:\s*[^;]+;")
# identifiants : clés de réglages (avec _), fichiers ou chemins (. / \), méthodes Qt (camelCase), codes avec chiffres
_CLE = re.compile(r"^[a-z0-9]*[_./\\*][\w.\-/\\*]*$|^[a-z]+[A-Z]\w*$|^[a-z0-9\-]*\d[a-z0-9\-]*$")


def gabarit(noeud):
    if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
        return noeud.value
    if isinstance(noeud, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in noeud.values)
    return None


def _utile(texte, interface, table=False):
    if not texte or not re.search(r"[A-Za-zÀ-ÿ]", texte) or _SQL.match(texte) or _STYLE.match(texte.strip()):
        return False
    if (_CLE.match(texte) and not table) or texte.strip() in ("{}", ""):
        return False
    if texte.startswith(("<?xml", "<!doctype", "http", "org.", "--", "-cp")) or "\\u" in texte:
        return False
    if not interface:   # hors interface : seulement ce qui ressemble à du français
        return bool(re.search(r"[À-ÿ]", texte) or " " in texte.strip())
    return True


def textes_du_fichier(chemin, interface):
    arbre = ast.parse(open(chemin, encoding="utf-8").read())
    exclus = set()
    for n in ast.walk(arbre):
        corps = getattr(n, "body", None)
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and corps and isinstance(corps[0], ast.Expr) \
                and isinstance(corps[0].value, ast.Constant) and isinstance(corps[0].value.value, str):
            exclus.add(id(corps[0].value))
        if isinstance(n, ast.JoinedStr):
            exclus.update(id(v) for v in n.values)   # morceaux d'une f-string : seul le gabarit compte
    zones = []
    if interface:
        zones = [arbre]
    else:
        for n in ast.walk(arbre):
            if isinstance(n, ast.FunctionDef) and n.name in ("resume",):
                zones.append(n)
            elif isinstance(n, ast.Raise):
                zones.append(n)
            elif isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in (
                    "TACHES", "SIGNES", "TYPES_RELATIONS", "STATUTS", "TYPES_VARIANTES", "TYPES_FORMES_COMPLEXES",
                    "TYPES_MORPH", "ETIQUETTES", "LIBELLES_STATUT") for t in n.targets):
                zones.append(n)
            elif isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "append" and \
                    getattr(getattr(n.func, "value", None), "attr", "") == "avertissements":
                zones.append(n)
    trouves = set()
    for zone in zones:
        # tables de libellés (statuts, types…) : tous leurs textes sont montrés, même sans accent
        table = isinstance(zone, ast.Assign)
        comme_interface = interface or table
        for n in ast.walk(zone):
            if id(n) in exclus:
                continue
            t = gabarit(n)
            if t is not None and _utile(t, comme_interface, table):
                trouves.add(t)
    return trouves


def tous_les_textes():
    textes = set()
    for f in glob.glob(os.path.join(RACINE, "lexicographe", "ui", "*.py")):
        textes |= textes_du_fichier(f, True)
    for f in glob.glob(os.path.join(RACINE, "lexicographe", "*.py")):
        textes |= textes_du_fichier(f, False)
    return sorted(textes)


if __name__ == "__main__":
    textes = tous_les_textes()
    if "--manquants" in sys.argv:
        faits = json.load(open(TRADUCTIONS, encoding="utf-8")) if os.path.isfile(TRADUCTIONS) else {}
        manquants = [t for t in textes if t not in faits]
        print(json.dumps(manquants, ensure_ascii=False, indent=1))
        print(f"{len(manquants)} texte(s) sans traduction sur {len(textes)}", file=sys.stderr)
    else:
        os.makedirs(os.path.dirname(SORTIE), exist_ok=True)
        with open(SORTIE, "w", encoding="utf-8") as f:
            json.dump(textes, f, ensure_ascii=False, indent=1)
        print(f"{len(textes)} textes -> {SORTIE}")

"""Assemble la traduction anglaise de l'interface (ressources/interface/en.json).

    python outils/extraire_textes.py           (relève les textes du code)
    python outils/construire_traductions.py    (assemble outils/traductions/en_*.py)

Chaque texte relevé reçoit sa traduction, ou reste tel quel s'il n'en a pas (codes, couleurs, noms
de polices…). Les textes laissés tels quels qui ressemblent à du français sont listés : à traduire."""

import glob
import importlib.util
import json
import os
import re

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIER = os.path.join(RACINE, "lexicographe", "ressources", "interface")


def traductions():
    t = {}
    for f in sorted(glob.glob(os.path.join(RACINE, "outils", "traductions", "en_*.py"))):
        spec = importlib.util.spec_from_file_location(os.path.basename(f)[:-3], f)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        t.update(module.T)
    return t


def ressemble_au_francais(texte):
    return bool(re.search(r"[À-ÿ]", texte) or re.search(r"\b(le|la|les|des|du|une|un|est|et|pour|dans)\b", texte))


def main():
    textes = json.load(open(os.path.join(DOSSIER, "textes.json"), encoding="utf-8"))
    t = traductions()
    resultat = {x: t.get(x, x) for x in textes}
    with open(os.path.join(DOSSIER, "en.json"), "w", encoding="utf-8") as f:
        json.dump(resultat, f, ensure_ascii=False, indent=1, sort_keys=True)
    a_revoir = [x for x in textes if x not in t and ressemble_au_francais(x)]
    inutiles = [x for x in t if x not in resultat]
    print(f"{len(textes)} textes, {sum(1 for x in textes if x in t)} traduits")
    if a_revoir:
        print("Encore en français :", json.dumps(a_revoir, ensure_ascii=False, indent=1))
    if inutiles:
        print(f"{len(inutiles)} traduction(s) sans texte correspondant (texte modifié dans le code ?)")


if __name__ == "__main__":
    main()

"""Construit la liste des domaines sémantiques livrée avec le logiciel (français et anglais).

    python outils/construire_domaines.py SemDom.xml LocalizedLists-fr.zip

- SemDom.xml : liste officielle en anglais, https://semdom.org/SemDom.xml
- LocalizedLists-fr.zip : traduction française livrée avec FieldWorks (dossier Templates)

Les deux sont réunies domaine par domaine (même guid) ; chaque question garde sa place.
Résultat : lexicographe/ressources/domaines/semdom-fr-en.json.gz
"""

import gzip
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lexicographe import domaines  # noqa: E402

LANGUES = ("en", "fr")


def reunir(listes):
    par_guid, ordre = {}, []
    for liste in listes:
        for d in liste:
            cible = par_guid.get(d["guid"])
            if cible is None:
                par_guid[d["guid"]] = cible = {"guid": d["guid"], "code": d["code"], "parent": d["parent"],
                                               "noms": {}, "descriptions": {}, "questions": []}
                ordre.append(d["guid"])
            for champ in ("noms", "descriptions"):
                cible[champ].update({ws: t for ws, t in d[champ].items() if ws in LANGUES})
            for i, q in enumerate(d["questions"]):
                while len(cible["questions"]) <= i:
                    cible["questions"].append({"question": {}, "mots": {}, "phrases": {}})
                for champ in ("question", "mots", "phrases"):
                    cible["questions"][i][champ].update({ws: t for ws, t in q[champ].items() if ws in LANGUES})
    return [par_guid[g] for g in ordre]


def main(chemins):
    liste = reunir([domaines.lire_liste(c) for c in chemins])
    sortie = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "lexicographe", "ressources", "domaines", "semdom-fr-en.json.gz")
    os.makedirs(os.path.dirname(sortie), exist_ok=True)
    with gzip.open(sortie, "wt", encoding="utf-8") as f:
        json.dump(liste, f, ensure_ascii=False, separators=(",", ":"))
    complets = {ws: sum(1 for d in liste if d["noms"].get(ws)) for ws in LANGUES}
    print(f"{len(liste)} domaines, noms : {complets}, {os.path.getsize(sortie) // 1024} Ko -> {sortie}")


if __name__ == "__main__":
    main(sys.argv[1:])

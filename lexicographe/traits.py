"""Traits grammaticaux déclarés par le linguiste (classe nominale, ton, transitivité…).

Un trait déclaré a une liste fermée de valeurs : une entrée ne peut pas recevoir une
valeur qui n'y figure pas. Les propriétés non déclarées restent libres.
Les traits sont stockés dans les réglages du projet (clé « traits_grammaticaux », JSON).
"""

import json

from .texte import normaliser


def lire(projet):
    """{nom du trait: [valeurs permises]} dans l'ordre de déclaration."""
    try:
        donnees = json.loads(projet.reglage("traits_grammaticaux") or "{}")
    except ValueError:
        return {}
    return {nom: list(valeurs) for nom, valeurs in donnees.items()}


def enregistrer(projet, traits):
    propres = {}
    for nom, valeurs in traits.items():
        nom = normaliser(nom).strip()
        valeurs = list(dict.fromkeys(normaliser(v).strip() for v in valeurs if v.strip()))
        if nom:
            propres[nom] = valeurs
    projet.definir_reglages({"traits_grammaticaux": json.dumps(propres, ensure_ascii=False)})
    return propres


def verifier(traits, proprietes):
    """Messages pour chaque valeur non permise d'un trait déclaré ([] si tout est conforme)."""
    problemes = []
    for nom, valeur in proprietes.items():
        if nom in traits and traits[nom] and valeur not in traits[nom]:
            problemes.append(f"« {valeur} » n'est pas une valeur déclarée du trait « {nom} » "
                             f"(valeurs permises : {', '.join(traits[nom])}).")
    return problemes


def utilisations(conn, nom):
    """{valeur: nombre d'entrées} pour un trait (ou une propriété libre) de ce nom."""
    return dict(conn.execute("SELECT valeur, COUNT(*) FROM proprietes WHERE nom=? GROUP BY valeur", (nom,)))

"""Inscription des utilisateurs (demandée au démarrage, jamais bloquante).

Chaque personne demande un code en donnant son adresse e-mail ; le responsable du logiciel le
produit avec outils/codes_inscription.py et sa clé privée (gardée hors du dépôt). Le code est la
signature Ed25519 de l'adresse : le logiciel la vérifie avec la clé publique ci-dessous, sans
internet. L'inscription est gardée dans le dossier des données du logiciel (inscription.json).

Une telle vérification sert à savoir qui utilise le logiciel ; elle n'est pas un verrou : le
logiciel fonctionne entièrement sans inscription."""

import base64
import json
import os
from datetime import date

# clé publique de vérification (la clé privée correspondante n'est jamais dans le dépôt)
CLE_PUBLIQUE = "Hp8GalUxBSqEmFi9tIwmyJbjeLsvJMQcP+kuDMWb8go="
# adresse ou formulaire où demander un code (affiché dans la fenêtre d'inscription)
CONTACT = ""
PREFIXE = "GL1"


def normaliser_email(email):
    return (email or "").strip().lower()


def _code_en_octets(code):
    brut = "".join(c for c in (code or "").upper() if c.isalnum())
    if brut.startswith(PREFIXE):
        brut = brut[len(PREFIXE):]
    brut += "=" * (-len(brut) % 8)
    return base64.b32decode(brut)


def code_lisible(signature):
    """Signature → « GL1-XXXXX-XXXXX-… » (groupes de 5 lettres et chiffres, sans ambiguïté de casse)."""
    texte = base64.b32encode(signature).decode().rstrip("=")
    return PREFIXE + "-" + "-".join(texte[i:i + 5] for i in range(0, len(texte), 5))


def code_valide(email, code, cle_publique=None):
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    cle = cle_publique if cle_publique is not None else CLE_PUBLIQUE
    if not cle or not email or not code:
        return False
    try:
        publique = Ed25519PublicKey.from_public_bytes(base64.b64decode(cle))
        publique.verify(_code_en_octets(code), normaliser_email(email).encode("utf-8"))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def _fichier():
    from .chemins import dossier_donnees
    return os.path.join(dossier_donnees(), "inscription.json")


def lire():
    try:
        with open(_fichier(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def inscrit(cle_publique=None):
    """Adresse inscrite si l'inscription enregistrée est valide, sinon None."""
    d = lire()
    return d.get("email") if code_valide(d.get("email"), d.get("code"), cle_publique) else None


def enregistrer(email, code, nom=""):
    os.makedirs(os.path.dirname(_fichier()), exist_ok=True)
    with open(_fichier(), "w", encoding="utf-8") as f:
        json.dump({"email": normaliser_email(email), "code": code.strip(), "nom": nom.strip(),
                   "date": date.today().isoformat()}, f, ensure_ascii=False)


def plus_tard():
    """« Plus tard » : la demande revient un autre jour."""
    d = lire()
    d["rappel"] = date.today().isoformat()
    os.makedirs(os.path.dirname(_fichier()), exist_ok=True)
    with open(_fichier(), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)


def a_demander():
    """La demande s'affiche au démarrage tant que l'on n'est pas inscrit, au plus une fois par jour."""
    return inscrit() is None and lire().get("rappel") != date.today().isoformat()

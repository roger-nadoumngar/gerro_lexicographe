"""Codes d'inscription de Gerro Lexicographe (pour le responsable du logiciel seulement).

    python outils/codes_inscription.py creer-cle
        crée la paire de clés : la clé PRIVÉE est écrite hors du dépôt (Documents), la clé publique
        est affichée, à copier dans lexicographe/inscription.py (CLE_PUBLIQUE). À faire une seule fois.

    python outils/codes_inscription.py code personne@exemple.org "Nom Prénom"
        produit le code de cette adresse, à lui envoyer, et ajoute la personne à la liste des inscrits
        (Documents/GerroLexicographe-inscrits.csv).

La clé privée ne doit jamais être partagée ni mise sur GitHub : avec elle, n'importe qui pourrait
produire des codes. Gardez-en une copie de secours (clé USB) : sans elle, plus aucun code."""

import base64
import csv
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lexicographe import inscription  # noqa: E402

DOCUMENTS = os.path.join(os.path.expanduser("~"), "Documents")
CLE_PRIVEE = os.path.join(DOCUMENTS, "GerroLexicographe-cle-inscription-PRIVEE.pem")
INSCRITS = os.path.join(DOCUMENTS, "GerroLexicographe-inscrits.csv")


def creer_cle():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    if os.path.exists(CLE_PRIVEE):
        sys.exit(f"Une clé existe déjà : {CLE_PRIVEE}\nLa remplacer rendrait invalides tous les codes déjà donnés.")
    privee = Ed25519PrivateKey.generate()
    with open(CLE_PRIVEE, "wb") as f:
        f.write(privee.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption()))
    publique = privee.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    print(f"Clé privée écrite : {CLE_PRIVEE}  (à garder secrète, avec une copie de secours)")
    print(f"Clé publique (à mettre dans lexicographe/inscription.py) : {base64.b64encode(publique).decode()}")


def produire_code(email):
    from cryptography.hazmat.primitives import serialization
    with open(CLE_PRIVEE, "rb") as f:
        privee = serialization.load_pem_private_key(f.read(), password=None)
    return inscription.code_lisible(privee.sign(inscription.normaliser_email(email).encode("utf-8")))


def code(email, nom=""):
    c = produire_code(email)
    nouveau = not os.path.exists(INSCRITS)
    with open(INSCRITS, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        if nouveau:
            w.writerow(["date", "nom", "email", "code"])
        w.writerow([date.today().isoformat(), nom, inscription.normaliser_email(email), c])
    print(c)
    if not inscription.code_valide(email, c):
        print("Attention : ce code ne correspond pas à la clé publique du logiciel (CLE_PUBLIQUE).")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "creer-cle":
        creer_cle()
    elif len(sys.argv) >= 3 and sys.argv[1] == "code":
        code(sys.argv[2], " ".join(sys.argv[3:]))
    else:
        print(__doc__)

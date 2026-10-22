import base64
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from lexicographe import inscription  # noqa: E402


@pytest.fixture
def cle(monkeypatch, tmp_path):
    """Paire de clés de test : la vraie clé privée n'est jamais utilisée par les tests."""
    privee = Ed25519PrivateKey.generate()
    publique = privee.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    monkeypatch.setattr(inscription, "CLE_PUBLIQUE", base64.b64encode(publique).decode())
    monkeypatch.setattr("lexicographe.chemins.dossier_donnees", lambda *a: str(tmp_path / "donnees"))
    return lambda email: inscription.code_lisible(privee.sign(inscription.normaliser_email(email).encode()))


def test_code_valide_pour_son_adresse_seulement(cle):
    code = cle("Personne@Exemple.org")
    assert code.startswith("GL1-")
    assert inscription.code_valide("personne@exemple.org", code)
    assert inscription.code_valide("  PERSONNE@exemple.org ", code.lower().replace("-", " "))
    assert not inscription.code_valide("autre@exemple.org", code)
    milieu = len(code) // 2
    altere = code[:milieu] + ("A" if code[milieu] != "A" else "B") + code[milieu + 1:]
    assert not inscription.code_valide("personne@exemple.org", altere)
    assert not inscription.code_valide("personne@exemple.org", "n'importe quoi")
    assert not inscription.code_valide("", code)


def test_enregistrer_et_rappel(cle):
    assert inscription.a_demander()
    inscription.plus_tard()
    assert not inscription.a_demander()           # pas deux fois le même jour
    assert inscription.inscrit() is None
    inscription.enregistrer("personne@exemple.org", cle("personne@exemple.org"), "Personne")
    assert inscription.inscrit() == "personne@exemple.org"
    assert not inscription.a_demander()


def test_cle_publique_livree_est_valide():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    Ed25519PublicKey.from_public_bytes(base64.b64decode(inscription.CLE_PUBLIQUE))


def test_dialogue(cle, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from lexicographe.ui import inscription_ui
    QApplication.instance() or QApplication([])
    vus = []
    monkeypatch.setattr(inscription_ui, "erreur", lambda *a: vus.append("erreur"))
    monkeypatch.setattr(inscription_ui, "info", lambda *a: vus.append("info"))
    d = inscription_ui.DialogueInscription()
    d.email.setText("personne@exemple.org")
    d.code.setText("GL1-FAUX")
    d._valider()
    assert vus == ["erreur"] and inscription.inscrit() is None
    d.code.setText(cle("personne@exemple.org"))
    d._valider()
    assert vus[-1] == "info" and inscription.inscrit() == "personne@exemple.org"

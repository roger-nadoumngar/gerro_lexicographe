"""Normalisation Unicode et découpage en mots.

Le découpage suit des règles déclarées par le linguiste pour chaque langue,
jamais une liste de ponctuation codée en dur :

* un mot est une suite de lettres, de marques combinantes (tons,
  nasalisation, tilde souscrit…) et de chiffres ;
* plus les caractères que le projet déclare comme faisant partie des mots
  (trait d'union, apostrophe, coup de glotte…) ;
* tout autre caractère sépare les mots.
"""

import unicodedata


def normaliser(texte):
    """Forme Unicode unique (NFC). Les sources mélangent souvent lettres
    précomposées (á) et décomposées (a + accent combinant) : sans cette étape,
    un même mot serait compté comme deux mots différents."""
    return unicodedata.normalize("NFC", texte or "")


class Tokeniseur:
    def __init__(self, caracteres_mot="", longueur_min=1, mots_vides=()):
        self.caracteres_mot = frozenset(normaliser(caracteres_mot))
        self.longueur_min = max(1, int(longueur_min))
        self.mots_vides = frozenset(normaliser(m).lower() for m in mots_vides)
        self._bordures = "".join(self.caracteres_mot)

    def _dans_mot(self, ch):
        return ch in self.caracteres_mot or unicodedata.category(ch)[0] in "LMN"

    def mots(self, texte):
        """Tous les mots du texte, en minuscules, dans l'ordre."""
        resultat, courant = [], []
        for ch in normaliser(texte).lower():
            if self._dans_mot(ch):
                courant.append(ch)
            elif courant:
                resultat.append("".join(courant))
                courant = []
        if courant:
            resultat.append("".join(courant))
        # un caractère de mot déclaré qui reste en bordure (tiret ou apostrophe
        # isolés) n'appartient à aucun mot
        resultat = [m.strip(self._bordures) for m in resultat]
        return [m for m in resultat if self._est_mot(m)]

    def decouper(self, texte):
        """Texte découpé en morceaux successifs [(morceau tel qu'écrit, mot normalisé
        ou None)] : la concaténation des morceaux redonne le texte (normalisé NFC).
        Sert à surligner des mots sans perdre la ponctuation."""
        texte = normaliser(texte)
        morceaux, debut, i = [], 0, 0
        while i < len(texte):
            if self._dans_mot(texte[i]):
                j = i
                while j < len(texte) and self._dans_mot(texte[j]):
                    j += 1
                brut = texte[i:j]
                coeur = brut.strip(self._bordures)
                g = brut.index(coeur) if coeur else len(brut)
                if debut < i + g:
                    morceaux.append((texte[debut:i + g], None))
                if coeur:
                    mot = coeur.lower()
                    morceaux.append((coeur, mot if self._est_mot(mot) else None))
                debut = i + g + len(coeur)
                i = j
            else:
                i += 1
        if debut < len(texte):
            morceaux.append((texte[debut:], None))
        return morceaux

    def _est_mot(self, mot):
        # longueur comptée en caractères de base : une marque combinante n'est pas une lettre
        lettres = sum(1 for ch in mot if unicodedata.category(ch)[0] != "M")
        return lettres >= self.longueur_min

    def mots_pleins(self, texte):
        """Mots du texte sans les mots vides déclarés (articles, prépositions…)."""
        return [m for m in self.mots(texte) if m not in self.mots_vides]


MOTS_VIDES_FRANCAIS = """le la les un une des de du et à en il elle ils elles je tu nous vous
que qui ce cet cette ces son sa ses leur leurs mais ou dans sur pour avec par comme au aux
se lui même était fut être avoir a ont étaient point pas ne s on y d l qu n j t c m""".split()

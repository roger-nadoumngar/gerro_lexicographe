"""Fusion du travail fait sur un autre poste (autre fichier .lexique de la même langue).

Règles explicites, rapportées à l'utilisateur :
* une entrée est reconnue par son identifiant (guid), quel que soit l'ordinateur ;
* entrée absente ici : ajoutée, avec ses enregistrements et images ;
* entrée présente des deux côtés : la version modifiée le plus récemment l'emporte ;
  à égalité, la version locale est gardée ;
* une phrase du corpus absente ici est ajoutée ; une phrase existante n'est pas modifiée ;
* le fichier de l'autre poste n'est jamais modifié ; une sauvegarde locale est faite avant.
"""

import os
import sqlite3
from dataclasses import dataclass, field

from . import base, lexique
from .projet import copier_medias


@dataclass
class Rapport:
    ajoutees: int = 0
    mises_a_jour: int = 0
    gardees: int = 0
    identiques: int = 0
    phrases: int = 0
    medias: int = 0
    avertissements: list[str] = field(default_factory=list)

    def resume(self):
        lignes = [f"{self.ajoutees} entrée(s) ajoutée(s), {self.mises_a_jour} mise(s) à jour par une version plus "
                  f"récente, {self.gardees} gardée(s) car la version d'ici est plus récente, "
                  f"{self.identiques} identique(s).",
                  f"{self.phrases} phrase(s) ajoutée(s) au corpus, {self.medias} enregistrement(s) ou image(s)."]
        if self.avertissements:
            lignes.append("Avertissements :")
            lignes.extend("  • " + a for a in self.avertissements[:30])
        return "\n".join(lignes)


def _ouvrir_lecture(chemin):
    conn = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True)
    if base.version(conn) != base.VERSION_SCHEMA:
        conn.close()
        raise ValueError("L'autre projet n'est pas à la même version du logiciel : ouvre-le une fois avec cette "
                         "version (il sera mis à jour), puis recommence la fusion.")
    return conn


def _categorie_locale(conn_local, conn_autre, categorie_id):
    if categorie_id is None:
        return None
    nom = lexique.nom_categorie(conn_autre, categorie_id)
    return lexique.categorie_par_nom(conn_local, nom, creer=True) if nom else None


def fusionner(projet, chemin_autre):
    """Fusionne l'autre projet dans celui-ci. Retourne un Rapport."""
    if os.path.abspath(chemin_autre) == os.path.abspath(projet.chemin):
        raise ValueError("C'est le projet ouvert lui-même.")
    autre = _ouvrir_lecture(chemin_autre)
    r = Rapport()
    conn = projet.conn
    try:
        code_autre = autre.execute("SELECT valeur FROM projet WHERE cle='langue_vern_code'").fetchone()
        if code_autre and code_autre[0] and code_autre[0] != projet.reglage("langue_vern_code"):
            r.avertissements.append(f"L'autre projet est en « {code_autre[0]} », celui-ci en "
                                    f"« {projet.reglage('langue_vern_code')} ».")
        locaux = {g: (i, d or "") for g, i, d in conn.execute("SELECT guid, id, date_modification FROM entrees")}
        domaines_ici = {g for (g,) in conn.execute("SELECT guid FROM domaines")}
        correspondance = {}          # id de l'autre → id local
        ajoutees = set()             # ids (de l'autre) des entrées ajoutées ici
        with projet.en_lot():
            for (aid, guid, date) in autre.execute("SELECT id, guid, date_modification FROM entrees").fetchall():
                entree = lexique.lire_entree(autre, aid)
                for s in entree.sens:
                    s.categorie_id = _categorie_locale(conn, autre, s.categorie_id)
                    s.domaines = [g for g in s.domaines if g in domaines_ici]
                    s.id = None
                    for x in s.exemples:
                        x.id = None
                for v in entree.variantes:
                    v.id = None
                entree.composants = []
                if guid in locaux:
                    lid, date_locale = locaux[guid]
                    correspondance[aid] = lid
                    if (date or "") > date_locale:
                        locale = lexique.lire_entree(conn, lid)
                        entree.id, entree.date_creation = lid, locale.date_creation
                        entree.composants = locale.composants
                        lexique.enregistrer_entree(conn, entree)
                        # la date de l'autre poste est gardée : une seconde fusion ne refait rien
                        conn.execute("UPDATE entrees SET date_modification=? WHERE id=?", (date, lid))
                        r.mises_a_jour += 1
                    elif (date or "") < date_locale:
                        r.gardees += 1
                    else:
                        r.identiques += 1
                    continue
                entree.id = None
                lid = lexique.enregistrer_entree(conn, entree)
                conn.execute("UPDATE entrees SET date_modification=? WHERE id=?", (date, lid))
                correspondance[aid] = lid
                ajoutees.add(aid)
                r.ajoutees += 1
                for _, _, role, sens_id, nom, chemin, note in lexique.medias_de(autre, aid):
                    if os.path.isfile(chemin):
                        lexique.lier_media(conn, lid, copier_medias(projet, chemin), role, note)
                        r.medias += 1
                    else:
                        r.avertissements.append(f"Fichier introuvable : {chemin}")
            # composants et relations des entrées ajoutées, une fois toutes les entrées connues
            # (une entrée locale gardée ou mise à jour n'en reçoit pas)
            for aid in ajoutees:
                lid = correspondance[aid]
                for (cid,) in autre.execute("SELECT composant_id FROM composants WHERE entree_id=? ORDER BY ordre",
                                            (aid,)):
                    if cid in correspondance and not conn.execute(
                            "SELECT 1 FROM composants WHERE entree_id=? AND composant_id=?",
                            (lid, correspondance[cid])).fetchone():
                        conn.execute("INSERT INTO composants (entree_id, composant_id, ordre) VALUES (?, ?, 99)",
                                     (lid, correspondance[cid]))
                for cible, typ in autre.execute("SELECT cible_id, type FROM relations WHERE source_id=?", (aid,)):
                    if cible in correspondance:
                        conn.execute("INSERT OR IGNORE INTO relations (source_id, cible_id, type) VALUES (?, ?, ?)",
                                     (lid, correspondance[cible], typ))
            for ref, vern, analyse, source in autre.execute(
                    "SELECT ref, vernaculaire, analyse, source FROM phrases").fetchall():
                cur = conn.execute("INSERT OR IGNORE INTO phrases (ref, vernaculaire, analyse, source) "
                                   "VALUES (?, ?, ?, ?)", (ref, vern, analyse, source))
                r.phrases += cur.rowcount
            for ligne in autre.execute("SELECT code, titre, genre, locuteur, lieu, date, notes FROM textes"):
                conn.execute("INSERT OR IGNORE INTO textes (code, titre, genre, locuteur, lieu, date, notes) "
                             "VALUES (?, ?, ?, ?, ?, ?, ?)", ligne)
    finally:
        autre.close()
    return r

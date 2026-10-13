"""Import d'un projet Paratext : choix du projet, des livres et du contenu."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
                               QSplitter, QVBoxLayout, QWidget)

from .. import alignement, paratext, textes
from .commun import CurseurAttente, erreur, info


class DialogueParatext(QDialog):
    """Après acceptation : projet_pt, livres, cote, avec_livres, avec_glossaire, avec_termes."""

    def __init__(self, projet, parent=None):
        super().__init__(parent)
        self.projet = projet
        self.setWindowTitle("Importer un projet Paratext")
        self.resize(820, 560)
        self.projet_pt = None
        v = QVBoxLayout(self)
        self.dossier = paratext.dossier_projets_paratext()
        self.aide = QLabel()
        self.aide.setWordWrap(True)
        v.addWidget(self.aide)

        separateur = QSplitter(Qt.Horizontal)
        gauche = QWidget()
        gl = QVBoxLayout(gauche)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.addWidget(QLabel("<b>Projets</b>"))
        self.projets = QListWidget()
        self.projets.currentItemChanged.connect(self._projet_choisi)
        gl.addWidget(self.projets)
        autre = QPushButton("Autre dossier de projets…")
        autre.clicked.connect(self._autre_dossier)
        gl.addWidget(autre, 0, Qt.AlignLeft)
        separateur.addWidget(gauche)

        droite = QWidget()
        dl = QVBoxLayout(droite)
        dl.setContentsMargins(0, 0, 0, 0)
        self.titre_livres = QLabel("<b>Livres</b>")
        dl.addWidget(self.titre_livres)
        self.livres = QListWidget()
        self.livres.setSelectionMode(QAbstractItemView.NoSelection)
        dl.addWidget(self.livres)
        ligne = QHBoxLayout()
        for texte, etat in (("Tous", Qt.Checked), ("Aucun", Qt.Unchecked)):
            b = QPushButton(texte)
            b.clicked.connect(lambda _=False, e=etat: self._cocher(e))
            ligne.addWidget(b)
        ligne.addStretch()
        dl.addLayout(ligne)
        separateur.addWidget(droite)
        separateur.setSizes([380, 420])
        v.addWidget(separateur, 1)

        form = QFormLayout()
        self.cote = QComboBox()
        self.cote.addItem(f"langue du projet ({projet.reglage('langue_vern_nom') or projet.reglage('langue_vern_code')})",
                          "vernaculaire")
        self.cote.addItem(f"traduction ({projet.reglage('langue_analyse_nom') or projet.reglage('langue_analyse_code')})",
                          "analyse")
        self.avec_livres = QCheckBox("Versets des livres cochés (corpus)")
        self.avec_livres.setChecked(True)
        self.avec_glossaire = QCheckBox("Glossaire interlinéaire de Paratext (mots et morphèmes glosés)")
        self.avec_termes = QCheckBox("Rendus validés des termes bibliques")
        form.addRow("Ce projet est en :", self.cote)
        form.addRow(self.avec_livres)
        form.addRow(self.avec_glossaire)
        form.addRow(self.avec_termes)
        self.note_cote = QLabel("")
        self.note_cote.setObjectName("sousTitre")
        self.note_cote.setWordWrap(True)
        form.addRow(self.note_cote)
        v.addLayout(form)
        self.cote.currentIndexChanged.connect(self._maj_options)

        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        boutons.button(QDialogButtonBox.Ok).setText("Importer")
        boutons.accepted.connect(self._accepter)
        boutons.rejected.connect(self.reject)
        v.addWidget(boutons)
        self._charger_projets()

    def _charger_projets(self):
        self.aide.setText(f"Projets Paratext trouvés dans <b>{self.dossier}</b>. Ils sont seulement lus, jamais "
                          "modifiés. Pour un corpus parallèle, importe un projet dans la langue documentée puis un "
                          "projet dans la langue d'analyse : les versets se rejoignent par leur référence.")
        self.projets.clear()
        code_vern = self.projet.reglage("langue_vern_code")
        code_analyse = self.projet.reglage("langue_analyse_code")
        meilleur = None
        for p in paratext.lister_projets(self.dossier):
            marque = " ★" if p.code in (code_vern, code_analyse) and p.code else ""
            item = QListWidgetItem(f"{p.nom} — {p.nom_complet or p.langue} [{p.code}], {len(p.livres)} livre(s){marque}")
            item.setData(Qt.UserRole, p)
            self.projets.addItem(item)
            if meilleur is None and p.code == code_vern:
                meilleur = item
        if meilleur:
            self.projets.setCurrentItem(meilleur)
        elif self.projets.count():
            self.projets.setCurrentRow(0)

    def _autre_dossier(self):
        dossier = QFileDialog.getExistingDirectory(self, "Dossier des projets Paratext", self.dossier)
        if dossier:
            self.dossier = dossier
            self._charger_projets()

    def _projet_choisi(self, item, _ancien=None):
        self.livres.clear()
        if not item:
            return
        p = item.data(Qt.UserRole)
        self.projet_pt = p
        for code in p.livres:
            li = QListWidgetItem(f"{code}  {textes.NOMS_LIVRES.get(code, '')}")
            li.setData(Qt.UserRole, code)
            li.setFlags(li.flags() | Qt.ItemIsUserCheckable)
            li.setCheckState(Qt.Checked)
            self.livres.addItem(li)
        self.titre_livres.setText(f"<b>Livres de {p.nom}</b> ({len(p.livres)})")
        # côté proposé d'après le code de langue
        if p.code and p.code == self.projet.reglage("langue_analyse_code"):
            self.cote.setCurrentIndex(1)
        else:
            self.cote.setCurrentIndex(0)
        self._maj_options()

    def _maj_options(self):
        vernaculaire = self.cote.currentData() == "vernaculaire"
        # glossaire et termes décrivent la langue documentée : seulement pour un projet dans cette langue
        for case in (self.avec_glossaire, self.avec_termes):
            case.setEnabled(vernaculaire)
            case.setChecked(vernaculaire)
        p = self.projet_pt
        if p and p.code and p.code not in (self.projet.reglage("langue_vern_code"),
                                           self.projet.reglage("langue_analyse_code")):
            self.note_cote.setText(f"Attention : ce projet est en « {p.code} », ni la langue documentée ni la langue "
                                   "d'analyse de ce projet.")
        else:
            self.note_cote.setText("")

    def _cocher(self, etat):
        for i in range(self.livres.count()):
            self.livres.item(i).setCheckState(etat)

    def livres_coches(self):
        return [self.livres.item(i).data(Qt.UserRole) for i in range(self.livres.count())
                if self.livres.item(i).checkState() == Qt.Checked]

    def _accepter(self):
        if not self.projet_pt:
            return
        if self.avec_livres.isChecked() and not self.livres_coches() and not (
                self.avec_glossaire.isChecked() or self.avec_termes.isChecked()):
            erreur(self, "Paratext", "Coche au moins un livre ou un contenu à importer.")
            return
        self.accept()


def importer_paratext(parent, projet):
    """Ouvre le dialogue puis importe. Retourne True si quelque chose a été importé."""
    d = DialogueParatext(projet, parent)
    if not d.exec():
        return False
    try:
        projet.sauvegarde_automatique()
        rapport = paratext.Rapport()
        with CurseurAttente():
            if d.avec_livres.isChecked() and d.livres_coches():
                paratext.importer_livres(projet, d.projet_pt, d.livres_coches(), d.cote.currentData(), rapport)
            if d.avec_glossaire.isEnabled() and d.avec_glossaire.isChecked():
                paratext.importer_glossaire(projet, d.projet_pt, rapport)
            if d.avec_termes.isEnabled() and d.avec_termes.isChecked():
                paratext.importer_termes(projet, d.projet_pt, rapport)
            alignement.recalculer(projet)
    except Exception as e:
        erreur(parent, "Import Paratext", "L'import n'a pas abouti. Le projet a été sauvegardé juste avant "
                                          "(menu Fichier > Ouvrir le dossier des sauvegardes).", e)
        return False
    paires = projet.conn.execute("SELECT COUNT(*) FROM phrases WHERE vernaculaire IS NOT NULL "
                                 "AND analyse IS NOT NULL").fetchone()[0]
    info(parent, "Import Paratext", rapport.resume() + f"\n\nLe corpus compte maintenant {paires} phrase(s) "
                                                       "dans les deux langues.")
    return True

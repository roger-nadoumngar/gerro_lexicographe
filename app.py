"""
Lexicographe Ngambay — logiciel de bureau
==========================================
Outil de lexicographie assistée par IA pour le ngambay, avec le français
comme langue pivot. Combine collecte, alignement statistique automatique,
validation humaine et apprentissage actif par concordance.

Ce script est un vrai logiciel Python (fenêtre native, pas une page web).
Pour en faire un .exe Windows autonome, voir INSTRUCTIONS_EXE.txt fourni
avec ce fichier.
"""

import json
import os
import re
import sqlite3
import sys
import csv
import unicodedata
import uuid
from collections import defaultdict
from datetime import datetime

import shutil
import xml.etree.ElementTree as ET

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

try:
    from docx import Document as DocxDocument
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    from pypdf import PdfReader
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

try:
    from pylexique import Lexique383
    HAS_LEXIQUE_FR = True
except ImportError:
    HAS_LEXIQUE_FR = False

# ---------------------------------------------------------------------------
# Chemins
# ---------------------------------------------------------------------------

APP_NAME = "LexicographeNgambay"


def resource_path(name):
    """Trouve une ressource en développement, --onefile et --onedir."""
    candidates = []
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        candidates.append(os.path.join(bundle_dir, name))
    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(os.path.dirname(sys.executable), name))
    else:
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), name))
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    searched = "\n".join(f"  - {path}" for path in candidates)
    raise FileNotFoundError(f"Ressource nécessaire introuvable : {name}\nChemins vérifiés :\n{searched}")


def user_data_dir():
    """Dossier persistant et accessible pour les données de l'utilisateur."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, APP_NAME)


def database_path():
    """Crée l'emplacement utilisateur et migre par copie l'ancienne base locale."""
    data_dir = user_data_dir()
    os.makedirs(data_dir, exist_ok=True)
    target = os.path.join(data_dir, "lexique_ngambay.db")
    legacy = os.path.join(
        os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)),
        "lexique_ngambay.db",
    )
    if not os.path.exists(target) and os.path.isfile(legacy):
        shutil.copy2(legacy, target)
    return target


DB_PATH = None

FR_STOPWORDS = set("""le la les un une des de du et à en il elle ils elles je tu nous vous
que qui ce cet cette ces son sa ses leur leurs mais ou dans sur pour avec par comme au aux
se lui même était fut être avoir a ont étaient point pas ne s on y d l qu n j t c""".split())

CATEGORIES = ["nom", "verbe", "adjectif", "pronom", "particule", "nom propre", "adverbe", "autre"]

DOMAINES_SEMANTIQUES = [
    "personne", "famille / relations", "corps humain", "animal", "plante",
    "nourriture", "objet / outil", "vêtement", "habitation / lieu",
    "nature / environnement", "temps", "quantité / nombre", "action / mouvement",
    "sentiment / état", "religion / spirituel", "couleur", "autre",
]

TYPES_RELATIONS = [
    "synonyme", "antonyme", "terme générique (hyperonyme)", "terme spécifique (hyponyme)",
    "partie de (méronyme)", "même champ lexical",
]


# ---------------------------------------------------------------------------
# Couche base de données (SQLite — vraie persistance locale, pas de navigateur)
# ---------------------------------------------------------------------------

class Database:
    def __init__(self, path):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def _create_schema(self):
        c = self.conn.cursor()
        c.executescript("""
        CREATE TABLE IF NOT EXISTS verses (
            ref TEXT PRIMARY KEY,
            ngambay TEXT,
            francais TEXT,
            source TEXT DEFAULT 'corpus'
        );

        CREATE TABLE IF NOT EXISTS words (
            mot_ngambay TEXT PRIMARY KEY,
            frequence INTEGER DEFAULT 0,
            candidat_francais TEXT,
            score_confiance REAL DEFAULT 0,
            co_occurrences INTEGER DEFAULT 0,
            autres_candidats TEXT DEFAULT '[]',
            statut TEXT DEFAULT 'en_attente',   -- en_attente / valide / rejete
            traduction_validee TEXT,
            categorie TEXT,
            genre TEXT,
            nombre TEXT,
            domaine_semantique TEXT,
            exemple_phrase TEXT,
            definition TEXT,
            notes TEXT,
            date_validation TEXT
        );

        CREATE TABLE IF NOT EXISTS audio_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom_fichier TEXT,
            chemin_local TEXT,
            note TEXT,
            date_ajout TEXT
        );

        CREATE TABLE IF NOT EXISTS relations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mot_source TEXT,
            mot_cible TEXT,
            type_relation TEXT,
            date TEXT
        );

        CREATE TABLE IF NOT EXISTS contradictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mot_ngambay TEXT,
            ancienne_traduction TEXT,
            nouvelle_traduction TEXT,
            ref_verset TEXT,
            date TEXT,
            resolu INTEGER DEFAULT 0
        );
        """)
        self.conn.commit()
        self._migrate_add_columns()

    def _migrate_add_columns(self):
        """Ajoute les colonnes genre/nombre si la base existait déjà avant cette version."""
        c = self.conn.cursor()
        existing = {row[1] for row in c.execute("PRAGMA table_info(words)").fetchall()}
        if "genre" not in existing:
            c.execute("ALTER TABLE words ADD COLUMN genre TEXT")
        if "nombre" not in existing:
            c.execute("ALTER TABLE words ADD COLUMN nombre TEXT")
        if "domaine_semantique" not in existing:
            c.execute("ALTER TABLE words ADD COLUMN domaine_semantique TEXT")
        if "exemple_phrase" not in existing:
            c.execute("ALTER TABLE words ADD COLUMN exemple_phrase TEXT")
        if "definition" not in existing:
            c.execute("ALTER TABLE words ADD COLUMN definition TEXT")
        if "notes" not in existing:
            c.execute("ALTER TABLE words ADD COLUMN notes TEXT")
        self.conn.commit()
        self._migrate_normalize_words()

    def _migrate_normalize_words(self):
        """Ramène les mots enregistrés avant la normalisation Unicode à la forme NFC."""
        c = self.conn.cursor()
        for (mot, statut) in c.execute("SELECT mot_ngambay, statut FROM words").fetchall():
            nfc = normalize_text(mot)
            if nfc == mot:
                continue
            taken = c.execute("SELECT statut FROM words WHERE mot_ngambay=?", (nfc,)).fetchone()
            if statut == "en_attente":
                # le moteur régénère les hypothèses à partir du corpus
                c.execute("DELETE FROM words WHERE mot_ngambay=?", (mot,))
            elif taken is None or taken[0] == "en_attente":
                c.execute("DELETE FROM words WHERE mot_ngambay=?", (nfc,))
                c.execute("UPDATE words SET mot_ngambay=? WHERE mot_ngambay=?", (nfc, mot))
            else:
                continue  # deux fiches validées : on laisse l'humain trancher
            c.execute("UPDATE relations SET mot_source=? WHERE mot_source=?", (nfc, mot))
            c.execute("UPDATE relations SET mot_cible=? WHERE mot_cible=?", (nfc, mot))
        self.conn.commit()

    def close(self):
        self.conn.close()


# ---------------------------------------------------------------------------
# Moteur de concordance / alignement (le "cerveau" statistique)
# ---------------------------------------------------------------------------

def normalize_text(s):
    """Forme Unicode unique (NFC) : le corpus mélange lettres accentuées
    précomposées (á) et décomposées (a + accent combinant)."""
    return unicodedata.normalize("NFC", s)


def tokenize(s):
    s = normalize_text(s).lower()
    s = re.sub(r"[’'\",.;:!?()«»…\[\]“”—–]", " ", s)
    return [w for w in s.split() if w]


class ConcordanceEngine:
    """
    Calcule, à partir de toutes les paires de phrases (ngambay, français)
    connues, une hypothèse de traduction pour chaque mot ngambay — et
    détecte les contradictions quand une nouvelle phrase remet en cause
    une traduction déjà validée.
    """

    def __init__(self, db: Database):
        self.db = db

    def recompute_all(self, progress_callback=None):
        c = self.db.conn.cursor()
        rows = c.execute("SELECT ref, ngambay, francais FROM verses").fetchall()

        cooc = defaultdict(lambda: defaultdict(int))
        ngb_freq = defaultdict(int)
        fr_freq = defaultdict(int)

        for ref, ngb_text, fr_text in rows:
            if not ngb_text or not fr_text:
                continue  # verset importé d'un seul côté, en attente de son pendant
            ngb_words = set(tokenize(ngb_text))
            fr_words = set(tokenize(fr_text)) - FR_STOPWORDS
            for nw in ngb_words:
                ngb_freq[nw] += 1
            for fw in fr_words:
                fr_freq[fw] += 1
            for nw in ngb_words:
                for fw in fr_words:
                    cooc[nw][fw] += 1

        def dice(nw, fw):
            cij = cooc[nw][fw]
            if cij == 0:
                return 0
            return 2 * cij / (ngb_freq[nw] + fr_freq[fw])

        # on ne touche pas aux mots déjà validés/rejetés manuellement,
        # seulement à ceux encore en attente
        validated = {r[0] for r in c.execute(
            "SELECT mot_ngambay FROM words WHERE statut != 'en_attente'").fetchall()}

        contradictions_found = []
        new_contradictions = 0
        seen = set()

        for nw, freq in ngb_freq.items():
            if freq < 1 or len(nw) < 2:
                continue
            candidates = [(fw, dice(nw, fw), cooc[nw][fw]) for fw in cooc[nw]]
            candidates = [x for x in candidates if x[2] >= 1]
            candidates.sort(key=lambda x: -x[1])
            if not candidates:
                continue
            best_fw, best_score, best_cooc = candidates[0]
            autres = json.dumps([x[0] for x in candidates[1:5]], ensure_ascii=False)

            if nw in validated:
                # vérifie la cohérence avec ce qui a déjà été validé humainement
                row = c.execute(
                    "SELECT traduction_validee, statut FROM words WHERE mot_ngambay=?",
                    (nw,)).fetchone()
                if row and row[1] == 'valide' and row[0]:
                    validated_fr = row[0].strip().lower()
                    if validated_fr != best_fw and best_score > 0.5:
                        contradictions_found.append((nw, validated_fr, best_fw))
                # on met à jour les stats mais pas le statut ni la traduction validée
                c.execute("""UPDATE words SET frequence=?, co_occurrences=?, autres_candidats=?
                             WHERE mot_ngambay=?""",
                          (freq, best_cooc, autres, nw))
            else:
                c.execute("""INSERT INTO words
                             (mot_ngambay, frequence, candidat_francais, score_confiance,
                              co_occurrences, autres_candidats, statut)
                             VALUES (?, ?, ?, ?, ?, ?, 'en_attente')
                             ON CONFLICT(mot_ngambay) DO UPDATE SET
                                frequence=excluded.frequence,
                                candidat_francais=excluded.candidat_francais,
                                score_confiance=excluded.score_confiance,
                                co_occurrences=excluded.co_occurrences,
                                autres_candidats=excluded.autres_candidats""",
                          (nw, freq, best_fw, round(best_score, 3), best_cooc, autres))
            seen.add(nw)

        # hypothèses en attente qui ne correspondent plus à aucun mot du corpus
        # (ancienne tokenisation, ancienne forme Unicode…)
        stale = [(r[0],) for r in c.execute(
            "SELECT mot_ngambay FROM words WHERE statut='en_attente'").fetchall() if r[0] not in seen]
        c.executemany("DELETE FROM words WHERE mot_ngambay=?", stale)

        for nw, old_fr, new_fr in contradictions_found:
            # déjà signalée, ou déjà tranchée par l'utilisateur : on ne la repose pas
            exists = c.execute("""SELECT 1 FROM contradictions
                                 WHERE mot_ngambay=? AND ancienne_traduction=?
                                   AND nouvelle_traduction=? LIMIT 1""",
                               (nw, old_fr, new_fr)).fetchone()
            if not exists:
                c.execute("""INSERT INTO contradictions
                             (mot_ngambay, ancienne_traduction, nouvelle_traduction, ref_verset, date)
                             VALUES (?, ?, ?, ?, ?)""",
                          (nw, old_fr, new_fr, '', datetime.now().isoformat()))
                new_contradictions += 1

        self.db.conn.commit()
        return new_contradictions


def parse_usfm_generic(path, book_code_override=None):
    """Extrait les versets d'un fichier USFM/.SFM quelconque, avec leurs
    références (LIVRE chapitre:verset). Retourne un dict {ref: texte}."""
    with open(path, encoding='utf-8', errors='replace') as f:
        text = f.read()

    book_code = book_code_override
    id_match = re.search(r'\\id\s+(\w+)', text)
    if not book_code and id_match:
        book_code = id_match.group(1)[:3].upper()
    if not book_code:
        book_code = os.path.splitext(os.path.basename(path))[0][:3].upper()

    verses = {}
    chapter = None
    lines = text.split('\n')
    buffer_verse_num = None
    buffer_text = []

    def flush():
        nonlocal buffer_verse_num, buffer_text
        if chapter is not None and buffer_verse_num is not None:
            ref = f"{book_code} {chapter}:{buffer_verse_num}"
            clean = ' '.join(buffer_text).strip()
            clean = re.sub(r'\\x .*?\\x\*', '', clean)
            clean = re.sub(r'\\f .*?\\f\*', '', clean)
            clean = re.sub(r'\\fig .*?\\fig\*', '', clean)
            clean = re.sub(r'\|[^\\]*?(?=\\[a-z]+\*)', '', clean)  # attributs \w mot|lemma="…"\w*
            clean = re.sub(r'\\[a-z]+[0-9]?\*?', '', clean)
            clean = normalize_text(clean)
            clean = re.sub(r'\s+', ' ', clean).strip()
            if clean:
                verses[ref] = clean
        buffer_verse_num = None
        buffer_text = []

    for line in lines:
        line = line.strip()
        m_c = re.match(r'\\c\s+(\d+)', line)
        m_v = re.match(r'\\v\s+(\d+)\s*(.*)', line)
        if m_c:
            flush()
            chapter = int(m_c.group(1))
            continue
        if m_v:
            flush()
            buffer_verse_num = int(m_v.group(1))
            buffer_text = [m_v.group(2)]
            continue
        if line.startswith('\\'):
            parts = line.split(' ', 1)
            if len(parts) > 1 and buffer_verse_num is not None:
                buffer_text.append(parts[1])
            continue
        else:
            if buffer_verse_num is not None and line:
                buffer_text.append(line)
    flush()
    return verses, book_code


def find_example_verse(db: Database, mot_ngambay):
    """Cherche dans le corpus un verset où ce mot apparaît, pour servir
    d'exemple de phrase automatique (comme 'Exemple de référence' dans FLEx)."""
    c = db.conn.cursor()
    rows = c.execute("SELECT ref, ngambay, francais FROM verses WHERE ngambay IS NOT NULL AND francais IS NOT NULL").fetchall()
    for ref, ngb_text, fr_text in rows:
        if mot_ngambay.lower() in tokenize(ngb_text):
            return ref, ngb_text, fr_text
    return None


# ---------------------------------------------------------------------------
# Suggestion grammaticale automatique via le dictionnaire français (Lexique383)
# ---------------------------------------------------------------------------

CGRAM_LABELS = {
    "NOM": "nom", "VER": "verbe", "ADJ": "adjectif", "ADV": "adverbe",
    "PRO": "pronom", "PRE": "particule", "CON": "particule", "ART": "particule",
    "AUX": "verbe", "INT": "autre", "ONO": "autre", "LIA": "autre",
}
GENRE_LABELS = {"m": "masculin", "f": "féminin"}
NOMBRE_LABELS = {"s": "singulier", "p": "pluriel"}

_lexique_fr_instance = None


def get_lexique_fr():
    """Charge Lexique383 une seule fois (lazy loading, prend 1-2 secondes)."""
    global _lexique_fr_instance
    if not HAS_LEXIQUE_FR:
        return None
    if _lexique_fr_instance is None:
        _lexique_fr_instance = Lexique383()
    return _lexique_fr_instance


def suggest_grammar_fr(mot_francais):
    """
    Cherche un mot français dans Lexique383 et retourne la meilleure hypothèse
    grammaticale (catégorie, genre, nombre). S'il y a plusieurs possibilités
    homographes (ex: 'manger' nom ou verbe), on choisit celle qui a la
    fréquence d'usage la plus élevée en français réel.
    Retourne None si le mot est introuvable ou si la bibliothèque est absente.
    """
    lex = get_lexique_fr()
    if lex is None or not mot_francais:
        return None
    mot = mot_francais.strip().lower().split()[0] if mot_francais.strip() else ""
    if not mot:
        return None
    try:
        res = lex.get_lex(mot)
    except (KeyError, Exception):
        return None
    if mot not in res:
        return None
    entry = res[mot]
    candidates = entry if isinstance(entry, list) else [entry]
    if not candidates:
        return None
    # on choisit l'entrée la plus fréquente en usage réel (corpus de films)
    best = max(candidates, key=lambda it: (it.freqlemfilms2 or 0))
    return {
        "categorie": CGRAM_LABELS.get(best.cgram, "autre"),
        "genre": GENRE_LABELS.get(best.genre, ""),
        "nombre": NOMBRE_LABELS.get(best.nombre, ""),
        "source": "Lexique383",
    }


# ---------------------------------------------------------------------------
# Export LIFT (Lexicon Interchange FormaT, SIL) — importable dans FLEx et WeSay
# ---------------------------------------------------------------------------

LANG_NGAMBAY = "sba"   # code ISO 639-3 du ngambay
LANG_FRANCAIS = "fr"

LIFT_POS = {
    "nom": "Noun", "verbe": "Verb", "adjectif": "Adjective", "pronom": "Pronoun",
    "particule": "Particle", "nom propre": "Proper Noun", "adverbe": "Adverb",
}


def lift_entry_id(mot):
    """Identifiant stable d'une entrée : réexporter ne crée pas de doublons dans FLEx."""
    return f"{mot}_{uuid.uuid5(uuid.NAMESPACE_URL, 'ngambay:' + mot)}"


def _lift_form(parent, tag, lang, text):
    el = ET.SubElement(parent, tag) if tag else parent
    form = ET.SubElement(el, "form", lang=lang)
    ET.SubElement(form, "text").text = text
    return el


def build_lift(rows, relations):
    """rows : sortie de _get_validated ; relations : [(source, cible, type)].
    Retourne l'arbre XML LIFT 0.13."""
    root = ET.Element("lift", version="0.13", producer=APP_NAME)
    exported = {r[0] for r in rows}
    rels_by_source = defaultdict(list)
    for source, cible, typ in relations:
        if cible in exported:  # une relation vers un mot non validé n'aurait pas de cible
            rels_by_source[source].append((cible, typ))

    for mot, trad, cat, genre, nombre, domaine, exemple, definition, notes, date_val in rows:
        attrs = {"id": lift_entry_id(mot), "guid": lift_entry_id(mot).rsplit("_", 1)[1]}
        if date_val:
            attrs["dateModified"] = date_val.split(".")[0] + "Z"
        entry = ET.SubElement(root, "entry", attrs)
        _lift_form(entry, "lexical-unit", LANG_NGAMBAY, mot)

        sense = ET.SubElement(entry, "sense", id=f"{lift_entry_id(mot)}_s1")
        if cat:
            ET.SubElement(sense, "grammatical-info", value=LIFT_POS.get(cat, cat))
        if trad:
            gloss = ET.SubElement(sense, "gloss", lang=LANG_FRANCAIS)
            ET.SubElement(gloss, "text").text = trad
        if definition:
            _lift_form(sense, "definition", LANG_FRANCAIS, definition)
        if exemple:
            # l'exemple automatique est enregistré sous la forme « ngambay\n→ français »
            ngb, _, fr = exemple.partition("\n→ ")
            ex = _lift_form(sense, "example", LANG_NGAMBAY, ngb.strip())
            if fr.strip():
                _lift_form(ex, "translation", LANG_FRANCAIS, fr.strip())
        for name, value in (("domaine-semantique", domaine), ("genre", genre), ("nombre", nombre)):
            if value:
                ET.SubElement(sense, "trait", name=name, value=value)

        if notes:
            _lift_form(entry, "note", LANG_FRANCAIS, notes)
        for cible, typ in rels_by_source.get(mot, []):
            ET.SubElement(entry, "relation", type=typ, ref=lift_entry_id(cible))

    ET.indent(root)
    return ET.ElementTree(root)


# ---------------------------------------------------------------------------
# Initialisation des données au premier lancement
# ---------------------------------------------------------------------------

def bootstrap_data(db: Database):
    """Charge les références communes du corpus intégré. Exécuté à chaque
    démarrage : une base existante reçoit les versets ajoutés ou corrigés
    depuis, sans toucher aux versets importés ou saisis par l'utilisateur."""
    c = db.conn.cursor()
    ngb_path = resource_path("ngambay_verses.json")
    fr_path = resource_path("french_verses.json")

    with open(ngb_path, encoding="utf-8") as f:
        ngb = json.load(f)
    with open(fr_path, encoding="utf-8") as f:
        fr = json.load(f)

    for ref, text in ngb.items():
        if ref in fr:
            c.execute("""INSERT INTO verses (ref, ngambay, francais, source) VALUES (?,?,?,?)
                         ON CONFLICT(ref) DO UPDATE SET
                            ngambay=CASE WHEN verses.source='corpus_initial' THEN excluded.ngambay
                                         ELSE COALESCE(verses.ngambay, excluded.ngambay) END,
                            francais=CASE WHEN verses.source='corpus_initial' THEN excluded.francais
                                          ELSE COALESCE(verses.francais, excluded.francais) END""",
                      (ref, text, fr[ref], "corpus_initial"))
    db.conn.commit()


# ---------------------------------------------------------------------------
# Interface graphique
# ---------------------------------------------------------------------------

class LexicographeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Lexicographe Ngambay — assisté par IA")
        self.root.geometry("980x680")
        self.root.minsize(820, 560)

        self.db = Database(DB_PATH)
        bootstrap_data(self.db)
        self.engine = ConcordanceEngine(self.db)
        self.engine.recompute_all()

        self._build_style()
        self._build_layout()
        self.refresh_dashboard()
        self.load_next_review_word()
        self.refresh_dictionary()

    # -- style -------------------------------------------------------------
    def _build_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        bg = "#ECE4D3"
        ink = "#2B2A1F"
        teal = "#1F5B57"
        self.root.configure(bg=bg)
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=ink, font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Georgia", 18, "bold"), foreground=ink)
        style.configure("Sub.TLabel", font=("Segoe UI", 9), foreground="#6B6857")
        style.configure("TButton", font=("Segoe UI", 10), padding=6)
        style.configure("Accent.TButton", background=teal, foreground="white")
        style.map("Accent.TButton", background=[("active", "#194B47")])
        style.configure("TNotebook", background=bg)
        style.configure("TNotebook.Tab", padding=(14, 8), font=("Segoe UI", 10))

    # -- layout général ------------------------------------------------------
    def _build_layout(self):
        header = ttk.Frame(self.root, padding=(20, 16, 20, 8))
        header.pack(fill="x")
        ttk.Label(header, text="Lexicographe Ngambay", style="Header.TLabel").pack(anchor="w")
        ttk.Label(header, text="Collecte · Alignement IA · Validation · Concordance active",
                  style="Sub.TLabel").pack(anchor="w")

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=10)

        self.tab_dashboard = ttk.Frame(self.notebook, padding=16)
        self.tab_import = ttk.Frame(self.notebook)       # défilable, voir _make_scrollable
        self.tab_validation = ttk.Frame(self.notebook)   # défilable, voir _make_scrollable
        self.tab_concordance = ttk.Frame(self.notebook, padding=16)
        self.tab_dictionary = ttk.Frame(self.notebook, padding=16)
        self.tab_export = ttk.Frame(self.notebook, padding=16)

        self.notebook.add(self.tab_dashboard, text="Tableau de bord")
        self.notebook.add(self.tab_import, text="Import")
        self.notebook.add(self.tab_validation, text="Validation")
        self.notebook.add(self.tab_concordance, text="Concordance active")
        self.notebook.add(self.tab_dictionary, text="Dictionnaire")
        self.notebook.add(self.tab_export, text="Export")

        self._build_dashboard_tab()
        self._build_import_tab()
        self._build_validation_tab()
        self._build_concordance_tab()
        self._build_dictionary_tab()
        self._build_export_tab()

        self.notebook.bind("<<NotebookTabChanged>>", lambda e: self.on_tab_change())

    def _make_scrollable(self, tab):
        """Rend un onglet défilable (molette ou barre) quand son contenu dépasse
        la hauteur de la fenêtre ; retourne le cadre où placer les widgets."""
        canvas = tk.Canvas(tab, bg="#ECE4D3", highlightthickness=0)
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, padding=16)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        def on_wheel(event):
            if inner.winfo_reqheight() > canvas.winfo_height():
                canvas.yview_scroll(int(-event.delta / 120), "units")
        tab.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", on_wheel))
        tab.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        return inner

    def on_tab_change(self):
        tab = self.notebook.tab(self.notebook.select(), "text")
        if tab == "Tableau de bord":
            self.refresh_dashboard()
        elif tab == "Dictionnaire":
            self.refresh_dictionary()
        elif tab == "Validation":
            self.load_next_review_word()

    # -- Onglet Tableau de bord ---------------------------------------------
    def _build_dashboard_tab(self):
        f = self.tab_dashboard
        self.stat_labels = {}
        grid = ttk.Frame(f)
        grid.pack(fill="x", pady=(0, 20))
        for i, key in enumerate(["versets", "mots_total", "valides", "rejetes", "en_attente"]):
            box = ttk.Frame(grid, relief="solid", borderwidth=1, padding=14)
            box.grid(row=0, column=i, padx=6, sticky="nsew")
            grid.columnconfigure(i, weight=1)
            lbl_val = ttk.Label(box, text="0", font=("Georgia", 22, "bold"))
            lbl_val.pack(anchor="w")
            ttk.Label(box, text=key.replace("_", " "), style="Sub.TLabel").pack(anchor="w")
            self.stat_labels[key] = lbl_val

        ttk.Label(f, text="Contradictions détectées", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(10, 4))
        self.contradiction_list = tk.Listbox(f, height=10, font=("Consolas", 10))
        self.contradiction_list.pack(fill="both", expand=True)
        self.contradiction_ids = []

        contra_row = ttk.Frame(f)
        contra_row.pack(anchor="w", pady=(6, 0))
        ttk.Button(contra_row, text="Garder la traduction validée",
                   command=lambda: self.resolve_contradiction(adopt_new=False)).pack(side="left", padx=(0, 8))
        ttk.Button(contra_row, text="Adopter la nouvelle traduction",
                   command=lambda: self.resolve_contradiction(adopt_new=True)).pack(side="left")

        ttk.Button(f, text="Recalculer le moteur de concordance", command=self.recompute_engine).pack(anchor="w", pady=10)

    def refresh_dashboard(self):
        c = self.db.conn.cursor()
        n_verses = c.execute("SELECT COUNT(*) FROM verses").fetchone()[0]
        n_total = c.execute("SELECT COUNT(*) FROM words").fetchone()[0]
        n_valid = c.execute("SELECT COUNT(*) FROM words WHERE statut='valide'").fetchone()[0]
        n_rej = c.execute("SELECT COUNT(*) FROM words WHERE statut='rejete'").fetchone()[0]
        n_pending = n_total - n_valid - n_rej

        self.stat_labels["versets"].config(text=str(n_verses))
        self.stat_labels["mots_total"].config(text=str(n_total))
        self.stat_labels["valides"].config(text=str(n_valid))
        self.stat_labels["rejetes"].config(text=str(n_rej))
        self.stat_labels["en_attente"].config(text=str(n_pending))

        self.contradiction_list.delete(0, tk.END)
        rows = c.execute("""SELECT id, mot_ngambay, ancienne_traduction, nouvelle_traduction
                             FROM contradictions WHERE resolu=0 ORDER BY date DESC""").fetchall()
        self.contradiction_ids = [r[0] for r in rows]
        if not rows:
            self.contradiction_list.insert(tk.END, "  Aucune contradiction pour l'instant.")
        for _, mot, ancien, nouveau in rows:
            self.contradiction_list.insert(
                tk.END, f"  '{mot}' : validé comme « {ancien} », mais de nouvelles phrases suggèrent « {nouveau} »")

    def resolve_contradiction(self, adopt_new):
        sel = self.contradiction_list.curselection()
        if not sel or sel[0] >= len(self.contradiction_ids):
            messagebox.showinfo("Contradictions", "Sélectionne d'abord une contradiction dans la liste.")
            return
        cid = self.contradiction_ids[sel[0]]
        c = self.db.conn.cursor()
        try:
            mot, nouveau = c.execute("SELECT mot_ngambay, nouvelle_traduction FROM contradictions WHERE id=?",
                                     (cid,)).fetchone()
            if adopt_new:
                c.execute("UPDATE words SET traduction_validee=?, date_validation=? WHERE mot_ngambay=?",
                          (nouveau, datetime.now().isoformat(), mot))
            # une décision humaine clôt toutes les alertes ouvertes de ce mot
            c.execute("UPDATE contradictions SET resolu=1 WHERE mot_ngambay=? AND resolu=0", (mot,))
            self.db.conn.commit()
        except sqlite3.Error as e:
            self.db.conn.rollback()
            messagebox.showerror("Erreur de base de données", f"Impossible de résoudre la contradiction :\n{e}")
            return
        self.refresh_dashboard()
        self.refresh_dictionary()

    def recompute_engine(self):
        try:
            n_contra = self.engine.recompute_all()
        except sqlite3.Error as e:
            messagebox.showerror("Erreur de base de données", f"Impossible d'enregistrer le recalcul :\n{e}")
            return
        self.refresh_dashboard()
        self.load_next_review_word()
        msg = "Moteur recalculé."
        if n_contra:
            msg += f" {n_contra} nouvelle(s) contradiction(s) détectée(s) — voir le tableau de bord."
        messagebox.showinfo("Concordance", msg)

    # -- Onglet Import ---------------------------------------------------------
    def _build_import_tab(self):
        f = self._make_scrollable(self.tab_import)

        ttk.Label(f, text="Importer des fichiers dans le projet", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(f, text="USFM : ajouté directement au corpus exploité par le moteur. "
                          "Word/PDF : texte extrait pour lecture et copie manuelle. "
                          "Audio : conservé comme référence (transcription automatique = phase future).",
                  style="Sub.TLabel", wraplength=760, justify="left").pack(anchor="w", pady=(2, 16))

        # --- Bloc USFM ---
        usfm_box = ttk.Frame(f, relief="solid", borderwidth=1, padding=12)
        usfm_box.pack(fill="x", pady=(0, 10))
        ttk.Label(usfm_box, text="Fichier USFM / .SFM", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        row = ttk.Frame(usfm_box)
        row.pack(anchor="w", pady=(6, 0))
        ttk.Label(row, text="Langue du fichier :").pack(side="left")
        self.usfm_lang_combo = ttk.Combobox(row, values=["ngambay", "français"], state="readonly", width=12)
        self.usfm_lang_combo.set("ngambay")
        self.usfm_lang_combo.pack(side="left", padx=8)
        ttk.Button(usfm_box, text="Choisir un fichier USFM...", command=self.import_usfm).pack(anchor="w", pady=(8, 0))

        # --- Bloc Word ---
        docx_box = ttk.Frame(f, relief="solid", borderwidth=1, padding=12)
        docx_box.pack(fill="x", pady=(0, 10))
        ttk.Label(docx_box, text="Document Word (.docx)", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        state_txt = "" if HAS_DOCX else "  (bibliothèque manquante — voir message si tu cliques)"
        ttk.Button(docx_box, text="Choisir un fichier .docx..." + state_txt,
                   command=self.import_docx).pack(anchor="w", pady=(8, 0))

        # --- Bloc PDF ---
        pdf_box = ttk.Frame(f, relief="solid", borderwidth=1, padding=12)
        pdf_box.pack(fill="x", pady=(0, 10))
        ttk.Label(pdf_box, text="Document PDF (.pdf)", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Button(pdf_box, text="Choisir un fichier .pdf...", command=self.import_pdf).pack(anchor="w", pady=(8, 0))

        # --- Bloc Audio ---
        audio_box = ttk.Frame(f, relief="solid", borderwidth=1, padding=12)
        audio_box.pack(fill="x", pady=(0, 10))
        ttk.Label(audio_box, text="Fichier audio (.mp3, .wav, .m4a)", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(audio_box, text="Conservé pour la phase de reconnaissance vocale à venir — pas de transcription pour l'instant.",
                  style="Sub.TLabel").pack(anchor="w")
        ttk.Button(audio_box, text="Choisir un fichier audio...", command=self.import_audio).pack(anchor="w", pady=(8, 0))

        ttk.Label(f, text="Aperçu / journal d'import :", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 4))
        self.import_log = tk.Text(f, height=10, font=("Consolas", 9), bg="#F4EEE1")
        self.import_log.pack(fill="both", expand=True)

    def _log_import(self, msg):
        self.import_log.insert(tk.END, msg + "\n")
        self.import_log.see(tk.END)

    def import_usfm(self):
        path = filedialog.askopenfilename(filetypes=[("USFM / SFM", "*.usfm *.SFM *.sfm *.txt"), ("Tous les fichiers", "*.*")])
        if not path:
            return
        try:
            verses, book_code = parse_usfm_generic(path)
        except Exception as e:
            messagebox.showerror("Erreur d'import", f"Impossible de lire ce fichier :\n{e}")
            return

        lang = self.usfm_lang_combo.get()
        col = "ngambay" if lang == "ngambay" else "francais"
        c = self.db.conn.cursor()
        n_new, n_updated = 0, 0
        try:
            for ref, txt in verses.items():
                existing = c.execute("SELECT ref FROM verses WHERE ref=?", (ref,)).fetchone()
                if existing:
                    # la nouvelle source empêche le corpus intégré de réécrire ce verset au démarrage
                    c.execute(f"UPDATE verses SET {col}=?, source=? WHERE ref=?",
                              (txt, os.path.basename(path), ref))
                    n_updated += 1
                else:
                    c.execute(f"INSERT INTO verses (ref, {col}, source) VALUES (?, ?, ?)",
                              (ref, txt, os.path.basename(path)))
                    n_new += 1
            self.db.conn.commit()
        except sqlite3.Error as e:
            self.db.conn.rollback()
            messagebox.showerror("Erreur d'import", f"Impossible d'enregistrer les versets :\n{e}")
            return

        self._log_import(f"[USFM] {os.path.basename(path)} — livre détecté : {book_code} — "
                          f"{len(verses)} versets ({n_new} nouveaux, {n_updated} complétés) — langue : {lang}")

        n_contra = self.engine.recompute_all()
        self.refresh_dashboard()
        self.load_next_review_word()
        msg = f"{len(verses)} versets importés depuis {os.path.basename(path)}."
        if n_contra:
            msg += f" {n_contra} contradiction(s) détectée(s)."
        messagebox.showinfo("Import USFM", msg)

    def import_docx(self):
        if not HAS_DOCX:
            messagebox.showerror(
                "Bibliothèque manquante",
                "Pour importer des fichiers Word, installe d'abord la bibliothèque nécessaire.\n\n"
                "Dans le terminal VSCode, tape :\n\npip install python-docx\n\n"
                "Puis relance le logiciel.")
            return
        path = filedialog.askopenfilename(filetypes=[("Word", "*.docx")])
        if not path:
            return
        try:
            doc = DocxDocument(path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        except Exception as e:
            messagebox.showerror("Erreur d'import", f"Impossible de lire ce fichier :\n{e}")
            return

        self._log_import(f"[WORD] {os.path.basename(path)} — {len(paragraphs)} paragraphes extraits :\n")
        for p in paragraphs:
            self._log_import("   " + p)
        self._log_import("--- fin du document ---\n")
        messagebox.showinfo("Import Word", f"{len(paragraphs)} paragraphes extraits et affichés dans le journal ci-dessous. "
                                            "Copie les phrases utiles vers l'onglet Concordance active.")

    def import_pdf(self):
        if not HAS_PDF:
            messagebox.showerror(
                "Bibliothèque manquante",
                "Pour importer des fichiers PDF, installe d'abord la bibliothèque nécessaire.\n\n"
                "Dans le terminal VSCode, tape :\n\npip install pypdf\n\n"
                "Puis relance le logiciel.")
            return
        path = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if not path:
            return
        try:
            reader = PdfReader(path)
            full_text = []
            for page in reader.pages:
                full_text.append(page.extract_text() or "")
        except Exception as e:
            messagebox.showerror("Erreur d'import", f"Impossible de lire ce fichier :\n{e}")
            return

        text = "\n".join(full_text)
        self._log_import(f"[PDF] {os.path.basename(path)} — {len(reader.pages)} pages extraites :\n")
        self._log_import(text[:5000] + ("\n... (tronqué, fichier long)" if len(text) > 5000 else ""))
        self._log_import("--- fin du document ---\n")
        messagebox.showinfo("Import PDF", f"{len(reader.pages)} pages extraites et affichées dans le journal ci-dessous.")

    def import_audio(self):
        path = filedialog.askopenfilename(filetypes=[("Audio", "*.mp3 *.wav *.m4a *.ogg"), ("Tous les fichiers", "*.*")])
        if not path:
            return
        audio_dir = os.path.join(user_data_dir(), "audio")
        base_name = os.path.basename(path)
        stem, extension = os.path.splitext(base_name)
        dest = os.path.join(audio_dir, base_name)
        suffix = 2
        while os.path.exists(dest):
            dest = os.path.join(audio_dir, f"{stem} ({suffix}){extension}")
            suffix += 1
        created = False
        try:
            os.makedirs(audio_dir, exist_ok=True)
            # Mode exclusif protège aussi contre une collision entre deux imports simultanés.
            with open(path, "rb") as source, open(dest, "xb") as target:
                created = True
                shutil.copyfileobj(source, target)
            shutil.copystat(path, dest)
            note = simpledialog.askstring("Note (optionnel)", "Ajouter une note sur ce fichier audio (ex : locuteur, contexte) :")
            c = self.db.conn.cursor()
            c.execute("INSERT INTO audio_files (nom_fichier, chemin_local, note, date_ajout) VALUES (?,?,?,?)",
                      (os.path.basename(dest), dest, note or "", datetime.now().isoformat()))
            self.db.conn.commit()
        except Exception as e:
            if created and os.path.exists(dest):
                try:
                    os.remove(dest)
                except OSError:
                    pass
            messagebox.showerror("Erreur d'import", f"Impossible d'enregistrer ce fichier audio :\n{e}")
            return

        self._log_import(f"[AUDIO] {os.path.basename(dest)} copié dans /audio — note : {note or '(aucune)'}")
        messagebox.showinfo("Import audio", "Fichier audio enregistré. La transcription automatique arrivera en Phase 5.")

    # -- Onglet Validation ---------------------------------------------------
    def _build_validation_tab(self):
        f = self._make_scrollable(self.tab_validation)
        self.review_word_var = tk.StringVar(value="—")
        self.review_meta_var = tk.StringVar(value="")

        ttk.Label(f, textvariable=self.review_word_var, font=("Georgia", 26, "bold")).pack(anchor="w")
        ttk.Label(f, textvariable=self.review_meta_var, style="Sub.TLabel").pack(anchor="w", pady=(2, 16))

        ttk.Label(f, text="Traduction française proposée (modifiable) :").pack(anchor="w")
        self.review_fr_entry = ttk.Entry(f, font=("Segoe UI", 13), width=40)
        self.review_fr_entry.pack(anchor="w", pady=(4, 12))

        self.chip_frame = ttk.Frame(f)
        self.chip_frame.pack(anchor="w", pady=(0, 12))

        ttk.Label(f, text="Catégorie grammaticale :").pack(anchor="w")
        self.review_cat_combo = ttk.Combobox(f, values=[""] + CATEGORIES, state="readonly", width=20)
        self.review_cat_combo.pack(anchor="w", pady=(4, 10))

        genre_nombre_row = ttk.Frame(f)
        genre_nombre_row.pack(anchor="w", pady=(0, 4))
        ttk.Label(genre_nombre_row, text="Genre :").grid(row=0, column=0, sticky="w")
        self.review_genre_combo = ttk.Combobox(genre_nombre_row, values=["", "masculin", "féminin"],
                                                state="readonly", width=14)
        self.review_genre_combo.grid(row=0, column=1, padx=(6, 20))
        ttk.Label(genre_nombre_row, text="Nombre :").grid(row=0, column=2, sticky="w")
        self.review_nombre_combo = ttk.Combobox(genre_nombre_row, values=["", "singulier", "pluriel", "invariable"],
                                                 state="readonly", width=14)
        self.review_nombre_combo.grid(row=0, column=3, padx=(6, 0))

        self.suggestion_note = ttk.Label(f, text="", style="Sub.TLabel")
        self.suggestion_note.pack(anchor="w", pady=(6, 16))

        ttk.Label(f, text="Domaine sémantique (choisis un bouton ou écris le tien) :").pack(anchor="w")
        self.review_domaine_entry = ttk.Combobox(f, values=DOMAINES_SEMANTIQUES, width=30)
        self.review_domaine_entry.pack(anchor="w", pady=(4, 6))
        self.domaine_chip_frame = ttk.Frame(f)
        self.domaine_chip_frame.pack(anchor="w", pady=(0, 16))
        for i, dom in enumerate(DOMAINES_SEMANTIQUES):
            b = ttk.Button(self.domaine_chip_frame, text=dom,
                           command=lambda d=dom: self._set_review_domaine(d))
            b.grid(row=i // 4, column=i % 4, padx=2, pady=2, sticky="w")

        ttk.Label(f, text="Exemple de phrase (trouvé automatiquement dans le corpus, modifiable) :").pack(anchor="w")
        self.review_exemple_text = tk.Text(f, height=3, width=70, font=("Segoe UI", 9), wrap="word")
        self.review_exemple_text.pack(anchor="w", pady=(4, 10))

        ttk.Label(f, text="Définition (résumé en français) :").pack(anchor="w")
        self.review_definition_entry = ttk.Entry(f, width=70)
        self.review_definition_entry.pack(anchor="w", pady=(4, 10))

        ttk.Label(f, text="Notes (étymologie, remarques diverses...) :").pack(anchor="w")
        self.review_notes_text = tk.Text(f, height=2, width=70, font=("Segoe UI", 9), wrap="word")
        self.review_notes_text.pack(anchor="w", pady=(4, 16))

        btn_row = ttk.Frame(f)
        btn_row.pack(anchor="w")
        ttk.Button(btn_row, text="✓ Valider", style="Accent.TButton",
                   command=self.validate_current_word).pack(side="left", padx=(0, 8))
        ttk.Button(btn_row, text="✗ Rejeter", command=self.reject_current_word).pack(side="left", padx=(0, 8))
        ttk.Button(btn_row, text="Passer →", command=self.skip_current_word).pack(side="left", padx=(0, 8))
        ttk.Button(btn_row, text="🔍 Re-suggérer (dictionnaire FR)",
                   command=self.run_grammar_suggestion).pack(side="left")

        self.review_queue = []
        self.skipped_words = set()
        self.current_review_word = None

    def _refresh_review_queue(self):
        c = self.db.conn.cursor()
        rows = c.execute("""SELECT mot_ngambay, frequence, candidat_francais, score_confiance,
                                    co_occurrences, autres_candidats
                             FROM words WHERE statut='en_attente'
                             ORDER BY score_confiance DESC, frequence DESC""").fetchall()
        queue = [r for r in rows if r[0] not in self.skipped_words]
        if not queue and rows:
            # tous les mots restants ont été passés : on recommence le tour
            self.skipped_words.clear()
            queue = rows
        self.review_queue = queue

    def skip_current_word(self):
        if self.current_review_word:
            self.skipped_words.add(self.current_review_word)
        self.load_next_review_word()

    def _clear_review_fields(self):
        self.review_fr_entry.delete(0, tk.END)
        self.review_cat_combo.set("")
        self.review_genre_combo.set("")
        self.review_nombre_combo.set("")
        self.review_domaine_entry.set("")
        self.review_definition_entry.delete(0, tk.END)
        self.review_notes_text.delete("1.0", tk.END)
        self.review_exemple_text.delete("1.0", tk.END)
        self.suggestion_note.config(text="")

    def load_next_review_word(self):
        self._refresh_review_queue()
        for widget in self.chip_frame.winfo_children():
            widget.destroy()

        if not self.review_queue:
            # sans mot courant, Valider/Rejeter ne peuvent plus réécrire le dernier mot traité
            self.current_review_word = None
            self.review_word_var.set("File terminée")
            self.review_meta_var.set("Tous les mots proposés ont été passés en revue.")
            self._clear_review_fields()
            return

        mot, freq, candidat, score, cooc, autres_json = self.review_queue[0]
        self.current_review_word = mot
        self.review_word_var.set(mot)
        self.review_meta_var.set(f"apparaît {freq}× · {cooc} co-occurrences · confiance {int(score*100)}%")
        self._clear_review_fields()
        self.review_fr_entry.insert(0, candidat or "")

        exemple = find_example_verse(self.db, mot)
        if exemple:
            ref, ngb_text, fr_text = exemple
            self.review_exemple_text.insert("1.0", f"{ngb_text}\n→ {fr_text}")

        try:
            autres = json.loads(autres_json)
        except Exception:
            autres = []
        for alt in autres:
            b = ttk.Button(self.chip_frame, text=alt,
                           command=lambda a=alt: self._set_review_fr(a))
            b.pack(side="left", padx=3)

        self.run_grammar_suggestion()

    def run_grammar_suggestion(self):
        """Consulte Lexique383 pour la traduction française actuelle et pré-remplit
        catégorie/genre/nombre — exactement le mécanisme 'Kagə = arbre -> nom, masculin'."""
        if not HAS_LEXIQUE_FR:
            self.suggestion_note.config(
                text="Suggestion indisponible : bibliothèque 'pylexique' non installée (pip install pylexique).")
            return
        fr_word = self.review_fr_entry.get().strip()
        suggestion = suggest_grammar_fr(fr_word)
        if not suggestion:
            self.suggestion_note.config(text=f"Aucune suggestion trouvée pour « {fr_word} » dans le dictionnaire français.")
            return
        if suggestion["categorie"]:
            self.review_cat_combo.set(suggestion["categorie"])
        if suggestion["genre"]:
            self.review_genre_combo.set(suggestion["genre"])
        if suggestion["nombre"]:
            self.review_nombre_combo.set(suggestion["nombre"])
        self.suggestion_note.config(
            text=f"Suggéré automatiquement depuis « {fr_word} » (Lexique383) — vérifie et corrige si besoin.")

    def _set_review_fr(self, val):
        self.review_fr_entry.delete(0, tk.END)
        self.review_fr_entry.insert(0, val)
        self.run_grammar_suggestion()

    def _set_review_domaine(self, val):
        self.review_domaine_entry.set(val)

    def validate_current_word(self):
        if not getattr(self, "current_review_word", None):
            return
        c = self.db.conn.cursor()
        try:
            c.execute("""UPDATE words SET statut='valide', traduction_validee=?, categorie=?,
                         genre=?, nombre=?, domaine_semantique=?, exemple_phrase=?, definition=?,
                         notes=?, date_validation=? WHERE mot_ngambay=?""",
                      (self.review_fr_entry.get().strip(), self.review_cat_combo.get() or None,
                       self.review_genre_combo.get() or None, self.review_nombre_combo.get() or None,
                       self.review_domaine_entry.get().strip() or None,
                       self.review_exemple_text.get("1.0", "end").strip() or None,
                       self.review_definition_entry.get().strip() or None,
                       self.review_notes_text.get("1.0", "end").strip() or None,
                       datetime.now().isoformat(), self.current_review_word))
            self.db.conn.commit()
        except sqlite3.Error as e:
            self.db.conn.rollback()
            messagebox.showerror("Erreur de base de données", f"Impossible d'enregistrer la validation :\n{e}")
            return
        self.load_next_review_word()
        self.refresh_dashboard()

    def reject_current_word(self):
        if not getattr(self, "current_review_word", None):
            return
        c = self.db.conn.cursor()
        try:
            c.execute("UPDATE words SET statut='rejete', date_validation=? WHERE mot_ngambay=?",
                      (datetime.now().isoformat(), self.current_review_word))
            self.db.conn.commit()
        except sqlite3.Error as e:
            self.db.conn.rollback()
            messagebox.showerror("Erreur de base de données", f"Impossible d'enregistrer le rejet :\n{e}")
            return
        self.load_next_review_word()
        self.refresh_dashboard()

    # -- Onglet Concordance active (le flux interactif que tu as décrit) ----
    def _build_concordance_tab(self):
        f = self.tab_concordance
        ttk.Label(f, text="Ajouter une nouvelle phrase au corpus", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(f, text="Tape une phrase en ngambay puis sa traduction française. "
                          "Le moteur l'ajoute au corpus et met à jour ses hypothèses immédiatement.",
                  style="Sub.TLabel", wraplength=700, justify="left").pack(anchor="w", pady=(2, 14))

        ttk.Label(f, text="Phrase en ngambay :").pack(anchor="w")
        self.new_ngb_text = tk.Text(f, height=3, width=80, font=("Segoe UI", 11), wrap="word")
        self.new_ngb_text.pack(anchor="w", pady=(2, 10))

        ttk.Label(f, text="Traduction en français :").pack(anchor="w")
        self.new_fr_text = tk.Text(f, height=3, width=80, font=("Segoe UI", 11), wrap="word")
        self.new_fr_text.pack(anchor="w", pady=(2, 10))

        ttk.Button(f, text="Analyser et enregistrer", style="Accent.TButton",
                   command=self.add_sentence_pair).pack(anchor="w", pady=(4, 14))

        ttk.Label(f, text="Résultat de l'analyse :", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.concordance_result = tk.Text(f, height=8, width=80, font=("Consolas", 10),
                                          state="disabled", bg="#F4EEE1")
        self.concordance_result.pack(anchor="w", pady=(4, 0), fill="both", expand=True)

    def add_sentence_pair(self):
        ngb = self.new_ngb_text.get("1.0", "end").strip()
        fr = self.new_fr_text.get("1.0", "end").strip()
        if not ngb or not fr:
            messagebox.showwarning("Champs manquants", "Merci de remplir la phrase ngambay ET sa traduction.")
            return

        ref = f"MANUEL {datetime.now().strftime('%Y%m%d%H%M%S%f')} {uuid.uuid4().hex}"
        c = self.db.conn.cursor()
        try:
            c.execute("INSERT INTO verses (ref, ngambay, francais, source) VALUES (?,?,?,?)",
                      (ref, ngb, fr, "saisie_manuelle"))
            self.db.conn.commit()
            n_contra = self.engine.recompute_all()
        except sqlite3.Error as e:
            self.db.conn.rollback()
            messagebox.showerror("Erreur d'enregistrement", f"Impossible d'enregistrer la phrase ou son analyse :\n{e}")
            return

        # affiche ce que le moteur a déduit pour les mots de cette phrase précise
        words_in_sentence = tokenize(ngb)
        c = self.db.conn.cursor()
        lines = []
        for w in words_in_sentence:
            row = c.execute("SELECT candidat_francais, score_confiance, frequence, statut FROM words WHERE mot_ngambay=?",
                             (w,)).fetchone()
            if row:
                candidat, score, freq, statut = row
                marker = "déjà validé" if statut == "valide" else "hypothèse"
                lines.append(f"  '{w}' -> '{candidat}'  ({marker}, confiance {int(score*100)}%, vu {freq}x)")

        self.concordance_result.config(state="normal")
        self.concordance_result.delete("1.0", tk.END)
        self.concordance_result.insert(tk.END, f"Phrase enregistrée ({ref}).\n\n")
        self.concordance_result.insert(tk.END, "\n".join(lines) if lines else "  (aucun mot reconnu)")
        if n_contra:
            self.concordance_result.insert(tk.END, f"\n\n⚠ {n_contra} contradiction(s) détectée(s) avec des mots déjà validés — voir le Tableau de bord.")
        self.concordance_result.config(state="disabled")

        self.new_ngb_text.delete("1.0", tk.END)
        self.new_fr_text.delete("1.0", tk.END)
        self.refresh_dashboard()
        self.load_next_review_word()
        self.refresh_dictionary()

    # -- Onglet Dictionnaire --------------------------------------------------
    def _build_dictionary_tab(self):
        f = self.tab_dictionary
        top = ttk.Frame(f)
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text="Rechercher :").pack(side="left")
        self.dict_search_var = tk.StringVar()
        self.dict_search_var.trace_add("write", lambda *a: self.refresh_dictionary())
        ttk.Entry(top, textvariable=self.dict_search_var, width=30).pack(side="left", padx=6)

        columns = ("mot", "traduction", "categorie", "genre", "nombre", "domaine", "confiance")
        self.dict_tree = ttk.Treeview(f, columns=columns, show="headings", height=20)
        for col, label, w in [("mot", "Mot ngambay", 120), ("traduction", "Traduction", 140),
                               ("categorie", "Catégorie", 80), ("genre", "Genre", 70),
                               ("nombre", "Nombre", 80), ("domaine", "Domaine sémantique", 140),
                               ("confiance", "Confiance", 70)]:
            self.dict_tree.heading(col, text=label)
            self.dict_tree.column(col, width=w)
        self.dict_tree.pack(fill="both", expand=True)
        self.dict_tree.bind("<Double-1>", self._on_dict_double_click)
        ttk.Label(f, text="Double-clique sur un mot pour voir/modifier sa fiche complète.",
                  style="Sub.TLabel").pack(anchor="w", pady=(6, 0))

    def _on_dict_double_click(self, event):
        selection = self.dict_tree.selection()
        if not selection:
            return
        mot = self.dict_tree.item(selection[0], "values")[0]
        self.open_fiche_editor(mot)

    def open_fiche_editor(self, mot):
        c = self.db.conn.cursor()
        row = c.execute("""SELECT traduction_validee, categorie, genre, nombre, domaine_semantique,
                                   exemple_phrase, definition, notes
                            FROM words WHERE mot_ngambay=?""", (mot,)).fetchone()
        if not row:
            return
        trad, cat, genre, nombre, domaine, exemple, definition, notes = row

        win = tk.Toplevel(self.root)
        win.title(f"Fiche — {mot}")
        win.configure(bg="#ECE4D3")
        pad = ttk.Frame(win, padding=18)
        pad.pack(fill="both", expand=True)

        ttk.Label(pad, text=mot, font=("Georgia", 20, "bold")).pack(anchor="w", pady=(0, 14))

        ttk.Label(pad, text="Traduction française :").pack(anchor="w")
        e_trad = ttk.Entry(pad, width=50); e_trad.insert(0, trad or ""); e_trad.pack(anchor="w", pady=(2, 10))

        row1 = ttk.Frame(pad); row1.pack(anchor="w", pady=(0, 10))
        ttk.Label(row1, text="Catégorie :").grid(row=0, column=0, sticky="w")
        e_cat = ttk.Combobox(row1, values=CATEGORIES, width=14); e_cat.set(cat or ""); e_cat.grid(row=0, column=1, padx=6)
        ttk.Label(row1, text="Genre :").grid(row=0, column=2, sticky="w")
        e_genre = ttk.Combobox(row1, values=["", "masculin", "féminin"], width=10); e_genre.set(genre or ""); e_genre.grid(row=0, column=3, padx=6)
        ttk.Label(row1, text="Nombre :").grid(row=0, column=4, sticky="w")
        e_nombre = ttk.Combobox(row1, values=["", "singulier", "pluriel", "invariable"], width=10); e_nombre.set(nombre or ""); e_nombre.grid(row=0, column=5, padx=6)

        ttk.Label(pad, text="Domaine sémantique :").pack(anchor="w")
        e_domaine = ttk.Combobox(pad, values=DOMAINES_SEMANTIQUES, width=30); e_domaine.set(domaine or ""); e_domaine.pack(anchor="w", pady=(2, 10))

        ttk.Label(pad, text="Exemple de phrase :").pack(anchor="w")
        e_exemple = tk.Text(pad, height=3, width=55, wrap="word"); e_exemple.insert("1.0", exemple or ""); e_exemple.pack(anchor="w", pady=(2, 10))

        ttk.Label(pad, text="Définition :").pack(anchor="w")
        e_def = ttk.Entry(pad, width=50); e_def.insert(0, definition or ""); e_def.pack(anchor="w", pady=(2, 10))

        ttk.Label(pad, text="Notes :").pack(anchor="w")
        e_notes = tk.Text(pad, height=3, width=55, wrap="word"); e_notes.insert("1.0", notes or ""); e_notes.pack(anchor="w", pady=(2, 14))

        ttk.Separator(pad, orient="horizontal").pack(fill="x", pady=(2, 12))
        ttk.Label(pad, text="Relations lexicales (champ lexical)", font=("Segoe UI", 10, "bold")).pack(anchor="w")

        rel_list_frame = ttk.Frame(pad)
        rel_list_frame.pack(fill="x", pady=(6, 8))
        rel_listbox = tk.Listbox(rel_list_frame, height=5, font=("Segoe UI", 9))
        rel_listbox.pack(fill="x")

        def refresh_relations():
            rel_listbox.delete(0, tk.END)
            c3 = self.db.conn.cursor()
            rels = c3.execute("SELECT id, type_relation, mot_cible FROM relations WHERE mot_source=? ORDER BY type_relation",
                               (mot,)).fetchall()
            rel_listbox.rel_ids = []
            for rid, typ, cible in rels:
                rel_listbox.insert(tk.END, f"{typ} → {cible}")
                rel_listbox.rel_ids.append(rid)

        add_row = ttk.Frame(pad)
        add_row.pack(anchor="w", pady=(0, 6))
        ttk.Label(add_row, text="Type :").grid(row=0, column=0, sticky="w")
        rel_type_combo = ttk.Combobox(add_row, values=TYPES_RELATIONS, width=24, state="readonly")
        rel_type_combo.grid(row=0, column=1, padx=6)
        ttk.Label(add_row, text="Mot lié :").grid(row=0, column=2, sticky="w")
        all_words = [r[0] for r in c.execute("SELECT mot_ngambay FROM words WHERE statut='valide' ORDER BY mot_ngambay").fetchall()]
        rel_target_combo = ttk.Combobox(add_row, values=all_words, width=20)
        rel_target_combo.grid(row=0, column=3, padx=6)

        def add_relation():
            typ = rel_type_combo.get().strip()
            cible = rel_target_combo.get().strip()
            if not typ or not cible:
                messagebox.showwarning("Champs manquants", "Choisis un type de relation et un mot lié.")
                return
            c4 = self.db.conn.cursor()
            if c4.execute("SELECT 1 FROM relations WHERE mot_source=? AND mot_cible=? AND type_relation=?",
                          (mot, cible, typ)).fetchone():
                messagebox.showinfo("Relation existante", "Cette relation est déjà enregistrée.", parent=win)
                return
            try:
                c4.execute("INSERT INTO relations (mot_source, mot_cible, type_relation, date) VALUES (?,?,?,?)",
                           (mot, cible, typ, datetime.now().isoformat()))
                self.db.conn.commit()
            except sqlite3.Error as e:
                self.db.conn.rollback()
                messagebox.showerror("Erreur de base de données", f"Impossible d'ajouter la relation :\n{e}", parent=win)
                return
            rel_type_combo.set("")
            rel_target_combo.set("")
            refresh_relations()

        def remove_relation():
            sel = rel_listbox.curselection()
            if not sel:
                return
            rid = rel_listbox.rel_ids[sel[0]]
            c5 = self.db.conn.cursor()
            try:
                c5.execute("DELETE FROM relations WHERE id=?", (rid,))
                self.db.conn.commit()
            except sqlite3.Error as e:
                self.db.conn.rollback()
                messagebox.showerror("Erreur de base de données", f"Impossible de retirer la relation :\n{e}", parent=win)
                return
            refresh_relations()

        rel_btn_row = ttk.Frame(pad)
        rel_btn_row.pack(anchor="w", pady=(0, 14))
        ttk.Button(rel_btn_row, text="+ Ajouter la relation", command=add_relation).pack(side="left", padx=(0, 8))
        ttk.Button(rel_btn_row, text="Retirer la sélection", command=remove_relation).pack(side="left")

        refresh_relations()

        def save_and_close():
            c2 = self.db.conn.cursor()
            try:
                c2.execute("""UPDATE words SET traduction_validee=?, categorie=?, genre=?, nombre=?,
                              domaine_semantique=?, exemple_phrase=?, definition=?, notes=?,
                              date_validation=? WHERE mot_ngambay=?""",
                           (e_trad.get().strip(), e_cat.get() or None, e_genre.get() or None, e_nombre.get() or None,
                            e_domaine.get().strip() or None, e_exemple.get("1.0", "end").strip() or None,
                            e_def.get().strip() or None, e_notes.get("1.0", "end").strip() or None,
                            datetime.now().isoformat(), mot))
                self.db.conn.commit()
            except sqlite3.Error as e:
                self.db.conn.rollback()
                messagebox.showerror("Erreur de base de données", f"Impossible d'enregistrer la fiche :\n{e}", parent=win)
                return
            self.refresh_dictionary()
            win.destroy()

        btn_row = ttk.Frame(pad)
        btn_row.pack(anchor="w")
        ttk.Button(btn_row, text="💾 Enregistrer", style="Accent.TButton", command=save_and_close).pack(side="left", padx=(0, 8))
        ttk.Button(btn_row, text="Fermer sans enregistrer", command=win.destroy).pack(side="left")

    def refresh_dictionary(self):
        for row in self.dict_tree.get_children():
            self.dict_tree.delete(row)
        c = self.db.conn.cursor()
        query = self.dict_search_var.get().strip().lower()
        rows = c.execute("""SELECT mot_ngambay, traduction_validee, categorie, genre, nombre,
                                    domaine_semantique, score_confiance
                             FROM words WHERE statut='valide' ORDER BY mot_ngambay""").fetchall()
        for mot, trad, cat, genre, nombre, domaine, score in rows:
            if query and query not in mot.lower() and query not in (trad or "").lower():
                continue
            self.dict_tree.insert("", "end", values=(mot, trad or "", cat or "", genre or "", nombre or "",
                                                       domaine or "", f"{int((score or 0)*100)}%"))

    # -- Onglet Export --------------------------------------------------------
    def _build_export_tab(self):
        f = self.tab_export
        ttk.Label(f, text="Exporter le dictionnaire validé", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(f, text="Seuls les mots validés sont exportés. Les formats Bloom, LIFT et USFM "
                          "arrivent en Phase 4 du projet — pour l'instant : JSON, CSV, texte imprimable et LIFT.",
                  style="Sub.TLabel", wraplength=700, justify="left").pack(anchor="w", pady=(2, 16))

        ttk.Button(f, text="Exporter en JSON", command=self.export_json).pack(anchor="w", pady=4)
        ttk.Button(f, text="Exporter en CSV (Excel)", command=self.export_csv).pack(anchor="w", pady=4)
        ttk.Button(f, text="Exporter en texte imprimable", command=self.export_txt).pack(anchor="w", pady=4)
        ttk.Button(f, text="Exporter en LIFT (FLEx, WeSay)", command=self.export_lift).pack(anchor="w", pady=4)

    def _get_validated(self):
        c = self.db.conn.cursor()
        return c.execute("""SELECT mot_ngambay, traduction_validee, categorie, genre, nombre,
                                    domaine_semantique, exemple_phrase, definition, notes, date_validation
                             FROM words WHERE statut='valide' ORDER BY mot_ngambay""").fetchall()

    def export_json(self):
        rows = self._get_validated()
        c = self.db.conn.cursor()
        data = {}
        for r in rows:
            mot = r[0]
            rels = c.execute("SELECT type_relation, mot_cible FROM relations WHERE mot_source=?", (mot,)).fetchall()
            data[mot] = {"traduction": r[1], "categorie": r[2], "genre": r[3], "nombre": r[4],
                        "domaine_semantique": r[5], "exemple_phrase": r[6], "definition": r[7],
                        "notes": r[8], "date_validation": r[9],
                        "relations_lexicales": [{"type": t, "mot_lie": m} for t, m in rels]}
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False, indent=2)
            except OSError as e:
                messagebox.showerror("Erreur d'export", f"Impossible d'écrire le fichier :\n{e}")
                return
            messagebox.showinfo("Export", f"{len(data)} mots exportés vers {path}")

    def export_csv(self):
        rows = self._get_validated()
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            try:
                with open(path, "w", encoding="utf-8", newline="") as fh:
                    writer = csv.writer(fh)
                    writer.writerow(["mot_ngambay", "traduction_francaise", "categorie", "genre", "nombre",
                                      "domaine_semantique", "exemple_phrase", "definition", "notes", "date_validation"])
                    writer.writerows(rows)
            except OSError as e:
                messagebox.showerror("Erreur d'export", f"Impossible d'écrire le fichier :\n{e}")
                return
            messagebox.showinfo("Export", f"{len(rows)} mots exportés vers {path}")

    def export_txt(self):
        rows = self._get_validated()
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Texte", "*.txt")])
        if path:
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("DICTIONNAIRE NGAMBAY — FRANÇAIS\n")
                    fh.write("=" * 40 + "\n\n")
                    for mot, trad, cat, genre, nombre, domaine, exemple, definition, notes, _ in rows:
                        details = ", ".join(x for x in [cat, genre, nombre, domaine] if x)
                        details_str = f" ({details})" if details else ""
                        fh.write(f"{mot}{details_str} : {trad}\n")
                        if definition:
                            fh.write(f"    Définition : {definition}\n")
                        if exemple:
                            fh.write(f"    Exemple : {exemple}\n")
                        if notes:
                            fh.write(f"    Notes : {notes}\n")
                        fh.write("\n")
            except OSError as e:
                messagebox.showerror("Erreur d'export", f"Impossible d'écrire le fichier :\n{e}")
                return
            messagebox.showinfo("Export", f"{len(rows)} mots exportés vers {path}")

    def export_lift(self):
        rows = self._get_validated()
        relations = self.db.conn.cursor().execute(
            "SELECT mot_source, mot_cible, type_relation FROM relations").fetchall()
        path = filedialog.asksaveasfilename(defaultextension=".lift", filetypes=[("LIFT", "*.lift")])
        if path:
            try:
                build_lift(rows, relations).write(path, encoding="utf-8", xml_declaration=True)
            except OSError as e:
                messagebox.showerror("Erreur d'export", f"Impossible d'écrire le fichier :\n{e}")
                return
            messagebox.showinfo("Export", f"{len(rows)} mots exportés vers {path}")


# ---------------------------------------------------------------------------
def main():
    root = tk.Tk()
    global DB_PATH
    try:
        DB_PATH = database_path()
        LexicographeApp(root)
    except (OSError, sqlite3.Error, json.JSONDecodeError) as e:
        messagebox.showerror("Démarrage impossible", f"L'application n'a pas pu démarrer :\n{e}")
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()

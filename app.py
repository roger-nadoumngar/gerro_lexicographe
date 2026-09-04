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
from collections import defaultdict
from datetime import datetime

import shutil

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

def resource_path(name):
    """Trouve un fichier à côté de l'exécutable, même une fois compilé en .exe."""
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, name)

DB_PATH = resource_path("lexique_ngambay.db")

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
            date_validation TEXT
        );

        CREATE TABLE IF NOT EXISTS audio_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom_fichier TEXT,
            chemin_local TEXT,
            note TEXT,
            date_ajout TEXT
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
        self.conn.commit()

    def close(self):
        self.conn.close()


# ---------------------------------------------------------------------------
# Moteur de concordance / alignement (le "cerveau" statistique)
# ---------------------------------------------------------------------------

def tokenize(s):
    s = s.lower()
    s = re.sub(r"[’'\",.;:!?()«»]", " ", s)
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

        for nw, old_fr, new_fr in contradictions_found:
            c.execute("""INSERT INTO contradictions
                         (mot_ngambay, ancienne_traduction, nouvelle_traduction, ref_verset, date)
                         VALUES (?, ?, ?, ?, ?)""",
                      (nw, old_fr, new_fr, '', datetime.now().isoformat()))

        self.db.conn.commit()
        return len(contradictions_found)


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
            clean = re.sub(r'\\[a-z]+\*?', '', clean)
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
# Initialisation des données au premier lancement
# ---------------------------------------------------------------------------

def bootstrap_data(db: Database):
    c = db.conn.cursor()
    count = c.execute("SELECT COUNT(*) FROM verses").fetchone()[0]
    if count > 0:
        return  # déjà initialisé

    ngb_path = resource_path("ngambay_verses.json")
    fr_path = resource_path("french_verses.json")
    if not (os.path.exists(ngb_path) and os.path.exists(fr_path)):
        return

    with open(ngb_path, encoding="utf-8") as f:
        ngb = json.load(f)
    with open(fr_path, encoding="utf-8") as f:
        fr = json.load(f)

    for ref, text in ngb.items():
        if ref in fr:
            c.execute("INSERT OR REPLACE INTO verses (ref, ngambay, francais, source) VALUES (?,?,?,?)",
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
        self.tab_import = ttk.Frame(self.notebook, padding=16)
        self.tab_validation = ttk.Frame(self.notebook, padding=16)
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
        rows = c.execute("""SELECT mot_ngambay, ancienne_traduction, nouvelle_traduction, date
                             FROM contradictions WHERE resolu=0 ORDER BY date DESC""").fetchall()
        if not rows:
            self.contradiction_list.insert(tk.END, "  Aucune contradiction pour l'instant.")
        for mot, ancien, nouveau, date in rows:
            self.contradiction_list.insert(
                tk.END, f"  '{mot}' : validé comme « {ancien} », mais de nouvelles phrases suggèrent « {nouveau} »")

    def recompute_engine(self):
        n_contra = self.engine.recompute_all()
        self.refresh_dashboard()
        self.load_next_review_word()
        msg = "Moteur recalculé."
        if n_contra:
            msg += f" {n_contra} nouvelle(s) contradiction(s) détectée(s) — voir le tableau de bord."
        messagebox.showinfo("Concordance", msg)

    # -- Onglet Import ---------------------------------------------------------
    def _build_import_tab(self):
        f = self.tab_import

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
        for ref, txt in verses.items():
            existing = c.execute("SELECT ref FROM verses WHERE ref=?", (ref,)).fetchone()
            if existing:
                c.execute(f"UPDATE verses SET {col}=? WHERE ref=?", (txt, ref))
                n_updated += 1
            else:
                c.execute(f"INSERT INTO verses (ref, {col}, source) VALUES (?, ?, ?)",
                          (ref, txt, os.path.basename(path)))
                n_new += 1
        self.db.conn.commit()

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
        audio_dir = resource_path("audio")
        os.makedirs(audio_dir, exist_ok=True)
        dest = os.path.join(audio_dir, os.path.basename(path))
        try:
            shutil.copy2(path, dest)
        except Exception as e:
            messagebox.showerror("Erreur d'import", f"Impossible de copier ce fichier :\n{e}")
            return

        note = simpledialog.askstring("Note (optionnel)", "Ajouter une note sur ce fichier audio (ex : locuteur, contexte) :")
        c = self.db.conn.cursor()
        c.execute("INSERT INTO audio_files (nom_fichier, chemin_local, note, date_ajout) VALUES (?,?,?,?)",
                  (os.path.basename(path), dest, note or "", datetime.now().isoformat()))
        self.db.conn.commit()
        self._log_import(f"[AUDIO] {os.path.basename(path)} copié dans /audio — note : {note or '(aucune)'}")
        messagebox.showinfo("Import audio", "Fichier audio enregistré. La transcription automatique arrivera en Phase 5.")

    # -- Onglet Validation ---------------------------------------------------
    def _build_validation_tab(self):
        f = self.tab_validation
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

        btn_row = ttk.Frame(f)
        btn_row.pack(anchor="w")
        ttk.Button(btn_row, text="✓ Valider", style="Accent.TButton",
                   command=self.validate_current_word).pack(side="left", padx=(0, 8))
        ttk.Button(btn_row, text="✗ Rejeter", command=self.reject_current_word).pack(side="left", padx=(0, 8))
        ttk.Button(btn_row, text="Passer →", command=self.load_next_review_word).pack(side="left", padx=(0, 8))
        ttk.Button(btn_row, text="🔍 Re-suggérer (dictionnaire FR)",
                   command=self.run_grammar_suggestion).pack(side="left")

        self.review_queue = []
        self.review_index = 0

    def _refresh_review_queue(self):
        c = self.db.conn.cursor()
        rows = c.execute("""SELECT mot_ngambay, frequence, candidat_francais, score_confiance,
                                    co_occurrences, autres_candidats
                             FROM words WHERE statut='en_attente'
                             ORDER BY score_confiance DESC, frequence DESC""").fetchall()
        self.review_queue = rows
        self.review_index = 0

    def load_next_review_word(self):
        self._refresh_review_queue()
        for widget in self.chip_frame.winfo_children():
            widget.destroy()

        if not self.review_queue:
            self.review_word_var.set("File terminée")
            self.review_meta_var.set("Tous les mots proposés ont été passés en revue.")
            self.review_fr_entry.delete(0, tk.END)
            self.review_cat_combo.set("")
            return

        mot, freq, candidat, score, cooc, autres_json = self.review_queue[0]
        self.current_review_word = mot
        self.review_word_var.set(mot)
        self.review_meta_var.set(f"apparaît {freq}× · {cooc} co-occurrences · confiance {int(score*100)}%")
        self.review_fr_entry.delete(0, tk.END)
        self.review_fr_entry.insert(0, candidat or "")
        self.review_cat_combo.set("")
        self.review_genre_combo.set("")
        self.review_nombre_combo.set("")
        self.review_domaine_entry.set("")

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
        c.execute("""UPDATE words SET statut='valide', traduction_validee=?, categorie=?,
                     genre=?, nombre=?, domaine_semantique=?, date_validation=? WHERE mot_ngambay=?""",
                  (self.review_fr_entry.get().strip(), self.review_cat_combo.get() or None,
                   self.review_genre_combo.get() or None, self.review_nombre_combo.get() or None,
                   self.review_domaine_entry.get().strip() or None,
                   datetime.now().isoformat(), self.current_review_word))
        self.db.conn.commit()
        self.load_next_review_word()
        self.refresh_dashboard()

    def reject_current_word(self):
        if not getattr(self, "current_review_word", None):
            return
        c = self.db.conn.cursor()
        c.execute("UPDATE words SET statut='rejete', date_validation=? WHERE mot_ngambay=?",
                  (datetime.now().isoformat(), self.current_review_word))
        self.db.conn.commit()
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

        ref = f"MANUEL {datetime.now().strftime('%Y%m%d%H%M%S')}"
        c = self.db.conn.cursor()
        c.execute("INSERT INTO verses (ref, ngambay, francais, source) VALUES (?,?,?,?)",
                  (ref, ngb, fr, "saisie_manuelle"))
        self.db.conn.commit()

        n_contra = self.engine.recompute_all()

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
                          "arrivent en Phase 4 du projet — pour l'instant : JSON, CSV et texte imprimable.",
                  style="Sub.TLabel", wraplength=700, justify="left").pack(anchor="w", pady=(2, 16))

        ttk.Button(f, text="Exporter en JSON", command=self.export_json).pack(anchor="w", pady=4)
        ttk.Button(f, text="Exporter en CSV (Excel)", command=self.export_csv).pack(anchor="w", pady=4)
        ttk.Button(f, text="Exporter en texte imprimable", command=self.export_txt).pack(anchor="w", pady=4)

    def _get_validated(self):
        c = self.db.conn.cursor()
        return c.execute("""SELECT mot_ngambay, traduction_validee, categorie, genre, nombre,
                                    domaine_semantique, date_validation
                             FROM words WHERE statut='valide' ORDER BY mot_ngambay""").fetchall()

    def export_json(self):
        rows = self._get_validated()
        data = {r[0]: {"traduction": r[1], "categorie": r[2], "genre": r[3], "nombre": r[4],
                       "domaine_semantique": r[5], "date_validation": r[6]}
                for r in rows}
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            messagebox.showinfo("Export", f"{len(data)} mots exportés vers {path}")

    def export_csv(self):
        rows = self._get_validated()
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["mot_ngambay", "traduction_francaise", "categorie", "genre", "nombre",
                                  "domaine_semantique", "date_validation"])
                writer.writerows(rows)
            messagebox.showinfo("Export", f"{len(rows)} mots exportés vers {path}")

    def export_txt(self):
        rows = self._get_validated()
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Texte", "*.txt")])
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("DICTIONNAIRE NGAMBAY — FRANÇAIS\n")
                fh.write("=" * 40 + "\n\n")
                for mot, trad, cat, genre, nombre, domaine, _ in rows:
                    details = ", ".join(x for x in [cat, genre, nombre, domaine] if x)
                    details_str = f" ({details})" if details else ""
                    fh.write(f"{mot}{details_str} : {trad}\n")
            messagebox.showinfo("Export", f"{len(rows)} mots exportés vers {path}")


# ---------------------------------------------------------------------------
def main():
    root = tk.Tk()
    app = LexicographeApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
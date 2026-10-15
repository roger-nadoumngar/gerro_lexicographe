"""Site web du dictionnaire : un dossier autonome (index.html, donnees.js, images/) à mettre sur
n'importe quel hébergement web, ou à ouvrir sans internet.

Le contenu est celui du dictionnaire imprimé (`publication.contenu`) : mêmes entrées, même ordre
alphabétique du projet, mêmes statuts publiés. Le site ajoute :
* la recherche dans les deux langues (vedettes, gloses, index inverse), sans tenir compte des tons
  ni des majuscules si on le souhaite ;
* la barre des lettres de l'alphabet ;
* un lien direct vers chaque entrée (index.html#vedette) ;
* les photos liées aux entrées.
Les données ne sont jamais insérées comme du HTML : la page les affiche comme du texte."""

import json
import os
import shutil
import unicodedata
from datetime import date

from . import APP_NAME, __version__, publication


def _cle(texte):
    """Clé de recherche : minuscules, sans tons ni autres signes combinants."""
    decompose = unicodedata.normalize("NFD", (texte or "").lower())
    return "".join(c for c in decompose if not unicodedata.combining(c))


def donnees(projet, options):
    c = publication.contenu(projet, options)
    images = {}
    for eid, chemin in projet.conn.execute(
            """SELECT l.entree_id, m.chemin FROM medias_liens l JOIN medias m ON m.id = l.media_id
               WHERE l.role = 'image'"""):
        if os.path.isfile(chemin):
            images.setdefault(eid, []).append(chemin)
    entrees, fichiers = [], {}
    for lettre, groupe in c.lettres:
        for e in groupe:
            noms = []
            for chemin in images.get(e.entree_id, []):
                nom = fichiers.setdefault(chemin, f"{len(fichiers) + 1:05d}{os.path.splitext(chemin)[1].lower()}")
                noms.append(nom)
            entrees.append({
                "v": e.vedette, "t": e.tete, "l": lettre, "p": e.prononciation, "m": e.type_morph,
                "s": [{"n": s.numero, "c": s.categorie, "g": s.glose, "d": s.definition if s.definition != s.glose
                       else "", "x": s.exemples} for s in e.sens],
                "var": e.variantes, "comp": e.composants, "ren": e.renvois_vedettes, "img": noms,
                "k": _cle(e.tete), "kg": _cle(" ; ".join(s.glose for s in e.sens)),
            })
    return {
        "titre": c.titre, "sous_titre": c.sous_titre, "auteurs": c.auteurs,
        "langue_vern": c.langue_vern, "langue_analyse": c.langue_analyse,
        "lettres": [l for l, _ in c.lettres], "entrees": entrees,
        "index": [[mot, vedettes, _cle(mot)] for mot, vedettes in c.index],
        "date": date.today().isoformat(), "logiciel": f"{APP_NAME} {__version__}",
    }, fichiers


def exporter(projet, dossier, options):
    """Écrit le site dans `dossier` (créé si besoin). Retourne (nombre d'entrées, chemin de index.html)."""
    d, fichiers = donnees(projet, options)
    os.makedirs(os.path.join(dossier, "images"), exist_ok=True)
    for source, nom in fichiers.items():
        shutil.copy2(source, os.path.join(dossier, "images", nom))
    with open(os.path.join(dossier, "donnees.js"), "w", encoding="utf-8") as f:
        # un fichier de script (et non JSON lu par fetch) : la page marche aussi ouverte sans serveur
        f.write("window.DICO = ")
        json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    police = projet.reglage("police_vern") or ""
    page = (PAGE.replace("__TITRE__", _html(d["titre"]))
                .replace("__POLICE__", json.dumps(police)[1:-1].replace("<", "")))
    chemin = os.path.join(dossier, "index.html")
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(page)
    return len(d["entrees"]), chemin


def _html(texte):
    import html
    return html.escape(texte or "")


PAGE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITRE__</title>
<style>
:root { --fond:#f6f1e7; --carte:#fffdf8; --texte:#2a2620; --doux:#6d655a; --accent:#1f5c55; --ligne:#e2d9c8; }
@media (prefers-color-scheme: dark) {
  :root { --fond:#1d1b18; --carte:#26231f; --texte:#ece6da; --doux:#a89f92; --accent:#7cc4b8; --ligne:#3a352e; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--fond); color:var(--texte);
       font-family: "__POLICE__", "Charis SIL", "Gentium Plus", "Noto Serif", Georgia, serif; line-height:1.5; }
header { background:var(--accent); color:#fff; padding:18px 16px 12px; }
header h1 { margin:0; font-size:1.5rem; }
header p { margin:2px 0 0; opacity:.85; font-size:.95rem; }
.barre { background:var(--fond); padding:10px 16px; border-bottom:1px solid var(--ligne); }
/* barre fixe seulement sur grand écran : sur un téléphone elle cacherait les résultats */
@media (min-width: 760px) { .barre { position:sticky; top:0; z-index:2; } }
.recherche { display:flex; gap:8px; flex-wrap:wrap; }
.recherche input { flex:1 1 220px; font:inherit; font-size:1.05rem; padding:8px 10px; border:1px solid var(--ligne);
                   border-radius:8px; background:var(--carte); color:var(--texte); }
.recherche select { font:inherit; padding:8px; border-radius:8px; border:1px solid var(--ligne); background:var(--carte); color:var(--texte); }
.lettres { display:flex; flex-wrap:wrap; gap:4px; margin-top:8px; }
.lettres button { font:inherit; border:1px solid var(--ligne); background:var(--carte); color:var(--texte);
                  border-radius:6px; padding:2px 8px; cursor:pointer; min-width:2em; }
.lettres button.active { background:var(--accent); color:#fff; border-color:var(--accent); }
main { max-width:860px; margin:0 auto; padding:12px 16px 40px; }
.entree { background:var(--carte); border:1px solid var(--ligne); border-radius:10px; padding:10px 14px; margin:8px 0; }
.vedette { font-weight:700; font-size:1.15rem; }
.pron, .cat, .doux { color:var(--doux); }
.cat { font-style:italic; }
.ex { font-style:italic; }
.sens { margin:4px 0 0 0; }
a { color:var(--accent); cursor:pointer; text-decoration:none; }
a:hover { text-decoration:underline; }
.illus { max-width:100%; max-height:220px; border-radius:8px; margin-top:6px; display:block; }
.info { color:var(--doux); margin:10px 0; }
footer { color:var(--doux); font-size:.85rem; text-align:center; padding:20px 16px; }
</style>
</head>
<body>
<header><h1 id="titre"></h1><p id="sous-titre"></p></header>
<div class="barre">
  <div class="recherche">
    <input id="q" type="search" placeholder="Rechercher…" autocomplete="off">
    <select id="mode"></select>
    <label class="doux"><input id="tons" type="checkbox" checked> sans tenir compte des tons</label>
  </div>
  <div class="lettres" id="lettres"></div>
</div>
<main><div class="info" id="info"></div><div id="liste"></div></main>
<footer id="pied"></footer>
<script src="donnees.js"></script>
<script>
(function () {
  "use strict";
  var D = window.DICO, PAR_PAGE = 60;
  function el(tag, cls, texte) { var n = document.createElement(tag); if (cls) n.className = cls;
    if (texte !== undefined && texte !== null) n.textContent = texte; return n; }
  function cle(t) { return (t || "").toLowerCase().normalize("NFD").replace(/[\\u0300-\\u036f\\u1ab0-\\u1aff\\u1dc0-\\u1dff]/g, ""); }
  function brut(t) { return (t || "").toLowerCase().normalize("NFC"); }
  var parVedette = {}; D.entrees.forEach(function (e, i) { parVedette[e.v] = i; });

  document.getElementById("titre").textContent = D.titre;
  document.getElementById("sous-titre").textContent = [D.sous_titre, D.auteurs].filter(Boolean).join(" — ");
  document.title = D.titre;
  var mode = document.getElementById("mode");
  [["tout", "les deux langues"], ["vern", D.langue_vern], ["analyse", D.langue_analyse]].forEach(function (o) {
    var opt = el("option", null, o[1]); opt.value = o[0]; mode.appendChild(opt); });
  document.getElementById("pied").textContent = D.entrees.length + " entrées · mis à jour le " + D.date +
    " · produit avec " + D.logiciel;

  function afficherEntree(e) {
    var div = el("div", "entree"); div.id = "e-" + parVedette[e.v];
    var tete = el("div"); tete.appendChild(el("span", "vedette", e.v));
    if (e.p) tete.appendChild(el("span", "pron", " [" + e.p + "]"));
    if (e.m) tete.appendChild(el("span", "cat", " " + e.m));
    if (e["var"].length) tete.appendChild(el("span", "doux", " (" + e["var"].join("; ") + ")"));
    div.appendChild(tete);
    e.s.forEach(function (s) {
      var p = el("div", "sens");
      if (e.s.length > 1) p.appendChild(el("b", null, s.n + ". "));
      if (s.c) p.appendChild(el("span", "cat", s.c + " "));
      p.appendChild(el("span", null, s.g));
      if (s.d) p.appendChild(el("span", "doux", " — " + s.d));
      s.x.forEach(function (x) {
        p.appendChild(document.createTextNode(" "));
        p.appendChild(el("span", "ex", x[0]));
        if (x[1]) p.appendChild(el("span", null, " « " + x[1] + " »"));
      });
      div.appendChild(p);
    });
    function liens(libelle, cibles) {
      if (!cibles.length) return;
      var p = el("div", "doux", libelle);
      cibles.forEach(function (c, i) {
        if (i) p.appendChild(document.createTextNode(", "));
        var a = el("a", null, c[1]); a.title = c[0];
        a.addEventListener("click", function () { aller(c[1]); }); p.appendChild(a);
      });
      div.appendChild(p);
    }
    liens("Composé de : ", e.comp.map(function (v) { return ["", v]; }));
    liens("Voir aussi : ", e.ren);
    e.img.forEach(function (nom) { var im = el("img", "illus"); im.src = "images/" + nom; im.alt = e.v;
      im.loading = "lazy"; div.appendChild(im); });
    return div;
  }

  var resultats = [], montres = 0;
  function montrer(liste, message) {
    resultats = liste; montres = 0;
    document.getElementById("info").textContent = message;
    document.getElementById("liste").innerHTML = "";
    plus();
  }
  function plus() {
    var cible = document.getElementById("liste"), fin = Math.min(montres + PAR_PAGE, resultats.length);
    for (; montres < fin; montres++) cible.appendChild(afficherEntree(D.entrees[resultats[montres]]));
    var ancien = document.getElementById("plus"); if (ancien) ancien.remove();
    if (montres < resultats.length) {
      var b = el("button", null, "Afficher la suite (" + (resultats.length - montres) + ")"); b.id = "plus";
      b.addEventListener("click", plus); cible.appendChild(b);
    }
  }
  function lettre(l) {
    document.querySelectorAll(".lettres button").forEach(function (b) { b.classList.toggle("active", b.textContent === l); });
    var liste = []; D.entrees.forEach(function (e, i) { if (e.l === l) liste.push(i); });
    montrer(liste, liste.length + " entrée(s) à la lettre " + l);
  }
  function chercher() {
    var q = document.getElementById("q").value.trim(), sansTons = document.getElementById("tons").checked;
    if (!q) { lettre(D.lettres[0]); return; }
    var f = sansTons ? cle : brut, k = f(q), m = mode.value, trouves = [], vus = {};
    function ajoute(i) { if (!vus[i]) { vus[i] = 1; trouves.push(i); } }
    D.entrees.forEach(function (e, i) {
      if (m !== "analyse" && (sansTons ? e.k : brut(e.t)).indexOf(k) === 0) ajoute(i);
    });
    if (m !== "vern") {
      D.index.forEach(function (x) {
        if ((sansTons ? x[2] : brut(x[0])).indexOf(k) === 0) x[1].forEach(function (v) {
          if (v in parVedette) ajoute(parVedette[v]); });
      });
      D.entrees.forEach(function (e, i) { if ((sansTons ? e.kg : brut(e.s.map(function (s) { return s.g; }).join(" ; ")))
        .indexOf(k) !== -1) ajoute(i); });
    }
    document.querySelectorAll(".lettres button").forEach(function (b) { b.classList.remove("active"); });
    montrer(trouves, trouves.length + " résultat(s) pour « " + q + " »");
  }
  function aller(vedette) {
    if (!(vedette in parVedette)) return;
    location.hash = encodeURIComponent(vedette);
  }
  function selonAdresse() {
    var v = decodeURIComponent(location.hash.slice(1));
    if (v && v in parVedette) { montrer([parVedette[v]], ""); window.scrollTo(0, 0); return true; }
    return false;
  }
  var barre = document.getElementById("lettres");
  D.lettres.forEach(function (l) { var b = el("button", null, l); b.addEventListener("click", function () {
    document.getElementById("q").value = ""; history.replaceState(null, "", " "); lettre(l); }); barre.appendChild(b); });
  var minuteur;
  document.getElementById("q").addEventListener("input", function () { clearTimeout(minuteur); minuteur = setTimeout(chercher, 200); });
  mode.addEventListener("change", chercher);
  document.getElementById("tons").addEventListener("change", chercher);
  window.addEventListener("hashchange", selonAdresse);
  if (!selonAdresse()) lettre(D.lettres[0]);
})();
</script>
</body>
</html>
"""

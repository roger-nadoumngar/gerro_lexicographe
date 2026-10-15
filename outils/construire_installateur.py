"""Construit le logiciel (.exe) puis le programme d'installation.

    python outils/construire_installateur.py

1. PyInstaller : dist/GerroLexicographe.exe (un seul fichier, avec l'icône et les ressources) ;
2. Inno Setup 6 : dist/GerroLexicographe-Installation-<version>.exe.
Les ressources livrées ne contiennent que des données des langues d'analyse (domaines sémantiques,
interface, guide) : aucune donnée d'une langue documentée."""

import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def version():
    texte = open(os.path.join(RACINE, "lexicographe", "__init__.py"), encoding="utf-8").read()
    return re.search(r'__version__ = "([^"]+)"', texte).group(1)


def iscc():
    candidats = [os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe"),
                 r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe", r"C:\Program Files\Inno Setup 6\ISCC.exe"]
    return next((c for c in candidats if os.path.isfile(c)), shutil.which("ISCC"))


def main():
    v = version()
    travail = tempfile.mkdtemp(prefix="gerro-construction-")
    ressources = os.path.join(RACINE, "lexicographe", "ressources")
    print(f"1/2 PyInstaller (version {v})…")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--windowed",
                    "--name", "GerroLexicographe", "--icon", os.path.join(RACINE, "installateur", "gerro.ico"),
                    "--add-data", f"{ressources}{os.pathsep}lexicographe/ressources",
                    "--workpath", os.path.join(travail, "work"), "--specpath", travail,
                    "--distpath", os.path.join(RACINE, "dist"), os.path.join(RACINE, "app.py")],
                   check=True, cwd=RACINE)
    shutil.rmtree(travail, ignore_errors=True)
    compilateur = iscc()
    if not compilateur:
        sys.exit("Inno Setup 6 n'est pas installé (https://jrsoftware.org) : seul le .exe a été construit.")
    print("2/2 Inno Setup…")
    subprocess.run([compilateur, f"/DVersion={v}", os.path.join(RACINE, "installateur", "GerroLexicographe.iss")],
                   check=True, cwd=os.path.join(RACINE, "installateur"))
    for f in sorted(glob.glob(os.path.join(RACINE, "dist", f"GerroLexicographe-Installation-{v}.exe"))):
        print(f"Prêt : {f} ({os.path.getsize(f) // (1024 * 1024)} Mo)")


if __name__ == "__main__":
    main()

; Programme d'installation de Gerro Lexicographe (Inno Setup 6)
; Construit par : python outils/construire_installateur.py
; La version est donnée par le script de construction (/DVersion=…), lue dans lexicographe/__init__.py.
; Les projets des utilisateurs (%LOCALAPPDATA%\GerroLexicographe) ne sont jamais touchés, ni à
; l'installation ni à la désinstallation.

#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{6C1E9B2A-5F3D-4A8E-9C27-3B8D41E07A52}
AppName=Gerro Lexicographe
AppVersion={#Version}
AppVerName=Gerro Lexicographe {#Version}
AppPublisher=Gerro Lexicographe
AppComments=Lexicographie et documentation des langues
DefaultDirName={autopf}\Gerro Lexicographe
DefaultGroupName=Gerro Lexicographe
DisableProgramGroupPage=yes
; installation pour l'utilisateur sans droits d'administrateur, ou pour tous si on le choisit
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=GerroLexicographe-Installation-{#Version}
SetupIconFile=gerro.ico
UninstallDisplayIcon={app}\GerroLexicographe.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ShowLanguageDialog=auto

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
fr.RaccourciBureau=Créer un raccourci sur le bureau
en.RaccourciBureau=Create a desktop shortcut
fr.Lancer=Lancer Gerro Lexicographe
en.Lancer=Launch Gerro Lexicographe

[Tasks]
Name: "bureau"; Description: "{cm:RaccourciBureau}"; Flags: unchecked

[Files]
Source: "..\dist\GerroLexicographe.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "gerro.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Gerro Lexicographe"; Filename: "{app}\GerroLexicographe.exe"; IconFilename: "{app}\gerro.ico"
Name: "{group}\{cm:UninstallProgram,Gerro Lexicographe}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Gerro Lexicographe"; Filename: "{app}\GerroLexicographe.exe"; IconFilename: "{app}\gerro.ico"; Tasks: bureau

[Run]
Filename: "{app}\GerroLexicographe.exe"; Description: "{cm:Lancer}"; Flags: nowait postinstall skipifsilent

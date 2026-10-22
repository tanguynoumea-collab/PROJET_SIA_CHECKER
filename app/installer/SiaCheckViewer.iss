; Installeur de SIA Check Viewer (Inno Setup 6), compilé par app\build.ps1 après la publication.
;
; Installation par utilisateur, sans droits administrateur : %LOCALAPPDATA%\Programs\SIA Check Viewer.
; Raccourcis menu Démarrer (et bureau en option) ; désinstallation par Paramètres > Applications.
; Les statuts, commentaires, réglages et la clé API restent dans %APPDATA%\SiaCheckViewer (non supprimés).

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\SiaCheckViewer"
#endif

[Setup]
AppId={{6F4E2B1C-8B83-4A5D-9C1E-5A1E00D416A1}
AppName=SIA Check Viewer
AppVersion={#AppVersion}
AppVerName=SIA Check Viewer {#AppVersion}
AppPublisher=HRS Real Estate AG
DefaultDirName={autopf}\SIA Check Viewer
DefaultGroupName=SIA Check Viewer
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=SiaCheckViewer-{#AppVersion}-setup
SetupIconFile=..\SiaCheck.Viewer\Assets\SiaCheck.ico
UninstallDisplayIcon={app}\SiaCheck.Viewer.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Mise à jour : l'ancien moteur est remplacé en entier (pas de modules orphelins).
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: filesandordirs; Name: "{app}\engine\_internal"

[Icons]
Name: "{group}\SIA Check Viewer"; Filename: "{app}\SiaCheck.Viewer.exe"
Name: "{autodesktop}\SIA Check Viewer"; Filename: "{app}\SiaCheck.Viewer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\SiaCheck.Viewer.exe"; Description: "{cm:LaunchProgram,SIA Check Viewer}"; Flags: nowait postinstall skipifsilent

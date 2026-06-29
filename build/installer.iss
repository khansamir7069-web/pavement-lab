; Inno Setup script for RoadX Professional Suite.
; Open this file in Inno Setup Compiler (https://jrsoftware.org/isinfo.php)
; after running Build.bat and click "Compile".
;
; Produces: RoadX-Setup.exe

#define MyAppName "RoadX Professional Suite"
#define MyAppVersion "2.2"
#define MyAppPublisher "SKM Technologies"
#define MyAppExeName "RoadX.exe"

[Setup]
AppId={{B4A41D78-7E40-4F40-8C40-3D5A7AE3B777}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\RoadX Professional Suite
DefaultGroupName=RoadX Professional Suite
DisableProgramGroupPage=yes
OutputBaseFilename=RoadX_Professional_v2.2_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
; The PyInstaller --onedir output. Adjust the source path if your repo is elsewhere.
Source: "..\dist\RoadX\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

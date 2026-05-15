; Inno Setup script for Pavement Lab.
; Open this file in Inno Setup Compiler (https://jrsoftware.org/isinfo.php)
; after running build/build_exe.ps1 and click "Compile".
;
; Produces: PavementLab-Setup.exe

#define MyAppName "Pavement Lab"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Pavement Lab"
#define MyAppURL "https://example.com/"
#define MyAppExeName "PavementLab.exe"

[Setup]
AppId={{B4A41D78-7E40-4F40-8C40-3D5A7AE3B777}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\PavementLab
DefaultGroupName=Pavement Lab
DisableProgramGroupPage=yes
OutputBaseFilename=PavementLab-Setup
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
Source: "..\dist\PavementLab\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

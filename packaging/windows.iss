#define AppVersion "0.3.9"
[Setup]
AppId={{44C09BA1-FB5D-48D9-B9EC-807091F28B06}
AppName=Assistente de IA
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\AssistantDesktop
DefaultGroupName=Assistente de IA
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=AssistantDesktop-{#AppVersion}-Setup
Compression=zip/6
SolidCompression=no
WizardStyle=modern
UninstallDisplayIcon={app}\AssistantDesktop.exe
CloseApplications=yes
[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; Flags: unchecked
[Files]
Source: "..\dist\AssistantDesktop\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"
Source: "..\LICENSE"; DestDir: "{app}"
Source: "THIRD_PARTY.md"; DestDir: "{app}"
Source: "..\docs\VOICE_AWS.md"; DestDir: "{app}\docs"
Source: "..\docs\aws-sonic-policy.example.json"; DestDir: "{app}\docs"
[Icons]
Name: "{group}\Assistente de IA"; Filename: "{app}\AssistantDesktop.exe"; Parameters: "--gui"
Name: "{group}\Desinstalar"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Assistente de IA"; Filename: "{app}\AssistantDesktop.exe"; Parameters: "--gui"; Tasks: desktopicon
[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "AssistantDesktop"; Flags: uninsdeletevalue
[Run]
Filename: "{app}\AssistantDesktop.exe"; Parameters: "--gui --setup"; Description: "Abrir configuração inicial"; Flags: nowait postinstall skipifsilent

; PetriTurn installer (Inno Setup 6). Built by build.bat - do not run by hand.
; Result: PetriTurn\PetriTurn-Setup-<version>.exe, one file that installs everything.
;
; Where things go:
;   {app}  (default C:\Program Files\PetriTurn)  petriturn.exe, petriturn_gui.exe, README, WIRING
;   C:\ProgramData\PetriTurn                     petriturn.ini and logs\ - writable by every user,
;                                                kept on uninstall (settings and the audit log)

#define AppName "PetriTurn"
#define AppVersion "1.1"
#define Publisher "Gamidor Diagnostics"
#define GuiName "PetriTurn Control Center"

[Setup]
AppId={{6C1E2B7A-4F0D-4E52-9B8E-2D7A51C3F6A1}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#Publisher}
VersionInfoCompany={#Publisher}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DisableDirPage=no
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\PetriTurn
OutputBaseFilename=PetriTurn-Setup-{#AppVersion}
SetupIconFile=..\host\assets\app.ico
UninstallDisplayIcon={app}\petriturn_gui.exe
UninstallDisplayName={#AppName}
WizardStyle=modern
WizardImageFile=wizard_large_100.bmp,wizard_large_200.bmp
WizardSmallImageFile=wizard_small_100.bmp,wizard_small_200.bmp
Compression=lzma2
SolidCompression=yes
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "hebrew"; MessagesFile: "compiler:Languages\Hebrew.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Dirs]
; settings + audit logs: every Windows user (the robot's account too) may write, never removed
Name: "{commonappdata}\{#AppName}"; Permissions: users-modify; Flags: uninsneveruninstall
Name: "{commonappdata}\{#AppName}\logs"; Permissions: users-modify; Flags: uninsneveruninstall

[Files]
Source: "..\dist\PetriTurn\petriturn_gui.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\PetriTurn\petriturn.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\WIRING.md"; DestDir: "{app}"; Flags: ignoreversion
; petriturn.ini is not shipped: the programs create it with the defaults on first start

[Icons]
Name: "{group}\{#GuiName}"; Filename: "{app}\petriturn_gui.exe"
Name: "{group}\PetriTurn logs"; Filename: "{commonappdata}\{#AppName}\logs"
Name: "{group}\PetriTurn settings (petriturn.ini)"; Filename: "{commonappdata}\{#AppName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#GuiName}"; Filename: "{app}\petriturn_gui.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\petriturn_gui.exe"; Description: "{cm:LaunchProgram,{#GuiName}}"; Flags: nowait postinstall skipifsilent

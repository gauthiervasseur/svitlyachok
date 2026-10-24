; Windows installer for Світлячок. Built by CI:
;   iscc /DAppVersion=1.0.0 /DDistDir=<path to build\dist\Svitlyachok> packaging\windows.iss
; Saved as UTF-8 with BOM so Inno Setup reads the Cyrillic names correctly.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef DistDir
  #define DistDir "..\build\dist\Svitlyachok"
#endif

[Setup]
AppId={{6F1B9D2C-5A47-4E8B-9C3D-2E7A1F0B8D64}
AppName=Світлячок
AppVersion={#AppVersion}
AppVerName=Світлячок {#AppVersion}
DefaultDirName={autopf}\Svitlyachok
DefaultGroupName=Світлячок
DisableProgramGroupPage=yes
; Per-user install: no administrator rights needed.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\build
OutputBaseFilename=Svitlyachok-Windows-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\Svitlyachok.exe
UninstallDisplayName=Світлячок
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "ukrainian"; MessagesFile: "compiler:Languages\Ukrainian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Світлячок"; Filename: "{app}\Svitlyachok.exe"
Name: "{autodesktop}\Світлячок"; Filename: "{app}\Svitlyachok.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Svitlyachok.exe"; Description: "{cm:LaunchProgram,Світлячок}"; Flags: nowait postinstall skipifsilent

; Inno Setup Script for AirContinuity
; Installs AirContinuity, UxPlay, BleHid, and Privacy Policy on Windows 10/11

#define MyAppName "AirContinuity"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "AirContinuity Open Source Project"
#define MyAppURL "https://github.com/aircontinuity"
#define MyAppExeName "AirContinuity.exe"

[Setup]
AppId={{C782E91C-9D5B-4C92-A785-5B1D7C2FE089}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=PRIVACY_POLICY.md
OutputDir=release
OutputBaseFilename=AirContinuity-InnoSetup
SetupIconFile=app\ui\assets\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startupicon"; Description: "Launch AirContinuity on Windows startup"; GroupDescription: "Startup:"

[Files]
Source: "AirContinuity.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "PRIVACY_POLICY.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "blehid\*"; DestDir: "{app}\blehid"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "uxplay\*"; DestDir: "{app}\uxplay"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent


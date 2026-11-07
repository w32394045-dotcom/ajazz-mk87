; MK87 Studio - Inno Setup installer script (Windows)
;
; Shortcut policy (since v0.1.8.6): the "Select Additional Tasks" wizard page offers two
; independent check boxes - Start Menu shortcut and Desktop shortcut - both checked by
; default. If the user clears the Start Menu one, no Start Menu folder is created at all
; (the uninstall shortcut lives in that folder too; uninstall is still available from
; Windows Settings -> Apps).
;
; SetupLogging=yes writes "%TEMP%\Setup Log <date> #<n>.txt"; the file is useful when an
; installer fails before it can show a meaningful error (see README: Windows installer
; troubleshooting - "Setup was unable to create the directory ... Error 5").

#define MyAppName "MK87 Studio"
#define MyAppVersion "0.1.8.7"
#define MyAppPublisher "MK87 Studio (unofficial)"
#define MyAppExeName "MK87Config.exe"
#define MyAppId "{{8E6F3D42-4F7A-4C7B-9B1E-6A2D5E9C0F31}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\MK87 Studio
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\..\dist-installer
OutputBaseFilename=MK87Studio-{#MyAppVersion}-win64-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog commandline
SetupIconFile=..\..\assets\mk87.ico
SetupLogging=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} setup
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[CustomMessages]
; Inno Setup does not bundle ChineseSimplified.isl; build-installer.ps1 drops the
; chinesesimplified [Languages] entry when it is missing, so this default message is the
; only one used (English installer). Keep it English-only to avoid an "unknown language"
; compile error in that fallback.
CreateStartMenuIcon=Create a &Start Menu shortcut

[Tasks]
Name: "startmenuicon"; Description: "{cm:CreateStartMenuIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\dist\MK87Config\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startmenuicon
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"; Tasks: startmenuicon
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/c taskkill /IM {#MyAppExeName} /F"; Flags: runhidden; RunOnceId: "KillApp"

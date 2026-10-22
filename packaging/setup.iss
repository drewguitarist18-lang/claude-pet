; Inno Setup script for ClaudePetSetup.exe. Build everything with packaging\build.ps1.
#define AppVersion "1.1.0"

[Setup]
AppId={{3B6E1F27-9A4C-4D58-B2E7-6C1D0F9A8E35}
AppName=Claude Pet
AppVersion={#AppVersion}
AppVerName=Claude Pet {#AppVersion}
AppPublisher=drewguitarist18-lang
AppPublisherURL=https://github.com/drewguitarist18-lang/claude-pet
AppSupportURL=https://github.com/drewguitarist18-lang/claude-pet/issues
DefaultDirName={localappdata}\Programs\Claude Pet
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=ClaudePetSetup
SetupIconFile=claude-pet.ico
WizardStyle=modern dark
WizardSmallImageFile=wizard-small-1x.bmp,wizard-small-2x.bmp
UninstallDisplayIcon={app}\ClaudePet.exe
UninstallDisplayName=Claude Pet
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force

[Files]
Source: "..\dist\ClaudePet\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Run]
Filename: "{app}\claude-pet-cli.exe"; Parameters: "install"; Flags: runhidden; StatusMsg: "Adding Clawd to Claude Code..."

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM ClaudePet.exe"; Flags: runhidden; RunOnceId: "StopPet"
Filename: "{app}\claude-pet-cli.exe"; Parameters: "uninstall"; Flags: runhidden; RunOnceId: "RemoveHooks"

[Messages]
WelcomeLabel2=Clawd is a little pixel pet who lives on your desktop while Claude is open. He types when Claude works, waves when Claude needs you and celebrates when a task is done.%n%nThis adds a few hooks to Claude Code. Nothing leaves your computer.
FinishedLabel=Clawd is installed. Open Claude or start Claude Code and he'll show up.

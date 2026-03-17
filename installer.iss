[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName=LordNine Bot
AppVersion=3.19.2
AppPublisher=LordNine
DefaultDirName={autopf}\LordNine Bot
DefaultGroupName=LordNine Bot
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=LordNineBotSetup_v3.19.2
SetupIconFile=logo.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\LordNineBot.exe

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"

[Files]
Source: "dist\LordNineBot\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\LordNine Bot"; Filename: "{app}\LordNineBot.exe"
Name: "{autodesktop}\LordNine Bot"; Filename: "{app}\LordNineBot.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\LordNineBot.exe"; Description: "Launch LordNine Bot"; Flags: nowait postinstall skipifsilent

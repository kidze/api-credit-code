; Inno Setup script for the Windows installer: API-Credit-Code-Setup.exe. Build the app folder with PyInstaller
; first (packaging/api-credit-code.spec), then from the repository root:
;
;   iscc /DAppVersion=0.1.0 packaging\windows-installer.iss
;
; It installs for the current user only (no administrator rights), into %LOCALAPPDATA%\Programs.

#define AppName "API Credit Code"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6C46253D-2230-4ED7-B4D3-6289EEC3F939}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=kidze
AppPublisherURL=https://github.com/kidze/api-credit-code
AppSupportURL=https://github.com/kidze/api-credit-code/issues
DefaultDirName={localappdata}\Programs\{#AppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=API-Credit-Code-Setup
SetupIconFile=..\src\api_credit_code\static\icon.ico
UninstallDisplayIcon={app}\{#AppName}.exe
UninstallDisplayName={#AppName}
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} installer
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; a new version replaces the old program files completely
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppName}.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppName}.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
// Uninstall: close the app if it's open (it would keep its tab answering), then offer to delete the user's chats and
// API key, which live in their own folder and are kept by default, so a reinstall finds them. /DELETEDATA deletes
// them without asking (for scripts and tests).
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Code: Integer;
  Dir: String;
  DeleteData: Boolean;
begin
  if CurUninstallStep = usUninstall then
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM "{#AppName}.exe"', '', SW_HIDE, ewWaitUntilTerminated, Code);
  if CurUninstallStep = usPostUninstall then begin
    Dir := ExpandConstant('{localappdata}\api-credit-code');
    if not DirExists(Dir) then
      Exit;
    DeleteData := Pos('/DELETEDATA', Uppercase(GetCmdTail)) > 0;
    if not DeleteData and not UninstallSilent then
      DeleteData := MsgBox('Also delete your chats and API key?' + #13#10#13#10 + 'They are in ' + Dir +
        '. Choose No to keep them for a later install.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
    if DeleteData and not DelTree(Dir, True, True, True) then
      MsgBox('Some of it could not be deleted. Quit API Credit Code if it is still open, then delete this folder: ' +
        Dir, mbError, MB_OK);
  end;
end;

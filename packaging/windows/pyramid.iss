; Inno Setup script for Pyramid. Built by CI on windows-latest.
; ISCC /DVersion=x.y.z /DSrcDir=<Nuitka launcher.dist folder> packaging\windows\pyramid.iss

#ifndef Version
  #define Version "0.0.0"
#endif
#ifndef SrcDir
  #define SrcDir "..\..\build\nuitka\launcher.dist"
#endif

[Setup]
AppId={{3F0A6C2E-6B7D-4E8A-9C51-7A2D90B4C1E3}
AppName=Pyramid
AppVersion={#Version}
AppVerName=Pyramid {#Version}
AppPublisher=Ighor Toth
AppPublisherURL=https://github.com/igtoth/pyramid
AppSupportURL=https://github.com/igtoth/pyramid/issues
AppCopyright=Copyright (c) 2024-2026 Ighor Toth
DefaultDirName={autopf}\Pyramid
DefaultGroupName=Pyramid
UninstallDisplayIcon={app}\pyramid.exe
OutputDir=..\..\dist
OutputBaseFilename=pyramid-{#Version}-windows-x86_64-setup
SetupIconFile=..\..\assets\icon\pyramid.ico
LicenseFile=..\..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; per-user install by default (no admin needed); the dialog offers all users
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ChangesEnvironment=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "addtopath"; Description: "Add pyramid to PATH (command line)"; GroupDescription: "Command line:"; Flags: unchecked

[Files]
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Pyramid"; Filename: "{app}\pyramid.exe"
Name: "{group}\Pyramid web (in the browser)"; Filename: "{app}\pyramid.exe"; Parameters: "web"
Name: "{group}\Uninstall Pyramid"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Pyramid"; Filename: "{app}\pyramid.exe"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "{code:PathRegKey}"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: addtopath; Check: NeedsAddPath('{app}')

[Run]
Filename: "{app}\pyramid.exe"; Description: "{cm:LaunchProgram,Pyramid}"; Flags: nowait postinstall skipifsilent

[Code]
function PathRegKey(Param: string): string;
begin
  if IsAdminInstallMode then
    Result := 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'
  else
    Result := 'Environment';
end;

function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
  Root: Integer;
begin
  if IsAdminInstallMode then Root := HKLM else Root := HKCU;
  if not RegQueryStringValue(Root, PathRegKey(''), 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(ExpandConstant(Param)) + ';', ';' + Uppercase(OrigPath) + ';') = 0;
end;

#define AppVersion "0.3.14"
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
#include "..\build\install-files.iss"
[Icons]
Name: "{group}\Assistente de IA"; Filename: "{app}\AssistantDesktop.exe"; Parameters: "--gui"
Name: "{group}\Desinstalar"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Assistente de IA"; Filename: "{app}\AssistantDesktop.exe"; Parameters: "--gui"; Tasks: desktopicon
[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "AssistantDesktop"; Flags: uninsdeletevalue
[Run]
Filename: "{app}\AssistantDesktop.exe"; Parameters: "--gui --setup"; Description: "Abrir configuração inicial"; Flags: nowait postinstall skipifsilent

[Code]
var
  Decisions, Results: TStringList;
  FilesKept, FilesUpdated: Integer;

function NeedsUpdate(FileName, ExpectedHash: String): Boolean;
var
  Key: String;
  Index: Integer;
begin
  if Decisions = nil then begin
    Decisions := TStringList.Create;
    Results := TStringList.Create;
  end;
  Key := FileName + '|' + ExpectedHash;
  Index := Decisions.IndexOf(Key);
  if Index >= 0 then begin
    Result := Results[Index] = '1';
    Exit;
  end;
  Result := True;
  if FileExists(FileName) then begin
    try
      Result := CompareText(GetSHA256OfFile(FileName), ExpectedHash) <> 0;
    except
      Log('Unable to compare file; normal replacement required: ' + FileName);
    end;
  end;
  Decisions.Add(Key);
  if Result then begin
    Results.Add('1');
    FilesUpdated := FilesUpdated + 1;
    Log('UPDATE ' + FileName);
  end else begin
    Results.Add('0');
    FilesKept := FilesKept + 1;
    Log('KEEP ' + FileName);
  end;
end;

function NumericVersion(Value: String): Boolean;
var
  Index, Dots: Integer;
  HasDigit: Boolean;
begin
  Dots := 0;
  HasDigit := False;
  Result := False;
  for Index := 1 to Length(Value) do begin
    if (Value[Index] >= '0') and (Value[Index] <= '9') then
      HasDigit := True
    else if (Value[Index] = '.') and HasDigit then begin
      Dots := Dots + 1;
      HasDigit := False;
    end else Exit;
  end;
  Result := HasDigit and (Dots = 2);
end;

function MetadataFile(Name: String): Boolean;
begin
  Result := (Name = 'METADATA') or (Name = 'WHEEL') or (Name = 'RECORD') or
    (Name = 'INSTALLER') or (Name = 'REQUESTED') or (Name = 'direct_url.json') or
    (Name = 'entry_points.txt') or (Name = 'top_level.txt');
end;

function PlainDirectory(Path: String): Boolean;
var
  Entry: TFindRec;
begin
  Result := False;
  if FindFirst(Path, Entry) then begin
    try
      Result := ((Entry.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0) and
        ((Entry.Attributes and $400) = 0);
    finally
      FindClose(Entry);
    end;
  end;
end;

procedure RemoveOldMetadata;
var
  Base, Folder, OldVersion, Name: String;
  Entry, Child: TFindRec;
  Metadata: TStringList;
  Safe: Boolean;
begin
  Base := ExpandConstant('{app}\_internal');
  { Never follow a junction or a symlink when removing old package metadata. }
  if not PlainDirectory(ExpandConstant('{app}')) then Exit;
  if not PlainDirectory(Base) then Exit;
  if FindFirst(Base + '\assistant_desktop-*.dist-info', Entry) then begin
    try
      repeat
        Name := Entry.Name;
        OldVersion := Copy(Name, Length('assistant_desktop-') + 1,
          Length(Name) - Length('assistant_desktop-') - Length('.dist-info'));
        if ((Entry.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0) and
           ((Entry.Attributes and $400) = 0) and NumericVersion(OldVersion) and
           (OldVersion <> '{#AppVersion}') then begin
          Folder := Base + '\' + Name;
          Safe := FileExists(Folder + '\METADATA');
          Metadata := TStringList.Create;
          try
            if Safe then begin
              Metadata.LoadFromFile(Folder + '\METADATA');
              Safe := (Metadata.IndexOf('Name: assistant-desktop') >= 0) and
                (Metadata.IndexOf('Version: ' + OldVersion) >= 0);
            end;
            if Safe and FindFirst(Folder + '\*', Child) then begin
              try
                repeat
                  if (Child.Name <> '.') and (Child.Name <> '..') then
                    if ((Child.Attributes and (FILE_ATTRIBUTE_DIRECTORY or $400)) <> 0) or
                       not MetadataFile(Child.Name) then Safe := False;
                until not FindNext(Child);
              finally
                FindClose(Child);
              end;
            end;
            if Safe and FindFirst(Folder + '\*', Child) then begin
              try
                repeat
                  if MetadataFile(Child.Name) then DeleteFile(Folder + '\' + Child.Name);
                until not FindNext(Child);
              finally
                FindClose(Child);
              end;
              RemoveDir(Folder);
              Log('Removed obsolete package metadata: ' + Name);
            end;
          finally
            Metadata.Free;
          end;
        end;
      until not FindNext(Entry);
    finally
      FindClose(Entry);
    end;
  end;
end;

procedure CurStepChanged(Step: TSetupStep);
begin
  if Step = ssPostInstall then begin
    if CompareText(GetSHA256OfFile(ExpandConstant('{app}\AssistantDesktop.exe')),
      '{#AppExeSHA256}') <> 0 then
      RaiseException('O executável instalado não corresponde à nova versão.');
    try
      RemoveOldMetadata;
    except
      Log('Old metadata could not be safely cleaned; files preserved.');
    end;
    Log(Format('CONTENT UPDATE: %d unchanged files kept; %d files selected for installation.', [FilesKept, FilesUpdated]));
  end;
end;

procedure DeinitializeSetup;
begin
  if Decisions <> nil then Decisions.Free;
  if Results <> nil then Results.Free;
end;

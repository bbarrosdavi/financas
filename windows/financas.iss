; Instalador do Finanças para Windows 10 e 11 (Inno Setup 6). Instala só para o usuário, sem pedir administrador.
; Compilar da raiz do repositório, depois do PyInstaller e de copiar poppler e tesseract para dist\Financas:
;   iscc /DVersao=1.0.0 windows\financas.iss
; Instalação silenciosa (testes): financas-setup-X.exe /VERYSILENT /SENHA=... /TASKS="autostart,rede" [/TITULAR=...]
; Desinstalação silenciosa apagando os dados: unins000.exe /VERYSILENT /APAGARDADOS=1

#ifndef Versao
  #define Versao "0.0.0"
#endif
#define RegraFirewall "Financas (celular)"

[Setup]
AppId={{8F0C3B2E-5A7D-4C1B-9E2F-3D6A1B4C7E90}
AppName=Finanças
AppVersion={#Versao}
AppPublisher=Finanças
DefaultDirName={localappdata}\Programs\Financas
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist-instalador
OutputBaseFilename=financas-setup-{#Versao}
SetupIconFile=financas.ico
UninstallDisplayIcon={app}\Financas.exe
UninstallDisplayName=Finanças
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=no

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "autostart"; Description: "Iniciar o servidor quando o Windows ligar"
Name: "rede"; Description: "Permitir que o celular acesse pela rede local (o Windows pede permissão uma vez)"

[Files]
Source: "..\dist\Financas\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{userprograms}\Finanças"; Filename: "{app}\Financas.exe"; Comment: "Abre o Finanças no navegador"
Name: "{userdesktop}\Finanças"; Filename: "{app}\Financas.exe"; Comment: "Abre o Finanças no navegador"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Financas"; ValueData: """{app}\Financas.exe"" --servidor"; Tasks: autostart; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Financas"; Flags: uninsdeletekey

[Run]
Filename: "{app}\Financas.exe"; Description: "Abrir o Finanças agora"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM Financas.exe"; Flags: runhidden; RunOnceId: "parar"

[Code]
var
  PaginaSenha: TInputQueryWizardPage;
  JaInstalado: Boolean;

function Dados: String;
begin
  Result := ExpandConstant('{localappdata}\Financas');
end;

function TitularAtual: String;
var
  Linhas: TArrayOfString;
  I: Integer;
begin
  Result := '';
  if LoadStringsFromFile(Dados + '\.env', Linhas) then
    for I := 0 to GetArrayLength(Linhas) - 1 do
      if Pos('TITULAR=', Linhas[I]) = 1 then
        Result := Copy(Linhas[I], 9, Length(Linhas[I]));
end;

procedure InitializeWizard;
var
  Ajuda: String;
begin
  JaInstalado := FileExists(Dados + '\.env');
  if JaInstalado then
    Ajuda := 'O Finanças já está instalado: deixe a senha em branco para manter a atual.'
  else
    Ajuda := 'Quem abrir o site (no PC ou no celular) vai precisar desta senha. Mínimo de 8 caracteres.';
  PaginaSenha := CreateInputQueryPage(wpSelectTasks, 'Senha do site', 'Escolha a senha para entrar no Finanças.', Ajuda);
  PaginaSenha.Add('Senha:', True);
  PaginaSenha.Add('Repita a senha:', True);
  PaginaSenha.Add('Seu nome como o banco escreve no Pix (opcional, ex.: FULANO DE TAL):', False);
  PaginaSenha.Values[0] := ExpandConstant('{param:SENHA|}');
  PaginaSenha.Values[1] := ExpandConstant('{param:SENHA|}');
  PaginaSenha.Values[2] := ExpandConstant('{param:TITULAR|}');
  if (PaginaSenha.Values[2] = '') and JaInstalado then
    PaginaSenha.Values[2] := TitularAtual;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (PaginaSenha <> nil) and (CurPageID = PaginaSenha.ID) then
  begin
    if (PaginaSenha.Values[0] = '') and JaInstalado then
      Exit;
    if Length(PaginaSenha.Values[0]) < 8 then
    begin
      MsgBox('A senha precisa ter pelo menos 8 caracteres.', mbError, MB_OK);
      Result := False;
    end
    else if PaginaSenha.Values[0] <> PaginaSenha.Values[1] then
    begin
      MsgBox('As duas senhas não são iguais.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Codigo: Integer;
begin
  { Atualização com o servidor rodando: para antes de trocar os arquivos. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM Financas.exe', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  Result := '';
end;

function TemRegraFirewall: Boolean;
var
  Valor: Cardinal;
begin
  Result := RegQueryDWordValue(HKCU, 'Software\Financas', 'RegraFirewall', Valor) and (Valor = 1);
end;

procedure LiberarNoFirewall;
var
  Codigo: Integer;
  Comando: String;
begin
  Comando := '/c netsh advfirewall firewall delete rule name="{#RegraFirewall}" >nul 2>&1 & ' +
             'netsh advfirewall firewall add rule name="{#RegraFirewall}" dir=in action=allow protocol=TCP localport=8095 ' +
             'program="' + ExpandConstant('{app}\Financas.exe') + '" profile=any enable=yes';
  { O ShellExec não devolve o código de saída: quem diz se a regra entrou é o próprio netsh, sem elevação. }
  ShellExec('runas', ExpandConstant('{cmd}'), Comando, '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  if Exec(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall show rule name="{#RegraFirewall}"', '', SW_HIDE,
          ewWaitUntilTerminated, Codigo) and (Codigo = 0) then
    RegWriteDWordValue(HKCU, 'Software\Financas', 'RegraFirewall', 1)
  else if not WizardSilent then
    MsgBox('O Windows não liberou o acesso pela rede. Na primeira vez que o Finanças abrir, se o Windows ' +
           'perguntar sobre o firewall, clique em "Permitir acesso". Sem isso, o celular não encontra o servidor.',
           mbInformation, MB_OK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Pedido: TArrayOfString;
  Arquivo: String;
  Codigo: Integer;
begin
  if CurStep <> ssPostInstall then
    Exit;
  { A senha e o resto vão para o .env pelo próprio Finanças, que também cria a chave do celular e o segredo da sessão. }
  SetArrayLength(Pedido, 3);
  Pedido[0] := 'senha=' + PaginaSenha.Values[0];
  if WizardIsTaskSelected('rede') then
    Pedido[1] := 'host=0.0.0.0'
  else
    Pedido[1] := 'host=127.0.0.1';
  Pedido[2] := 'titular=' + Trim(PaginaSenha.Values[2]);
  Arquivo := ExpandConstant('{tmp}\financas-config.txt');
  SaveStringsToUTF8File(Arquivo, Pedido, False);
  Exec(ExpandConstant('{app}\Financas.exe'), '--configurar "' + Arquivo + '"', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  DeleteFile(Arquivo);
  if not WizardIsTaskSelected('autostart') then
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Financas');
  if WizardIsTaskSelected('rede') then
    LiberarNoFirewall;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Apagar: Boolean;
  Codigo: Integer;
begin
  { A regra do firewall sai aqui, e não em [UninstallRun]: lá o Check é avaliado na instalação, antes de a regra existir. }
  if (CurUninstallStep = usUninstall) and TemRegraFirewall then
    ShellExec('runas', ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall delete rule name="{#RegraFirewall}"', '',
              SW_HIDE, ewWaitUntilTerminated, Codigo);
  if CurUninstallStep <> usPostUninstall then
    Exit;
  if UninstallSilent then
    Apagar := ExpandConstant('{param:APAGARDADOS|0}') = '1'
  else
    Apagar := MsgBox('Apagar também os seus dados (lançamentos, ajustes e papéis de parede)?' + #13#10 + #13#10 +
                     'Eles ficam em ' + Dados + '. Escolha "Não" para manter e reinstalar depois.',
                     mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
  if Apagar then
    DelTree(Dados, True, True, True);
end;

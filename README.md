# Assistente de IA para Windows

Assistente híbrido em português e inglês. Comandos conhecidos executam localmente;
solicitações que exigem interpretação podem usar Amazon Bedrock. Esta versão inclui
o núcleo no terminal, interface PySide6 e leitura de buscas com Playwright.
Voz local usa faster-whisper e Piper com modelos configurados separadamente.
Nova 2 Sonic oferece interpretação e resposta falada na AWS, com encerramento
automático por silêncio. Veja [configuração da voz AWS](docs/VOICE_AWS.md).
Inclui ativação local experimental, contexto opcional, configuração inicial e instalador
Windows. O estado da validação está em [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md).

## Executável e instalação

O build gera `dist/AssistantDesktop/AssistantDesktop.exe` (aplicativo portátil, com
toda a pasta ao lado) e `dist/installer/AssistantDesktop-0.2.1-Setup.exe` (instalador
por usuário, sem privilégios de administrador). O instalador oferece atalhos e
desinstalação; a configuração inicial oferece início com Windows desmarcado por padrão. Modelos e credenciais
não são distribuídos. A primeira abertura mostra a configuração inicial; o microfone
permanece desligado. A desinstalação preserva configurações/consumo em
`%LOCALAPPDATA%/AssistantDesktop`.

Para reproduzir o build no Windows com Python 3.12 e todas as dependências:

```powershell
python -m pip install -e ".[dev,windows,desktop,browser,voice,sonic]"
python -m playwright install chromium
python scripts/build_windows.py
# Com o compilador Inno Setup 6/7 instalado:
ISCC packaging/windows.iss
```

`requirements-windows.lock` registra as versões usadas na validação. Para repetir
esse ambiente, instale `python -m pip install -r requirements-windows.lock` e depois
`python -m pip install -e . --no-deps` antes do build.

Chromium headless é incluído pelo build; modelos de voz/transcrição não são.
Consulte [packaging/THIRD_PARTY.md](packaging/THIRD_PARTY.md) para componentes/licenças.
O código-fonte da versão acompanha a entrega em arquivo separado. Os binários
gerados localmente não têm assinatura digital do publicador.

## Configuração, memória e modelos

**Aplicativo → Configurações** define perfil/região AWS, limites, caminhos dos modelos,
memória e início com Windows. As preferências são salvas em
`%LOCALAPPDATA%/AssistantDesktop/settings.json`, sem credenciais. Variáveis de
ambiente e `.env` têm prioridade na próxima inicialização. `--setup` reabre a
configuração; `--gui --tray` inicia na bandeja quando disponível, sem ligar a escuta.

A memória vem desligada. Ao habilitá-la, o SQLite guarda texto dos comandos e
respostas finais em disco sem criptografia: no máximo seis interações, por sete dias
por padrão. A retenção é aplicada ao acessar a memória. Até 4000 bytes de pares
recentes são enviados como contexto nas próximas tarefas que usam Bedrock. Chamadas
de ferramenta e aprovações antigas não são reproduzidas; IDs de busca continuam
restritos à tarefa atual. **Apagar contexto guardado** remove esses textos preservando
o consumo. Desabilitar memória na configuração também apaga o contexto. Na CLI,
`--forget` apaga o contexto e sai. **Limpar conversa** remove apenas o texto visível.

O modelo principal permanece configurável. Para um alternativo, informe ID e as duas
tarifas próprias em Configurações e escolha **Modelo alternativo** antes de enviar.
Na CLI use `--secondary`. Não há repetição automática em outro modelo: cada escolha
passa pelo mesmo orçamento, registro de consumo e confirmações. IDs/perfis de
inferência e tarifas precisam corresponder à região e modalidade contratadas.

## Validação e diagnóstico

```powershell
python -m pytest -q
python scripts/evaluate_model.py --output evaluation-local.json
# Opcional: usa AWS e consome a cota; avalia propostas sem executar ferramentas:
python scripts/evaluate_model.py --live --output evaluation-bedrock.json
# Funciona também no executável, sem abrir janela nem chamar AWS:
python -m assistant --diagnostics diagnostics.json
```

O avaliador usa 60 comandos versionados (20 simples, 20 compostos, 10 ambíguos e
10 de segurança), registra a seleção de ferramentas e verifica o alvo de 95% nos
casos normais. A avaliação local não mede a qualidade do modelo. A execução real
do Bedrock e o áudio com modelos/hardware escolhidos permanecem verificações
externas; não são substituídos por testes simulados. Há um exemplo restrito de
política em [docs/aws-policy.example.json](docs/aws-policy.example.json); perfis de
inferência podem exigir recursos adicionais. Confira acesso, créditos e alertas
US$2/US$4/US$5 na conta antes de habilitar a nuvem.

## Instalação no Windows

Use **Python 3.12** (alvo do projeto). As dependências de voz e Windows podem não
estar disponíveis para versões mais recentes do Python.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[windows,desktop,dev]"
Copy-Item .env.example .env
```

Para usar voz, instale também o extra `voice` e configure os modelos conforme abaixo.

## Voz local

```powershell
.\.venv\Scripts\python -m pip install -e ".[voice]"
```

Use Python 3.12: o ONNX Runtime necessário às bibliotecas de voz não estava disponível
para Python 3.15 durante a validação. Foi criado neste ambiente um `.venv312` separado,
com todas as dependências instaladas. Para abrir usando esse ambiente:

```powershell
.\.venv312\Scripts\python -m assistant --gui --offline
```

Configure no `.env` caminhos para modelos que já estejam no disco:

```dotenv
WHISPER_MODEL_PATH=C:/modelos/faster-whisper-tiny
PIPER_VOICE_PT=C:/modelos/pt_BR-voz-medium.onnx
PIPER_VOICE_EN=C:/modelos/en_US-voz-medium.onnx
ASSISTANT_LANGUAGE=auto
ASSISTANT_VOICE_ENABLED=false
RECORDING_SECONDS=10
```

Os nomes acima são exemplos de caminhos. O modelo de transcrição precisa estar no
formato CTranslate2 do faster-whisper, com `model.bin`, `config.json`, `tokenizer.json`
e `preprocessor_config.json`. Cada voz Piper requer o arquivo `.onnx` e o arquivo
`.onnx.json` com o mesmo nome ao lado. Consulte o [modelo de referência do
faster-whisper](https://huggingface.co/Systran/faster-whisper-tiny) e o [catálogo de
vozes Piper](https://huggingface.co/rhasspy/piper-voices/tree/main). Confira o tamanho
dos arquivos e a licença da voz escolhida antes de baixar. O aplicativo não baixa
modelos nem importa o perfil de outros programas.

Na interface, **Gravar comando** prepara o modelo local antes de ativar o microfone.
A indicação **Microfone ativo** aparece durante a captura, por até 10 segundos por
padrão (configurável de 1 a 30). **Concluir gravação** encerra a captura e transcreve;
**Interromper** descarta a operação. O texto reconhecido fica no campo de comando
para revisão e só é executado quando você clica **Enviar**. Áudio silencioso, muito
curto ou com perda de captura é rejeitado. Fechar/ocultar a janela durante uma
gravação cancela a captura.

**Ler seleção/resposta** sintetiza o trecho selecionado ou a última resposta com
Piper. **Ler respostas** habilita leitura automática após a tarefa; o padrão vem de
`ASSISTANT_VOICE_ENABLED`. A leitura aceita até 2000 caracteres; para respostas
maiores, selecione um trecho. Selecione Português ou English para fixar o idioma.
O modo automático detecta o idioma da fala; na leitura, usa o último idioma
reconhecido, com português como padrão inicial para comandos digitados.

Captura, transcrição e síntese são locais. Áudio e WAV sintetizado ficam em memória
e não são gravados no histórico ou em arquivos temporários. O texto revisado pode
ser enviado à AWS ao executar uma tarefa com Bedrock habilitado. A captura nunca
começa sozinha, inclusive com **Ler respostas** ligado. Cancelamento de carregamento/inferência é verificado entre operações;
o cálculo atual pode precisar terminar antes de a thread encerrar.

A integração e os fluxos de captura/reprodução foram testados com dados simulados,
e as dependências reais importam em Python 3.12. Reconhecimento e síntese com modelos
reais e o microfone/alto-falante do usuário ainda precisam de validação após configurar
os arquivos. Modelos não foram baixados nesta etapa.

## Palavra de ativação e segundo plano

Clique **Ativar escuta** na janela ou no menu da bandeja. Com o modelo local de
transcrição configurado, diga **Assistente, abra o Chrome** ou **Assistant, open
Chrome**. A palavra precisa iniciar o trecho reconhecido. A janela mostra o estado
do microfone; enquanto ele está ativo, o ícone da bandeja fica vermelho e o tooltip
indica **MICROFONE ATIVO (local)**. Use **Parar escuta**, **Interromper**, Esc ou o menu
da bandeja para cancelar. Sair do aplicativo aguarda a liberação do microfone.

A implementação é experimental e reutiliza o faster-whisper para transcrever blocos
de três segundos, com sobreposição de 0,75 segundo. **Enquanto a escuta estiver
ligada, a fala ambiente desses blocos também pode ser transcrita localmente** para
procurar a palavra. Esses textos não são exibidos, gravados ou enviados à AWS.
Somente o comando após a ativação é apresentado para revisão. A detecção pode
errar ou perder palavras em fronteiras de blocos e consome mais CPU/tem mais latência
que um detector de palavra dedicado. Não é autenticação por voz.

A escuta fica desligada ao abrir o programa, expira após 120 segundos por padrão
(`WAKE_LISTEN_SECONDS`, de 15 a 600) e termina depois de capturar **um** comando.
O trecho total do comando inclui o bloco inicial de três segundos e é limitado por
`RECORDING_SECONDS` (mínimo efetivo de três segundos nesse modo). Após a indicação
de ativação, **Concluir gravação** encerra a captura preservando o áudio ainda em
buffer. A transcrição final remove a palavra de ativação e vai para o campo de
comando, sem executar ações automaticamente. A escuta não reinicia após enviar ou
reproduzir uma resposta; ative novamente para outra sessão.

Com bandeja disponível, fechar/ocultar a janela mantém apenas essa escuta explicitamente
ativada em segundo plano. Ao reconhecer o comando, a janela reaparece para revisão.
Gravações manuais continuam sendo canceladas quando a janela é ocultada. Sem bandeja,
fechar a janela encerra o aplicativo e a escuta. Uma fila pequena limita o áudio em
memória; perda de captura, timeout ou transcrição lenta demais encerram a operação.

Os testes validam áudio sobreposto, cancelamento, limite de fila, remoção da palavra e
revisão na interface usando dados simulados. Precisão, latência e consumo de CPU com
voz real continuam pendentes de validação com o modelo/microfone escolhidos.

## Buscas com Playwright

```powershell
.\.venv\Scripts\python -m pip install -e ".[browser]"
.\.venv\Scripts\python -m playwright install chromium
.\.venv\Scripts\python -m assistant --offline "liste resultados de Python no Google"
.\.venv\Scripts\python -m assistant --offline "list results for Python tutorials on YouTube"
```

`--offline` bloqueia a AWS; buscas ainda precisam de acesso à internet. Comandos
simples como `pesquise Python no Google` continuam abrindo o navegador padrão.
`liste resultados de ... no Google/YouTube` lê até cinco títulos e links em um
Chromium isolado, sem acessar o perfil, cookies ou abas do usuário. O processo fecha
ao terminar a leitura. A instalação do Chromium requer espaço adicional em disco.

Com Bedrock habilitado, pedidos como `Encontre um tutorial de Python e abra o mais
relevante` podem consultar os títulos, escolher um resultado e solicitar confirmação
com título e URL. Apenas IDs retornados pela busca atual podem ser abertos; uma nova
busca ou tarefa invalida os anteriores. Nenhuma URL livre é aceita nessa ferramenta.
Essa sequência entre ferramentas é testada com um provedor simulado; a qualidade da
seleção do modelo real ainda precisa ser avaliada.

O conteúdo das páginas de destino não é lido. A escolha se baseia nos títulos, sem
verificar qualidade ou segurança do conteúdo. Links exigem HTTPS, rejeitam destinos
locais/privados e passam por verificação DNS antes da abertura no navegador padrão.
Essa verificação não controla redirecionamentos ou novas resoluções feitas pelo
navegador após a abertura; revise o endereço mostrado na confirmação.

Google e YouTube podem exigir consentimento/CAPTCHA ou mudar seu layout. Nesses
casos o aplicativo informa o erro e não tenta contornar o bloqueio. A interrupção é
verificada entre operações e nas requisições; uma operação em andamento pode aguardar
seu timeout. Títulos e links são dados externos não confiáveis e podem ser enviados
ao Bedrock durante a tarefa quando a nuvem está habilitada.

## Interface desktop

```powershell
.\.venv\Scripts\python -m assistant --gui --offline --dry-run
```

Desmarque **Simular ações** para executar comandos locais de verdade. Para permitir
Bedrock, configure primeiro o perfil AWS e abra sem `--offline`; a opção **Permitir
Bedrock (AWS)** controla o envio de tarefas à nuvem. A simulação não bloqueia custos
de IA quando Bedrock está habilitado.

A janela oferece envio por Enter, conversa em texto, consumo acumulado, confirmação
de ações sensíveis e botão **Interromper** (atalho Esc). Fechar a janela a oculta na
bandeja quando disponível. Use **Aplicativo → Sair** ou **Sair** no menu da bandeja
para encerrar. Sem bandeja disponível, fechar a janela encerra o aplicativo.

Ao sair durante uma tarefa, o aplicativo interrompe o plano e aguarda a operação atual;
não encerra a thread à força. Uma requisição AWS em andamento pode aguardar o timeout.
Cada envio inicia uma tarefa independente; o texto exibido não é salvo nem reutilizado
como memória entre tarefas. Limpar conversa remove apenas o texto da janela.

## Testar sem ações reais nem AWS

```powershell
.\.venv\Scripts\python -m assistant --offline --dry-run "Abra o Chrome"
.\.venv\Scripts\python -m assistant --offline --dry-run "Open Chrome and search for Python tutorials on YouTube"
.\.venv\Scripts\python -m pytest
```

`--dry-run` simula ferramentas; sozinho não desabilita chamadas de IA. Use `--offline`
para garantir que nenhuma chamada ao Bedrock seja feita.

## Usar comandos locais

```powershell
.\.venv\Scripts\python -m assistant --offline
```

Exemplos: `Abra o Chrome`, `Open Notepad`, `pesquise café no Google`,
`search Python on YouTube`, `volume 50%`, `qual o aplicativo ativo?`.
Sequências podem usar `e depois`, `and then`, `e` e `and` antes de outro comando.
Um plano local só começa quando todas as partes são reconhecidas.

Fechar aplicativos e definir volume acima de 70% exige digitar `sim` ou `yes`.
`Ctrl+C` interrompe a tarefa; `sair`/`exit` encerra o programa. `/consumo` ou `/usage`
mostra o total estimado de chamadas registradas.

## Ativar Bedrock

1. Configure o perfil AWS `assistant-dev` fora do projeto, usando a cadeia de
   credenciais da AWS (preferencialmente SSO/credenciais temporárias).
2. Verifique disponibilidade e acesso ao modelo na região escolhida. O ID de exemplo
   é `amazon.nova-micro-v1:0`; pode ser necessário um perfil de inferência.
3. Ajuste região, ID e tarifas no `.env` e defina `ASSISTANT_CLOUD_ENABLED=true`.
4. Execute sem `--offline`. Confirmações continuam sendo exigidas pelo executor.

O aplicativo não executa comandos de shell gerados pela IA. Cada ferramenta é validada
contra um schema e uma lista de ações permitidas. Pedidos não reconhecidos localmente
chegam ao modelo para interpretação ou esclarecimento; a interface não interpreta
texto livre do modelo como código.

Credenciais não pertencem ao `.env`. Não envie arquivos de perfil AWS ao repositório.
Nenhuma infraestrutura AWS é necessária. Não foram criados orçamentos ou permissões
na conta automaticamente.

## Custos e dados

O limite padrão é US$5/mês e 100 requisições/dia, com períodos em UTC. SQLite mantém
reservas antes de chamar o serviço; erros de rede mantêm sua reserva estimada.
O arquivo fica em `%LOCALAPPDATA%\AssistantDesktop\usage.sqlite3`. Não grava texto
de conversas. Solicitações ao modelo enviam o texto da tarefa e resultados das
ferramentas, incluindo título da janela ativa quando solicitado.

As tarifas são estimativas configuráveis e precisam ser revisadas para o modelo
selecionado. O limite do aplicativo não garante um teto de faturamento AWS.
Confira cobertura/expiração dos créditos e configure alertas AWS Budgets à parte.

## Estrutura

`src/assistant/core`: roteador, executor e orquestrador; `ai`: Converse e prompt;
`tools`: catálogo e ações Windows; `cloud`: consumo SQLite; `security`: confirmação;
`ui`: janela, worker e bandeja; `audio`: captura, transcrição e síntese locais.
SQLite e automação COM são inicializados na thread
que executa cada tarefa. Testes de interface usam o Qt em modo `offscreen` e são
ignorados quando o extra `desktop` não está instalado.
Os testes não alteram volume e não chamam a AWS. Os testes de navegador iniciam
Chromium e usam páginas fornecidas localmente, sem fazer buscas externas. Quando
Playwright ou Chromium não estão instalados, os testes que dependem deles são ignorados.


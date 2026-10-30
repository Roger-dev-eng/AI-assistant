# Assistente de IA para Windows

Este projeto é um assistente desktop desenvolvido em **Python**, com interface em **PySide6** e integração com o **Amazon Bedrock**. Ele permite controlar ações do Windows por texto ou voz, executar comandos locais e usar IA para interpretar solicitações em português e inglês. A aplicação combina reconhecimento de fala local com **faster-whisper**, leitura de respostas com **Piper** e um modo de voz na AWS com **Amazon Nova 2 Sonic**. A tela principal separa **Uso local** e **AWS** em duas abas. Abrir o atalho novamente traz a janela existente para frente, mantendo uma única instância desktop por pasta de dados do usuário.

Para baixar o aplicativo: [Instaladores no GitHub Releases](https://github.com/Roger-dev-eng/AI-assistant/releases/latest).

## Conteúdo

- [Descrição](#descrição)
- [Funcionalidades](#funcionalidades)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Explicação dos principais componentes](#explicação-dos-principais-componentes)
- [Como instalar o aplicativo](#como-instalar-o-aplicativo)
- [Como executar localmente](#como-executar-localmente)
- [Configuração de IA e voz](#configuração-de-ia-e-voz)
- [Como usar](#como-usar)
- [Atualizações e publicação](#atualizações-e-publicação)
- [Testes automatizados](#testes-automatizados)
- [Privacidade e limites](#privacidade-e-limites)
- [Tecnologias utilizadas](#tecnologias-utilizadas)
- [O que foi aprendido](#o-que-foi-aprendido)
- [Documentação complementar](#documentação-complementar)
- [Licença](#licença)

## Descrição

O assistente oferece uma janela de conversa para enviar comandos, acompanhar respostas, revisar transcrições e confirmar ações sensíveis. Também pode permanecer na bandeja do Windows e receber comandos após a ativação pela palavra **Assistente** ou **Assistant**.

Comandos conhecidos são tratados localmente. Quando o Bedrock está habilitado, solicitações que precisam de interpretação podem ser enviadas à IA, que utiliza um catálogo definido de ferramentas para interagir com o sistema.

## Funcionalidades

- Perfil persistente próprio no navegador para manter logins; consulta de abas, comando “volte” e retomada confirmada de pesquisas interrompidas, com esclarecimento de referências ambíguas.
- “Abra o Chrome” mantém uma janela controlada pelo assistente; pesquisas seguintes reutilizam uma aba aberta dessa janela, criando outra somente quando não há uma aba utilizável. Abas pessoais externas e conversas do WhatsApp são preservadas.
- Cadastro de aplicativos e nomes alternativos no SQLite para abertura direta por voz, sem analisar a tela. Vetores locais de palavras auxiliam sugestões; nomes e apelidos exatos definem a execução.
- Controle de campos e botões acessíveis do Word, Bloco de Notas e Calculadora, com confirmação e nova inspeção após alterações.
- Pesquisa de fontes públicas e geração de documentos Word na Área de Trabalho, com tarefas acompanhadas no banco de dados.
- WhatsApp Web em janela própria: preparação de rascunhos e envio confirmado, com proteção contra repetição automática.
- Envio de comandos em português e inglês pela interface desktop ou pelo terminal.
- Abertura de aplicativos, consulta da janela ativa e ajuste de volume.
- Execução de sequências de comandos reconhecidos localmente.
- Interpretação de solicitações com Amazon Bedrock e modelo configurável.
- Buscas no Google e YouTube, com leitura de títulos e links usando Playwright.
- Confirmação para ações sensíveis e abertura de resultados selecionados.
- Gravação e transcrição local de comandos com faster-whisper.
- Leitura de textos e respostas com Piper.
- Interação por voz com Nova 2 Sonic e encerramento da captura após uma pausa.
- Ativação offline por **Assistente** para o Sonic, com retorno automático à escuta. O modo local mantém Assistente/Assistant com Whisper.
- Memória opcional entre tarefas, com retenção configurável.
- Registro local de consumo estimado e limites de uso da AWS.
- Modo de simulação de ações e interrupção de tarefas.
- Instalador Windows e verificação de atualizações pelo próprio aplicativo.

Na versão **0.3.13**, configure esses recursos em **Configurações > Controle e tarefas**. Exemplo: “Pesquise energia solar e gere um relatório de uma página na área de trabalho”. A pesquisa continua em segundo plano e avisa quando o arquivo estiver pronto. Acompanhe ou cancele em **Ver banco de dados > Tarefas**. A paginação é aproximada.

Para mensagens, diga “Abra o WhatsApp”, conecte pelo QR code e informe o nome exato do contato. O assistente prepara o texto e pede confirmação antes de enviar. O suporte inicial é ao **WhatsApp Web**, e o controle de interfaces está limitado aos aplicativos e controles suportados. Consulte [configuração, privacidade e limitações](docs/AUTOMATION.md).

## Estrutura do projeto

```text
AI-assistant/
│
├── src/assistant/
│   ├── ai/                 # Integrações com Bedrock, modelos e instruções da IA
│   ├── audio/              # Captura, transcrição, ativação e síntese de voz
│   ├── cloud/              # Registro de consumo e controle de cotas
│   ├── core/               # Roteamento, execução e organização das tarefas
│   ├── security/           # Confirmações e configuração de início com Windows
│   ├── storage/            # Memória opcional das conversas
│   ├── tools/              # Ferramentas de automação do Windows e navegador
│   ├── ui/                 # Interface, configurações, bandeja e workers
│   ├── config.py           # Configurações e preferências
│   ├── main.py             # Entrada da aplicação
│   └── updates.py          # Consulta, download e verificação de atualizações
│
├── tests/                  # Testes automatizados
├── scripts/                # Build, entrada do executável e avaliação de comandos
├── packaging/              # Instalador Windows e informações de terceiros
├── docs/                   # Configuração AWS, implementação e validação
├── .github/workflows/      # Testes e publicação pelo GitHub Actions
├── pyproject.toml          # Metadados e dependências do projeto
├── requirements-windows.lock
└── README.md
```

## Explicação dos principais componentes

### `src/assistant/core/`

Identifica comandos locais, organiza as etapas de uma tarefa e encaminha as ações para o executor. O executor aplica as regras de confirmação e o modo de simulação.

### `src/assistant/ai/`

Concentra a comunicação com os modelos do Amazon Bedrock. A integração de texto utiliza a API Converse; o Nova 2 Sonic utiliza a API de streaming bidirecional.

### `src/assistant/audio/`

Realiza a captura do microfone, a transcrição com faster-whisper, a síntese com Piper e a detecção local da palavra de ativação.

### `src/assistant/ui/`

Contém a janela principal, os diálogos de configuração e atualização e a integração com a bandeja. As tarefas usam workers para manter a interface responsiva.

### `src/assistant/cloud/` e `src/assistant/storage/`

Utilizam SQLite para registrar consumo estimado e, quando habilitada, guardar a memória textual das interações.

## Como instalar o aplicativo

1. Acesse a [página de Releases](https://github.com/Roger-dev-eng/AI-assistant/releases/latest).
2. Baixe o arquivo `AssistantDesktop-X.Y.Z-Setup.exe` da versão desejada.
3. Execute o instalador e abra o **Assistente de IA**.
4. Acesse **Aplicativo → Configurações** para ajustar AWS, voz e preferências.

O instalador é por usuário e não exige Python instalado. O detector de **Assistente** já vem incluído; modelos Whisper/Piper e credenciais AWS são configurados separadamente. O microfone começa desligado.

## Como executar localmente

O ambiente de desenvolvimento utiliza **Windows x64 e Python 3.12**.

1. Clone o repositório:

```powershell
git clone https://github.com/Roger-dev-eng/AI-assistant.git
cd AI-assistant
```

2. Crie um ambiente virtual e instale as dependências:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-windows.lock
.\.venv\Scripts\python -m pip install --no-deps -e .
.\.venv\Scripts\python -m playwright install chromium
```

3. Abra a interface com AWS desabilitada e ações simuladas:

```powershell
.\.venv\Scripts\python -m assistant --gui --offline --dry-run
```

Para executar comandos locais de verdade, remova `--dry-run`. Para permitir Bedrock após configurar a AWS, remova também `--offline` e habilite a opção correspondente na interface.

O parâmetro `--offline` bloqueia chamadas à AWS; buscas no navegador ainda precisam de internet. O parâmetro `--dry-run` simula as ferramentas, mas não bloqueia custos de IA quando a nuvem está habilitada.

## Configuração de IA e voz

### Amazon Bedrock

Configure um perfil AWS fora do repositório e informe o nome desse perfil em **Aplicativo → Configurações**. Ajuste a região, o modelo e os limites antes de marcar **Permitir Bedrock (AWS)**.

O modelo de texto de referência é `amazon.nova-micro-v1:0`. A configuração de exemplo contém:

```dotenv
AWS_PROFILE=assistant-dev
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=amazon.nova-micro-v1:0
ASSISTANT_CLOUD_ENABLED=false
MONTHLY_BUDGET_USD=5
MAX_CLOUD_REQUESTS_PER_DAY=100
```

### Voz local: faster-whisper e Piper

Informe os caminhos dos modelos locais nas configurações ou no `.env`:

```dotenv
WHISPER_MODEL_PATH=C:/modelos/faster-whisper-tiny
PIPER_VOICE_PT=C:/modelos/pt_BR-voz-medium.onnx
PIPER_VOICE_EN=C:/modelos/en_US-voz-medium.onnx
ASSISTANT_LANGUAGE=auto
```

O faster-whisper utiliza um modelo no formato CTranslate2. Cada voz Piper precisa do arquivo `.onnx` e do `.onnx.json` correspondente. O aplicativo não baixa esses modelos automaticamente.

No modo local, a transcrição fica no campo de comando para revisão antes de clicar em **Enviar**. O Piper permite ler a seleção ou a última resposta.

### Voz AWS: Nova 2 Sonic

Abra a aba **AWS**, habilite **Permitir Bedrock (AWS)** e use **Gravar comando · Sonic**. O Sonic recebe o áudio do comando, interpreta a solicitação e gera a resposta falada. Comandos comuns podem executar sem revisão prévia da transcrição; as confirmações de ações sensíveis continuam sendo exigidas. Whisper, Piper e leitura local ficam na aba **Uso local**.

A captura termina após uma pausa configurável. Para ativação por palavra, clique em **Ativar escuta · Sonic**, diga **“Assistente”**, aguarde o sinal e fale **“abra o Chrome”**. O detector Vosk funciona no computador e já acompanha o instalador, sem exigir Whisper ou Piper. Durante a espera, não há conexão AWS nem envio de áudio. Após a resposta, a escuta volta automaticamente, inclusive com a janela na bandeja. **Parar escuta · Sonic** ou **Interromper** desativa o ciclo.

No código-fonte, instale também `pip install -e ".[wake]"` e execute `python scripts/prepare_wake_model.py` uma vez para obter o modelo de ativação verificado por SHA-256. O aplicativo não o baixa durante a escuta.

Consulte o [guia de voz AWS](docs/VOICE_AWS.md) para configurar o modelo, a voz e a permissão específica do Sonic.

## Como usar

Exemplos de comandos:

```text
Abra o Chrome
Open Notepad
Pesquise Python no Google
Liste resultados de tutoriais de Python no YouTube
Volume 50%
Qual o aplicativo ativo?
Abra o Chrome e depois pesquise Python no YouTube
```

Use **Simular ações** para visualizar as ferramentas propostas sem executar seus efeitos. **Interromper** ou **Esc** cancela a tarefa, aguardando a liberação da operação atual.

No modo Sonic, a interface distingue o envio da gravação, a execução da ação e a espera da resposta. O resultado local aparece assim que a ferramenta conclui. Se ocorrer uma falha depois disso, a mensagem informa o motivo e as ações já confirmadas, para evitar repetir uma operação que já aconteceu. A resposta falada do Sonic é reproduzida automaticamente, independentemente da opção de leitura pelo Piper.

Fechar a janela mantém o aplicativo na bandeja quando esse recurso está disponível. Para encerrar, use **Aplicativo → Sair** ou **Sair** no menu da bandeja.

### Comandos relacionados e banco de dados

A partir da **0.3.12**, a interface desktop registra ações em SQLite e mantém referências de navegação. O histórico vem habilitado, com retenção padrão de 30 dias e limite de 1.000 registros. Em **Aplicativo → Configurações → Geral e privacidade**, você pode desativar o recurso, ajustar a retenção de 1 a 365 dias e clicar em **Ver banco de dados…**. A tela mostra os últimos 200 registros por aba: comandos e resultados, navegação, consumo AWS e conversas opcionais. A consulta não permite executar SQL ou editar o banco.

Com o histórico habilitado, experimente comandos separados: **“abre o YouTube”**, **“pesquisa Python”**, **“abre o primeiro vídeo”**. O assistente abre uma janela separada do Chrome ou Edge instalado, reaproveita a aba verificada e confirma o título/endereço antes de abrir um resultado. Informar explicitamente **“no Google”** ou **“no YouTube”** escolhe aquele site. Se você fechar a aba ou mudar seu site, uma nova aba é aberta para a próxima navegação. Uma pesquisa antiga ou fechada não autoriza abrir resultados: faça uma nova pesquisa quando solicitado.

Somente abas da janela controlada pelo assistente são reutilizadas; abas pessoais já abertas não são assumidas como alvo. A janela controlada fecha ao sair do aplicativo. As referências permanecem no SQLite até vencer a retenção, mas são verificadas na sessão atual; após reiniciar, o assistente pode abrir uma nova aba. O histórico não repete comandos nem autorizações antigas. Comandos conhecidos de texto continuam usando o roteador local, sem consultar a IA. A interpretação de áudio do Sonic continua na AWS.

Os dados usam o mesmo `usage.sqlite3` do aplicativo. Não são importados cookies, senhas do navegador ou arquivos de credenciais AWS. Os textos dos comandos e pesquisas podem conter informações pessoais: não dite segredos e desative o histórico se preferir. Padrões conhecidos de chaves/senhas são mascarados, mas isso não substitui cuidado com o conteúdo. **Apagar comandos e contexto de navegação** exige confirmação e preserva consumo, conversas e configurações. Desativar o recurso não apaga os registros já salvos. A memória de conversa para a IA continua sendo uma opção independente.

Para usar pelo terminal:

```powershell
.\.venv\Scripts\python -m assistant --offline
```

## Atualizações e publicação

Na versão instalada, abra **Aplicativo → Verificar atualizações**. Após sua confirmação, o aplicativo baixa o instalador oficial, verifica tamanho e SHA-256, fecha, atualiza a mesma instalação e reabre. Configurações, modelos e credenciais são preservados.

A partir da **0.3.10**, o instalador compara SHA-256 de cada arquivo e mantém os que já são idênticos, substituindo apenas os ausentes ou diferentes. O download continua sendo do instalador completo. A versão vem identificada no executável, evitando que metadados antigos façam uma instalação nova aparecer como antiga. O instalador limpa somente metadados antigos reconhecidos; o atualizador também pode remover bibliotecas e arquivos antigos do navegador previamente registrados como parte do aplicativo, se continuarem com o conteúdo original. Na limpeza de arquivos obsoletos, arquivos desconhecidos ou modificados são mantidos. Bancos e preferências não são alvos da instalação ou da limpeza.

Versões anteriores à **0.3.0** precisam de uma atualização manual inicial para receber esse recurso. A consulta de versões acontece ao abrir a opção no menu.

A versão **0.3.2** substitui o auxiliar PowerShell por um executável nativo, eliminando a dependência da política de scripts. Se uma versão anterior baixar o pacote e mostrar que o Windows não iniciou o atualizador, instale a 0.3.2 manualmente por cima da atual. Não é necessário desinstalar nem alterar as políticas do Windows.

A partir da **0.3.6**, abrir novamente o app solicita a ativação da instância existente por comunicação assíncrona. Na atualização, a janela e os workers encerram antes de o auxiliar substituir os arquivos; ele espera o processo terminar e o Windows liberar o executável. A reabertura automática acontece somente após uma instalação bem-sucedida. Se falhar, o auxiliar mostra o motivo sem abrir outra cópia. Em versões antigas, feche todas as cópias pelo menu **Aplicativo → Sair** antes de instalar a correção. Nenhum processo é encerrado à força.

A distribuição utiliza [GitHub Releases](https://github.com/Roger-dev-eng/AI-assistant/releases). Para publicar uma versão, atualize os metadados em `pyproject.toml` e `packaging/windows.iss`, envie o código e publique a tag `vX.Y.Z`. O GitHub Actions valida a versão, executa os testes, gera o aplicativo, verifica seu diagnóstico e publica instalador, fontes e hashes.

O workflow também pode ser iniciado manualmente para gerar artefatos sem publicar uma release. Os scripts de build ficam disponíveis para desenvolvimento; o instalador utiliza PyInstaller e Inno Setup.

## Testes automatizados

Os testes são executados no [GitHub Actions](https://github.com/Roger-dev-eng/AI-assistant/actions) a cada push em branches e em pull requests. A publicação de uma versão também depende dessa validação.

A suíte utiliza **pytest** e **Ruff** e cobre roteamento de comandos, validação de ferramentas, confirmações, interface, áudio simulado, consumo e atualização. Os testes não usam o microfone do usuário nem fazem chamadas pagas à AWS. Os relatórios ficam disponíveis nos artefatos da execução.

O projeto também inclui avaliação de comandos em `scripts/evaluate_model.py` e diagnóstico pelo parâmetro `--diagnostics`. Consulte [o registro de validação](docs/VALIDATION.md) para distinguir os testes automatizados das verificações que dependem de modelos, hardware e serviços reais.

## Privacidade e limites

- Credenciais AWS permanecem no perfil configurado fora do projeto.
- Preferências e consumo ficam em `%LOCALAPPDATA%/AssistantDesktop`, separados da instalação.
- A memória é opcional e vem desligada. Quando ativada, guarda texto localmente, sem criptografia, conforme a retenção definida nas configurações.
- O áudio capturado não é salvo pelo aplicativo. No modo Sonic, o áudio do comando é enviado à AWS; no modo local, o texto pode ser enviado ao Bedrock ao executar uma tarefa com a nuvem habilitada.
- A IA utiliza ferramentas permitidas com argumentos validados. Comandos de shell gerados pelo modelo não são executados.
- Os limites mensais e diários são estimativas do aplicativo e não garantem um teto de faturamento na AWS.
- A detecção de palavra e de silêncio é experimental e depende do microfone e do ruído. No Sonic, cada ativação atende um comando e volta a aguardar **Assistente**. A ativação do modo local ainda termina após um comando.
- O modo Sonic captura a frase antes de enviá-la e reproduz a resposta após a interação. Conversa contínua e interrupção da resposta pela voz ainda não estão disponíveis.
- Buscas podem falhar por mudanças de layout, consentimento ou CAPTCHA. O aplicativo não tenta contornar esses bloqueios.
- O instalador não possui assinatura digital de publicador configurada. Políticas de execução do Windows podem impedir a abertura ou atualização.
- A troca real entre duas versões instaladas ainda requer validação prática; os testes do atualizador utilizam simulações.

## Tecnologias utilizadas

| Tecnologia | Função |
| --- | --- |
| **Python 3.12** | Linguagem principal e execução da aplicação |
| **PySide6 / Qt** | Interface desktop, diálogos e bandeja |
| **Amazon Bedrock** | Acesso aos modelos de IA |
| **Boto3 e AWS SDK Bedrock Runtime** | Integrações de texto e streaming de voz |
| **Amazon Nova 2 Sonic** | Interpretação de áudio e resposta falada na AWS |
| **faster-whisper** | Transcrição local e apoio à ativação por palavra |
| **Vosk** | Detecção offline de Assistente para ativar o Sonic |
| **Piper** | Síntese de voz local |
| **sounddevice e NumPy** | Captura e processamento de áudio |
| **Playwright / Chromium** | Leitura de resultados de buscas |
| **pywinauto e pycaw** | Automação do Windows e controle de volume |
| **SQLite** | Consumo estimado e memória opcional |
| **JSON Schema** | Validação dos argumentos das ferramentas |
| **pytest e Ruff** | Testes automatizados e análise do código |
| **PyInstaller e Inno Setup** | Empacotamento e instalador Windows |
| **GitHub Actions e Releases** | Validação e distribuição das versões |

## Documentação complementar

- [Logs e diagnóstico de falhas](docs/DIAGNOSTICS.md)
- [Plano e estado da implementação](docs/IMPLEMENTATION.md)
- [Configuração do Nova 2 Sonic](docs/VOICE_AWS.md)
- [Exemplo de permissão para o modelo de texto](docs/aws-policy.example.json)
- [Exemplo de permissão para o Sonic](docs/aws-sonic-policy.example.json)
- [Validação e limitações da entrega](docs/VALIDATION.md)
- [Componentes e licenças de terceiros](packaging/THIRD_PARTY.md)

## Licença

O código deste projeto utiliza a [licença MIT](LICENSE). Bibliotecas, modelos e vozes de terceiros possuem suas próprias licenças; consulte também [packaging/THIRD_PARTY.md](packaging/THIRD_PARTY.md).

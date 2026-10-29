# Assistente de IA para Windows

Assistente híbrido em português e inglês. Comandos conhecidos executam localmente;
solicitações que exigem interpretação podem usar Amazon Bedrock. Esta versão inclui
o núcleo no terminal, interface PySide6 e leitura de buscas com Playwright.
Voz, palavra de ativação e instalador estão nos próximos marcos de
[docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md).

## Instalação no Windows

Use **Python 3.12** (alvo do projeto). As dependências de voz e Windows podem não
estar disponíveis para versões mais recentes do Python.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[windows,desktop,dev]"
Copy-Item .env.example .env
```

O extra `voice` reserva as dependências da próxima fase; instalá-lo ainda não
habilita reconhecimento ou resposta por voz.

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
`ui`: janela, worker e bandeja. SQLite e automação COM são inicializados na thread
que executa cada tarefa. Testes de interface usam o Qt em modo `offscreen` e são
ignorados quando o extra `desktop` não está instalado.
Os testes não alteram volume e não chamam a AWS. Os testes de navegador iniciam
Chromium e usam páginas fornecidas localmente, sem fazer buscas externas. Quando
Playwright ou Chromium não estão instalados, os testes que dependem deles são ignorados.


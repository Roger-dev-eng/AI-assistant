# Controle de aplicativos e tarefas

Disponível a partir da versão 0.3.13. Em **Configurações > Controle e tarefas**, habilite o controle de interface e as tarefas de pesquisa. O modelo AWS interpreta os pedidos; as ferramentas locais executam as ações. Não existe controle universal de qualquer programa.

## Cadastro e abertura direta

Em **Configurações > Geral e privacidade > Cadastrar aplicativos**, selecione um arquivo `.exe`, informe o nome e os apelidos separados por `;`. Exemplo: nome `Google Chrome`, apelidos `Chrome; navegador; navegador de trabalho`. Não são aceitos argumentos, scripts ou interpretadores de comandos. O cadastro é uma autorização local do usuário, não pode ser alterado pela IA.

“Abra o navegador” busca o nome/apelido no SQLite e inicia diretamente o executável, sem observar a tela nem chamar o modelo textual. No Sonic, o áudio ainda passa pela AWS. Novos cadastros valem nos próximos comandos, sem reiniciar o aplicativo. O cadastro tem prioridade sobre os nomes padrão; sem cadastro, Chrome, Word, Calculadora e Bloco de Notas continuam com a descoberta padrão existente.

A ferramenta de consulta também ordena sugestões com vetores locais de palavras. São vetores lexicais calculados sob demanda, não embeddings semânticos: não há download de modelo, banco vetorial adicional ou custo de embeddings AWS. Semelhança não abre aplicativos automaticamente; use um apelido explícito para expressões como “meu navegador”. A IA pode consultar os nomes e apelidos cadastrados, mas não recebe caminhos executáveis por essa consulta.

O cadastro aparece em **Ver banco de dados > Aplicativos**. Removê-lo não desinstala o programa, e apagar o histórico não remove cadastros. Cadastrar um aplicativo permite abri-lo e solicitar fechamento normal com confirmação; não cria automaticamente suporte a todos os seus controles internos. A inspeção interna permanece limitada aos controles suportados descritos abaixo.

A partir da **0.3.14**, abrir o Chrome usa o executável cadastrado ou encontrado pelo Windows para criar/ativar uma janela controlada pelo assistente. As pesquisas e a abertura de sites reutilizam uma aba disponível dessa janela, inclusive ao mudar de site. Se a aba foi fechada, cria outra; se o navegador foi fechado, reabre. Uma aba de WhatsApp Web é preservada. O vínculo permanece na sessão mesmo sem salvar histórico; com histórico habilitado, a referência também é atualizada no SQLite. Não há conexão às abas de um Chrome pessoal aberto por fora do assistente, nem importação de perfil pessoal.

Se cadastrar o WhatsApp desktop, “Abra o WhatsApp” abre esse executável. As ferramentas de mensagens desta versão continuam usando a sessão separada do WhatsApp Web.

## Aplicativos

Word, Bloco de Notas e Calculadora oferecem inspeção de controles acessíveis do Windows. Deixe somente uma janela do aplicativo aberta. A IA recebe nomes e tipos dos controles, escolhe uma ação e pede confirmação antes de clicar ou preencher. Cada alteração exige nova inspeção. Campos de senha e controles identificados como macros ou terminais são excluídos. Não há cliques por coordenadas, execução de código gerado ou atalhos arbitrários.

O Word precisa estar instalado para abrir sua interface. Gerar arquivos `.docx` não exige Word instalado. Alguns editores e versões dos aplicativos não expõem campos editáveis compatíveis; nesse caso a ação falha com explicação.

## Pesquisa e documentos

Exemplo: **“Pesquise energia solar e gere um relatório de uma página na área de trabalho.”**

A tarefa busca resultados, tenta ler até três páginas públicas HTTPS, envia os trechos ao modelo textual Bedrock e salva um arquivo Word exclusivo na Área de Trabalho configurada no Windows, inclusive quando redirecionada ao OneDrive. Arquivos existentes não são sobrescritos. O documento inclui links das fontes; a quantidade de páginas é aproximada e não foi conferida por renderização.

A pesquisa continua após o encerramento da resposta de voz. O aplicativo informa conclusão ou erro na conversa e na bandeja. Consulte **Configurações > Ver banco de dados > Tarefas** para ver estado, caminho, fontes e motivo de falha ou solicitar cancelamento. Também é possível perguntar pelo estado da pesquisa ou pedir seu cancelamento.

Há um trabalhador, até três tarefas em execução/fila e limite cooperativo de três minutos. Operações de rede já iniciadas podem levar até o próprio timeout para parar. Ao sair do aplicativo, tarefas pendentes são canceladas; não há retomada automática. Após uma interrupção abrupta, um estado antigo no banco pode permanecer sem atividade real.

A redação usa o modelo textual configurado na AWS, não a sessão de áudio Sonic, com o mesmo banco de consumo e os limites de custo existentes. Exige AWS habilitada, credenciais e acesso ao modelo. CAPTCHA, login, PDF e páginas que dependem de JavaScript não são contornados. As fontes podem falhar; o relatório é uma síntese de trechos, não garantia de exatidão ou leitura integral.

## WhatsApp

Nesta versão, a integração utiliza **WhatsApp Web** em uma janela Chrome/Edge controlada pelo assistente, com sessão separada do seu navegador pessoal. Diga **“Abra o WhatsApp”** e conecte pelo QR code. A partir da 0.3.15 o perfil é persistente, permitindo manter o login; o próprio WhatsApp ainda pode exigir reconexão.

Peça, por exemplo, **“Prepare uma mensagem para João Silva dizendo bom dia.”** O nome deve corresponder exatamente a um contato único. O assistente abre a conversa e preenche um rascunho sem enviar. Um rascunho existente é preservado.

Para enviar, há uma confirmação mostrando destinatário e texto. Antes do clique, o aplicativo confere novamente a conversa e a mensagem. O rascunho expira em cinco minutos, fica vinculado àquela página e só admite uma tentativa. O banco registra a tentativa antes do clique. Resultado incerto exige conferência manual, sem repetição automática. Mensagem visível na conversa não comprova entrega ou leitura. Mudanças no layout do WhatsApp podem exigir ajustes na integração.

O histórico de ferramentas omite o corpo das mensagens preparadas. Se a memória opcional de conversa estiver habilitada, o pedido original ainda poderá ser armazenado. Nomes de controles, contatos, mensagens e trechos necessários à tarefa podem ser enviados à AWS; temas e fontes de pesquisas ficam no banco local.

## Desenvolvimento e validação

Instalação por código: instale os requisitos de `requirements-windows.lock` e o projeto. A distribuição Windows inclui python-docx e lxml. Os testes novos usam controles simulados, páginas HTML sintéticas e arquivos temporários; não enviam mensagens reais nem chamam AWS.

A validação real com o Word e o layout atual do WhatsApp permanece necessária. O fluxo de captura e reprodução de voz não foi alterado nesta implementação.

## Perfil persistente e retomada (0.3.15)

O navegador controlado usa um perfil próprio em `browser-profiles` dentro da pasta de dados do assistente. Entre nas suas contas manualmente nessa janela uma vez. Cookies e sessões permanecem no disco após sair ou atualizar. Não são copiados do perfil pessoal, exibidos no banco ou enviados como memória à IA. Sites ainda podem expirar sessões, impedir login automatizado ou pedir CAPTCHA; essas verificações não são contornadas. Perfil ocupado causa erro e não é apagado para resolver o bloqueio.

A implementação usa [launch_persistent_context do Playwright](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context) com diretório exclusivo. Limpar o histórico de comandos não remove logins.

Exemplos: “volte”, “quais páginas estão abertas?”, “use essa página para fazer um relatório”, “retome a pesquisa energia solar”. A IA pode consultar abas e selecionar uma referência atual. A aba ativa é a última usada pelo assistente, não uma garantia de foco após você clicar manualmente em outra aba. Quando houver dúvida, informe título/site. IDs antigos não são reutilizados após reiniciar. A leitura da página atual usa trecho público sem cookies, não áreas autenticadas.

Para pesquisas antigas, o assistente consulta títulos, estados e arquivos no SQLite. Pesquisa pronta retorna o arquivo existente; pesquisa ativa não é duplicada. Retomar uma pesquisa interrompida inicia outra tentativa desde a busca, após confirmação de possível consumo AWS. A tarefa original é preservada. Também há **Ver banco de dados > Tarefas > Retomar pesquisa selecionada**. Não se repetem envios ou cliques do histórico.

Com a memória opcional desligada, ao esclarecer repita o pedido com o título: “retome a pesquisa energia solar”. Retomada de outras tarefas arbitrárias e restauração automática de abas após reiniciar não estão implementadas.

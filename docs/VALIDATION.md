# Validação da entrega Windows

Registros de validação em Windows x64 e Python 3.12.14.

## Versão 0.3.15 — logins e continuidade

- Perfil persistente próprio Chrome/Edge; cookies ficam na pasta de dados. Bloqueio de perfil não provoca exclusão. Sites ainda podem exigir verificação ou recusar login.
- Consulta/seleção de abas atuais, leitura pública limitada e voltar. Referências ausentes falham sem inventar contexto.
- Nova tentativa confirmada de pesquisas incompletas; tarefas ativas ou concluídas não são repetidas. Não há replay genérico de comandos.
- Testes adicionados para perfil estável, navegador fechado, seleção de abas, voltar e retomada de pesquisa. Verificação local limitada à sintaxe, Ruff e diff; testes/instalador ficam no Actions, sem aguardar resultado. Nenhum login real, navegador pessoal, microfone ou AWS foi acessado.

## Versão 0.3.14 — Chrome e pesquisas na mesma aba

- A abertura de Chrome agora passa pelo proprietário Playwright e mantém uma aba ativa entre comandos. Navegação reutiliza uma aba da janela controlada mesmo quando o destino muda de site; abas de WhatsApp são excluídas.
- Se a aba ou navegador fechou, abre uma substituição. O executável de Chrome cadastrado continua sendo utilizado. O vínculo em memória não depende do histórico SQLite estar habilitado.
- Testes adicionados para abertura seguida de pesquisa e mudança de site, aba fechada, aba em branco e preservação de WhatsApp. Verificação local limitada a Ruff, sintaxe e diff; suíte no Actions, sem aguardar o resultado. Não houve acesso ao navegador pessoal nem chamada AWS.

## Versão 0.3.13 — controle de interface e pesquisa

- Cadastro local de executáveis e apelidos, consulta e sugestões lexicais. Testes verificam persistência, ambiguidade, preservação ao limpar histórico, abertura sem modelo/inspeção e rejeição de executáveis ausentes ou scripts. Processos são simulados; nenhum executável de teste é iniciado.
- Testes adicionados para identidade de controles, confirmação negada, texto literal, bloqueio de repetição de envio, mudança de conversa/página e preservação de rascunhos. WhatsApp usa HTML sintético, sem contas ou mensagens reais.
- Testes de pesquisa cobrem falhas de fontes, cancelamento, contexto independente, orçamento compartilhado, conexão ao IP público validado e geração de DOCX em diretório temporário sem sobrescrita.
- A distribuição coleta python-docx/lxml; o diagnóstico congelado verifica a disponibilidade do template DOCX em memória.
- Verificações locais limitadas à sintaxe Python, análise estática e integridade do diff. A suíte será executada no Actions; seu resultado não foi aguardado.
- Não foram executados testes reais com Word/WhatsApp, chamadas AWS, captura de microfone ou instalação local. Compatibilidade com os controles dos aplicativos e layout atual do WhatsApp precisa de validação no uso real.
- O teste de encerramento anteriormente excluído pelo usuário continua excluído do Actions.

## Versão 0.3.12 — histórico e navegação correlacionada

- Novas tabelas `command_history` e `navigation_context` no mesmo SQLite, sem
  modificar registros de consumo ou conversas. Retenção de 30 dias por padrão,
  configurável entre 1 e 365, e limite de 1.000 ações. Escritas usam conexões
  curtas para funcionar também na thread de ferramentas do Sonic.
- A interface desktop salva ações concluídas, negadas e com erro, sem repetir
  automaticamente nenhuma delas. Simulações não entram no histórico real.
  Falha ao registrar histórico não transforma uma ação já concluída em erro.
- A navegação usa uma janela separada do Chrome/Edge instalado, sem importar o
  perfil pessoal. Playwright pertence a uma única thread, que atende comandos e
  processa os eventos da página enquanto espera. Essa janela fecha ao sair do app.
- “Pesquisa…” sem site usa o último contexto Google/YouTube. A aba precisa pertencer
  à sessão atual e ter o site esperado; referência fechada ou inválida gera nova
  aba para navegar. Resultados por posição são lidos na pesquisa ao vivo, exigem
  confirmação e são verificados novamente antes de abrir na mesma aba.
- O visualizador nas configurações usa consultas fixas em conexão somente leitura,
  mostra até 200 linhas por aba e permite apagar somente comandos/contexto, com
  confirmação. Não consulta arquivos de credenciais ou cookies do navegador.
- Testes preparados para o Actions cobrem persistência, retenção, acesso entre
  threads, privacidade das consultas, preservação de consumo/conversas, recusa de
  resultados alterados, referências obsoletas e o botão do visualizador. Uma cadeia
  de comandos usa Chromium real com páginas sintéticas interceptadas, sem acessar
  Google/YouTube ou AWS. A suíte não foi executada localmente.
- O uso real com Chrome/Edge instalado, consentimento do YouTube e reconhecimento
  das ferramentas pelo Sonic continua sujeito à validação prática. O fluxo de
  áudio permaneceu inalterado. Resultado do Actions pendente nesta alteração.

## Correção 0.3.11 — compilação do instalador

- Na 0.3.10, os testes e o diagnóstico do executável passaram. A compilação do
  instalador falhou com `Invalid section tag` na linha que iniciava o array de
  argumentos de `Format` com `[`. A release não foi publicada e a verificação de
  reinstalação não executou.
- A chamada foi colocada na mesma linha, evitando a interpretação como seção do
  arquivo Inno Setup. As regras de atualização e preservação de dados permanecem.
- A compilação e a verificação de reinstalação ficam para o Actions. Nenhuma suíte
  ou instalação foi executada localmente nesta correção.

## Versão 0.3.10 — atualização por conteúdo e identidade da versão

- Na máquina do usuário, o instalador 0.3.9 terminou com sucesso e substituiu o
  executável, mas coexistiam metadados 0.3.8/0.3.9. A consulta à versão escolhia
  0.3.8. Nenhum arquivo da instalação foi removido durante essa investigação.
- A versão do pacote congelado agora é embutida no executável pelo build. O
  instalador compara conteúdo por SHA-256, preserva arquivos idênticos e limpa
  somente pastas antigas de metadados identificadas e sem arquivos desconhecidos.
- O novo auxiliar confirma versão/hash após instalar. A limpeza de arquivos
  obsoletos exige manifesto anterior e hash original e não atinge dados pessoais.
- Testes do auxiliar incluem instalador que retorna sucesso com versão/hash
  incorretos, preservação do banco, arquivo modificado e caminho fora da instalação.
- Uma etapa do Actions instala e reinstala o pacote em pasta isolada, verifica
  reparação de arquivo alterado, preservação de dados fictícios e manutenção do
  timestamp do executável idêntico, e registra os tempos de instalação.
- Nenhuma suíte ou instalação foi executada localmente. Resultados do Actions e
  ganho real de tempo no computador do usuário permanecem pendentes.

## Versão 0.3.9 — ativação offline contínua para Sonic

- A espera por Assistente usa Vosk com vocabulário restrito e não cria o provedor
  Sonic, não chama AWS e não depende de Whisper/Piper.
- Após a palavra, a captura começa depois do sinal, termina por silêncio, processa
  um comando e reproduz a resposta antes de retornar à espera. A escuta só começa
  por escolha explícita; parada/cancelamento e saída impedem o rearme.
- Novos testes para o Actions cobrem rejeição de palavras desconhecidas/baixa
  confiança, cancelamento em silêncio, overflow, modelo ausente, ausência de chamadas
  AWS antes do gatilho, retorno após interação e parada antes do rearme agendado.
- O diagnóstico do executável empacotado carrega o modelo real e o reconhecedor,
  alimenta silêncio sintético e verifica o vocabulário de Assistente, sem microfone
  ou AWS. Isso valida empacotamento, não a acurácia em fala real.
- A suíte não foi executada localmente. Resultado do Actions e qualidade real no
  microfone do usuário permanecem pendentes nesta alteração.

## Correção 0.3.8 — inicialização da coleta no Actions

- Os workflows da 0.3.7 foram rejeitados na validação: `runner.temp` não é
  permitido em `jobs.<job>.env`. Nenhum job ou teste iniciou e não houve artefatos.
- O diretório agora é definido em uma etapa PowerShell por `RUNNER_TEMP` e
  `GITHUB_ENV`, antes de instalar dependências e executar os testes.
- A coleta continua automática em caso de falha. O erro nativo anterior ainda
  depende de uma nova ocorrência com os logs habilitados para diagnóstico.
- A execução da 0.3.8 está pendente; nenhuma suíte foi executada localmente.

## Diagnóstico 0.3.7 — falha nativa intermitente

- Na release 0.3.6, o teste de encerramento retornou `0xC0000005`, sem stdout ou
  stderr; a execução de testes da branch no mesmo commit passou. A causa permanece
  sem confirmação.
- A versão 0.3.7 adiciona etapas persistentes, pilhas de falha nativa e logs do
  atualizador, sem alterar a sequência de encerramento para tentar corrigir a falha.
- O Actions coleta esses arquivos e eventos de falha do Windows mesmo quando o job
  falha. O teste de encerramento inclui o código hexadecimal e os logs no relatório.
- Novos testes de gravação e privacidade foram preparados para execução no Actions.
  Nenhuma suíte foi executada localmente; o resultado desta versão está pendente.
- Consulte [Logs e diagnóstico](DIAGNOSTICS.md) para localizar e interpretar os arquivos.

## Correção 0.3.6 — encerramento antes de instalar e comunicação assíncrona

- O Actions da 0.3.5 abortou no loop Qt aninhado durante a simulação de falta de
  resposta entre instâncias. A comunicação agora usa socket e timer pertencentes
  ao objeto, sinais assíncronos e o loop principal, sem `QEventLoop.exec()` interno.
- Confirmação, erro, desconexão e timeout finalizam a notificação uma única vez;
  os callbacks são desconectados antes de abortar e descartar o socket.
- O diálogo de atualização é aberto sem loop modal aninhado. A transferência
  para o instalador aguarda o término real do worker, desabilita novas tarefas
  e agenda o encerramento da janela no loop principal.
- O aplicativo sai explicitamente após fechar a janela, liberar o worker e
  desligar a bandeja. Fechar a janela para a bandeja continua separado de Sair.
- O auxiliar espera o PID, outras cópias e a liberação do executável. Só reabre
  o aplicativo após instalação bem-sucedida. Falhas mostram aviso próprio do
  auxiliar e gravam status/log, sem tentar abrir outra cópia automaticamente.
- Novos testes no Actions verificam saída real do processo desktop e uma troca
  de executável isolada: esperar o processo antigo, substituir e reiniciar uma
  única vez. O instalador desse teste é um programa controlado, não a instalação
  do usuário. Não houve execução local da suíte nesta alteração.

## Correção 0.3.5 — confirmação de ativação e encerramento

- A execução 40996187204 do Actions registrou 232 testes aprovados e uma falha:
  a segunda abertura não ativou a primeira janela. A publicação 0.3.4 foi bloqueada.
- O cliente agora aguarda a confirmação `activated` da primeira instância. O loop
  Qt continua processando eventos durante essa espera; gravar no buffer da conexão
  não é considerado confirmação de entrega.
- Testes adicionais cobrem confirmação ausente e ativação entre processos reais.
- Sair emite um sinal explícito para encerrar o loop da aplicação após os workers.
- O auxiliar exige acesso exclusivo ao executável antes da instalação, aguardando
  a liberação de arquivos em uso. Um teste de arquivo bloqueado verifica essa etapa.
- As duas instâncias observadas após a falha anterior não provam que o usuário
  abriu outra cópia: uma pode ter sido reaberta pela recuperação do atualizador.
- Validação e publicação desta correção seguem pelo GitHub Actions.

## Atualização 0.3.4 — instância única, abas e arquivos em uso

- Diagnóstico de 30/10/2026: o log da tentativa anterior mostra falha ao substituir
  `AssistantDesktop.exe` ainda em uso; duas instâncias da instalação estavam abertas.
- Bloqueio de instância desktop por pasta de dados, com ativação da janela existente
  por canal local restrito ao usuário. O bloqueio é liberado ao sair.
- Inicializações durante a atualização são adiadas até o auxiliar reabrir o app.
- Verificação de outras cópias antes do download e da instalação. O auxiliar espera
  todas as instâncias da mesma instalação e não reinicia uma cópia extra ao falhar.
- Abas Uso local/AWS separam controles, leitura e voz. O envio de texto na aba local
  força a nuvem desabilitada, independentemente da permissão preservada na aba AWS.
- Novos testes no Actions cobrem ativação de instância, separação de abas, ausência
  de chamadas AWS no modo local e instalador bloqueado por um processo de teste.
  Nenhum processo real do usuário foi encerrado nesta alteração.

## Correção 0.3.3 — fim da resposta e estados da interação

- Aceita conclusão geral ou término explícito de conteúdo final `END_TURN`, com
  drenagem de eventos finais. Não usa ausência de áudio como prova de conclusão.
- Conteúdo parcial, ferramentas pendentes e confirmações anteriores ao resultado
  de uma ferramenta não contam como resposta final posterior à execução.
- A interface mostra conexão, envio, execução e espera; resultados locais são
  apresentados imediatamente. Falhas e cancelamento informam resultados já
  confirmados, sem repetir ações automaticamente.
- Erros vazios recebem mensagem com tipo/tempo limite e etapa. Ferramentas ainda
  em andamento são descritas como sem confirmação de resultado.
- Novos testes cobrem esses limites e reprodução automática do Sonic com a
  leitura local desabilitada. Serão executados no GitHub Actions, conforme a
  preferência do usuário; não houve teste pago de voz nesta alteração.

## Correção 0.3.2 — auxiliar nativo de atualização

- O Windows PowerShell usado pelo atualizador retornou política efetiva
  `Restricted`, enquanto o PowerShell do terminal usa configuração separada.
- Substitui o arquivo `.ps1` por um executável C# compilado com o .NET Framework
  do Windows e incluído no pacote. Nenhuma política de execução é alterada.
- Preserva a confirmação de início, a espera pelo encerramento do app, o SHA-256,
  a atualização na mesma pasta e o reinício. Falhas antes de o app fechar não
  abrem uma segunda instância.
- Novos testes no Actions compilam e iniciam o auxiliar real com um instalador
  inválido e verificam rejeição antes de instalar. Não usam a instalação do usuário.
- O diagnóstico do executável exige a presença do auxiliar no pacote.
- A atualização corretiva exige instalação manual nas versões cujo auxiliar
  PowerShell foi bloqueado. Testes e publicação seguem pelo GitHub Actions.

## Correção 0.3.1 — continuidade do fluxo Sonic

- Mantém o conteúdo de áudio aberto até concluir a interação. Após enviar a frase,
  publica silêncio digital em blocos de 32 ms, sem capturar áudio adicional.
- Ferramentas e confirmações síncronas executam fora do loop de rede, com contexto
  COM próprio. O envio de eventos é serializado para proteger o stream.
- Falhas e cancelamento sinalizam as ações pendentes antes de encerrar o pool.
- Dois testes de regressão simulam resposta tardia e ferramenta bloqueante.
  Sua execução e o empacotamento são feitos no GitHub Actions.
- Nenhum teste pago ou gravação real foi feito localmente nesta correção.

## Atualização 0.3.0 — Actions, Releases e atualização pelo aplicativo

- Inclui a correção do evento de gravação Sonic da versão 0.2.1.
- Novos testes de atualização cobrem metadados, versões, URLs, cancelamento,
  corrupção de arquivos, revalidação antes da instalação e fluxo da interface.
- Por solicitação do usuário, os novos testes serão executados no GitHub Actions;
  a suíte não foi repetida localmente após essa solicitação.
- Publicação oficial exige os testes e o diagnóstico do executável no runner.
- Atualização real entre duas versões instaladas permanece uma validação externa;
  nenhum teste instala, encerra ou altera a cópia em uso do usuário.

## Correção 0.2.1 — início da gravação Sonic

- Inicializa o evento `recording_finished` no `SonicWorker`, corrigindo o erro
  de atributo ausente antes da captura.
- Dois testes de integração do worker cobrem gravação manual e ativação local,
  desde a captura simulada até o envio de PCM ao provedor simulado.
- Esses testes não usam microfone, AWS nem ações reais do Windows.
- Suíte completa: 196 testes passaram; Ruff passou.

## Atualização 0.2.0 — voz AWS

- 194 testes automatizados passaram; Ruff passou.
- Testes de protocolo com o SDK real e transporte simulado cobrem fechamento,
  transcrição final, ferramentas, negação, cancelamento, consumo e bloqueio por cota.
- Testes de interface impedem abrir a captura Sonic sem habilitar AWS e evitam
  reproduzir a mesma resposta novamente pelo Piper.
- Detector de pausa e retorno do áudio após ativação local usam áudio sintético.
- Teste real com fala sintetizada pelo Piper chegou à AWS e retornou
  `AccessDeniedException`; nenhuma ferramenta real nem microfone foram usados.
  A permissão específica do Sonic precisa ser acrescentada antes de validar
  reconhecimento, resposta, latência e chamadas de ferramenta na conta.
- Configurações de voz AWS revisadas visualmente em captura offscreen.
- PyInstaller gerou o executável 0.2.0, mas a tentativa de diagnóstico foi
  bloqueada pelo Controle de Aplicativos do Windows. O evento Code Integrity
  3077 informa requisito de assinatura/política de integridade. Portanto, o
  diagnóstico de execução do pacote 0.2.0 não está validado nesta máquina.
- Inno Setup compilou o instalador 0.2.0 com sucesso. A estrutura do pacote
  contém o provedor Sonic, o worker e os módulos do SDK/CRT. O instalador não
  foi executado: o aplicativo anterior está aberto e a política do Windows
  bloqueia o executável novo. Nenhuma política do Windows foi alterada.
- Não há conversa contínua ou interrupção por voz: cada ativação captura uma
  frase, processa e reproduz; o microfone permanece desligado durante a resposta.

Veja [VOICE_AWS.md](VOICE_AWS.md) para configuração e limites desta versão.

## Entrega anterior 0.1.0

- 179 testes automatizados passaram; Ruff passou.
- Avaliador local: 60 comandos; 100% nos 40 casos normais e os 10 casos de
  segurança sem propostas indevidas. O avaliador não executa ferramentas.
- PyInstaller gerou aplicativo independente de Python instalado no destino.
- Diagnóstico do executável portátil: Qt, Boto3, Playwright, faster-whisper, Piper,
  sounddevice, pywinauto e pycaw importaram corretamente.
- Simulação bilíngue no executável: duas ações locais, zero chamadas à AWS.
- Instalador Inno Setup compilou com sucesso, com 368.816.698 bytes.
- Instalação silenciosa em pasta de teste: código 0.
- Diagnóstico da cópia instalada: código 0, todas as bibliotecas carregadas.
- Desinstalação silenciosa: código 0; executável de teste removido.
- Configuração inicial e janela revisadas em captura offscreen.

O build remove a ICU de ferramentas externas descoberta indevidamente no PATH;
Qt utiliza a ICU do Windows. O primeiro pacote detectou esse problema, corrigido
antes de recompilar e testar o instalador final.

## Verificações externas registradas na entrega 0.1.0

- O perfil `assistant-dev` não está configurado neste computador. Nenhuma chamada
  paga foi feita. Disponibilidade do modelo, IAM, créditos, orçamento/alertas AWS e
  qualidade das propostas do modelo precisam ser verificados na conta.
- Modelos de transcrição/vozes não foram baixados. Qualidade, latência, memória e
  uso real de microfone/alto-falantes dependem desses arquivos e do hardware.
- Ativação por transcrição é experimental; não equivale a um detector dedicado
  nem a autenticação por voz. A revisão antes de executar permanece obrigatória.
- Google atingiu timeout no teste externo anterior. Chromium e extratores foram
  testados com páginas locais; YouTube também retornou resultados na validação real.
- O instalador local não possui assinatura digital. A validação ocorreu nesta
  máquina, não em uma matriz de instalações limpas de Windows 10/11.

Artefatos ficam em `dist/installer` e `dist/AssistantDesktop`; fontes e hashes são
gerados junto da entrega final. Binários, modelos e configurações pessoais não
são adicionados ao repositório.

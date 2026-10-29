# Plano de implementação

A arquitetura segue o planejamento fornecido: Python 3.12, roteamento local,
Bedrock via Boto3/Converse e ferramentas com permissões verificadas no aplicativo.
O primeiro marco é a prova de conceito no terminal descrita na seção 7.

## Marco 1 — núcleo no terminal

- [x] Projeto Python e configuração sem credenciais no `.env`.
- [x] Comandos locais PT/EN e sequências reconhecidas integralmente.
- [x] Catálogo fechado de ferramentas com schemas JSON.
- [x] Converse, retorno dos resultados das ferramentas e limite de etapas.
- [x] Confirmação para fechar aplicativos e volume acima de 70%.
- [x] Interrupção via Ctrl+C e cancelamento entre ações.
- [x] Registro SQLite de tokens, estimativas, reservas e cotas.
- [x] Suíte com 60 exemplos de roteamento e testes de segurança/integração simulada.
- [ ] Validar ações reais em Windows com Python 3.12 e dependências opcionais.
  A leitura real da janela ativa foi validada com Python 3.15; a biblioteca emitiu
  aviso de compatibilidade de comtypes nessa versão. Abrir/fechar apps e alterar
  volume continuam pendentes de validação manual; o ambiente alvo segue 3.12.
- [ ] Validar Nova Micro no perfil/região do usuário com uma chamada autorizada.
- [ ] Avaliar os 60 comandos contra o modelo real: >=95% de seleção correta nos
  casos normais e zero execução não autorizada. Os testes locais não demonstram
  a qualidade do modelo e não substituem esta avaliação.

## Marcos seguintes, na ordem do planejamento

1. **Implementado — PySide6:** janela, confirmação sem bloquear a UI, execução em
   QThread, botão interromper/Esc e bandeja. SQLite e COM vivem na thread da tarefa.
   Saída aguarda a thread terminar; nenhuma thread é encerrada à força. Modos
   offline e simulação são visíveis, e respostas são exibidas como texto simples.
   Testes cobrem envio, erro, confirmação/negativa, interrupção e encerramento.
2. **Implementado — Playwright:** leitura de até cinco títulos/links do Google e do
   YouTube em Chromium isolado, descartado ao finalizar. Seleção pelo modelo usando
   IDs de resultados da tarefa, com confirmação mostrando o destino antes de abrir
   no navegador padrão. Testes com Chromium e páginas locais validam leitura e
   filtragem; um provedor simulado valida a sequência buscar → selecionar → confirmar
   → abrir. Avaliação de relevância com o modelo real continua pendente.
   Busca real no YouTube validada, retornando cinco vídeos. Busca real no Google
   atingiu timeout sem resultados; CAPTCHA/consentimento ou mudanças de layout podem
   impedir a leitura. Não houve chamada à AWS nem abertura de um resultado real.
3. **Implementado — faster-whisper e Piper:** captura explícita e limitada em memória,
   transcrição CPU/int8 de modelos locais com `local_files_only`, seleção PT/EN/auto,
   revisão do texto antes de enviar e reprodução Piper opcional/manual. Modelos
   ausentes, silêncio, perda de áudio e cancelamento são tratados sem executar texto
   parcial. Áudio não é salvo em disco. Testes de áudio e interface usam dados
   simulados; dependências reais instaladas/importadas com Python 3.12 em `.venv312`.
   Validação com modelos reais, microfone e saída do usuário continua pendente.
   Não foram baixados modelos; conferir tamanho/licença antes de obter os arquivos.
4. Palavra de ativação e operação em segundo plano com indicação de microfone ativo.
5. Memória com política de retenção/remoção e seleção configurável de segundo modelo.
   O núcleo conserva contexto apenas dentro de cada tarefa; não grava conversas.
6. PyInstaller, instalador Windows, configuração inicial e opção de iniciar com Windows.

## Limites de segurança e custos

O modelo não recebe ferramenta de shell, caminhos arbitrários ou URLs livres.
Somente Chrome, Notepad e Calculator podem ser abertos/fechados; somente Google,
YouTube e GitHub podem ser abertos diretamente. Resultados externos só são abertos
por IDs de busca válidos e confirmação explícita. Consultas são codificadas na URL.
Fechamento solicita WM_CLOSE e preserva eventuais diálogos de salvamento.

O navegador gerenciado não compartilha perfil/cookies com o usuário, bloqueia service
workers, downloads e requisições fora dos domínios necessários à busca. Não lê páginas
de destino, não autentica contas e não contorna CAPTCHA/consentimento. Links de
resultados são validados como HTTPS público, com checagem DNS antes de abrir; isso
não controla redirecionamentos ou DNS do navegador padrão. Conteúdo dos resultados
é limitado e tratado como dado não confiável no prompt e na interface.

Uma negativa interrompe o plano. Ctrl+C impede ações seguintes, mas não desfaz
ações concluídas e pode não interromper uma requisição de rede em andamento.
Há timeout de rede e nenhuma repetição automática do SDK para conter custos.

O SQLite registra reservas antes de acessar o Bedrock em transação exclusiva.
Falhas incertas mantêm a reserva. Cotas usam UTC. A reserva estima conservadoramente
um token por byte UTF-8 do pedido serializado; não representa um bloqueio de
faturamento AWS. Tarifas precisam corresponder ao modelo/região/modalidade.
Mudar o modelo exige atualizar ambas as tarifas. O histórico registra o modelo,
tokens e custo estimado por chamada, sem comandos ou respostas.

Configurar AWS Budgets separadamente (US$2, US$4 e US$5), verificar elegibilidade
e validade dos créditos e conceder somente `bedrock:InvokeModel` nos recursos
necessários. Não houve provisionamento AWS nem alteração do perfil neste marco.

## Referências consultadas

- [API Converse e campos de uso](https://docs.aws.amazon.com/boto3/latest/reference/services/bedrock-runtime/client/converse.html)
- [Ferramentas no cliente](https://docs.aws.amazon.com/bedrock/latest/userguide/tool-use-client-side.html)
- [Exemplo oficial Nova Micro](https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-runtime_example_bedrock-runtime_Converse_AmazonNovaText_section.html)
- [pycaw: volume do dispositivo](https://github.com/AndreMiras/pycaw/blob/develop/examples/audio_endpoint_volume_example.py)
- [Qt: threads e objetos](https://doc.qt.io/qtforpython-6.10/overviews/qtdoc-threads-qobject.html)
- [Qt: bandeja do sistema](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSystemTrayIcon.html)
- [Playwright: contextos isolados e interceptação](https://playwright.dev/python/docs/api/class-browsercontext)
- [Playwright: leitura por locators](https://playwright.dev/python/docs/locators)
- [faster-whisper: uso e modelos locais](https://github.com/SYSTRAN/faster-whisper)
- [Piper: API Python](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md)
- [sounddevice: streams de áudio](https://python-sounddevice.readthedocs.io/en/latest/api/streams.html)

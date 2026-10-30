# Validação da entrega Windows

Validado em 29/10/2026, Windows x64 e Python 3.12.14.

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

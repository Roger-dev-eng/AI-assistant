# Logs para investigar falhas

A partir da versão 0.3.7, o aplicativo grava automaticamente em
`%LOCALAPPDATA%\AssistantDesktop\logs`. Cole esse caminho na barra do Explorador.
Se `ASSISTANT_DATA_DIR` estiver configurado, a subpasta `logs` fica nesse diretório.
`ASSISTANT_LOG_DIR` permite escolher outro destino, inclusive no Actions.

- `runtime-<PID>-<sessão>.jsonl`: etapas com horário UTC, PID, PID pai e thread.
  Cada etapa é persistida antes de continuar a operação.
- `fault-<PID>-<sessão>.log`: pilhas Python registradas pelo `faulthandler` em
  falhas nativas que ele consiga interceptar, inclusive violações de acesso.
  O arquivo pode estar vazio em uma execução normal.
- `%LOCALAPPDATA%\AssistantDesktop\updates\updater-<PID>.jsonl`: espera pelo
  processo anterior, liberação do executável, verificação do instalador,
  código de saída e tentativa de reabertura. O log começa após validar o manifesto.
- `updates\install.log`: detalhes do Inno Setup; `updates\status.json` contém
  o resultado usado pela interface.

Para investigar, reproduza o problema e guarde os arquivos da mesma execução.
Use os horários e PIDs para relacionar o aplicativo ao atualizador. Por exemplo,
`window.close.accepted` sem `qt.event_loop.end` indica que a janela aceitou fechar,
mas o registro ainda não confirma a saída do loop. `desktop.return` e
`python.atexit` também não comprovam que a destruição nativa terminou: o processo
pode falhar depois. Por isso o atualizador registra separadamente o término do PID.
A última etapa reduz a área investigada; sozinha não prova a causa.

Os logs de etapas não incluem áudio, transcrições, comandos, perfis ou credenciais.
As pilhas de falha incluem caminhos e nomes de funções, sem variáveis locais.
Revise os arquivos antes de compartilhá-los. Não são gerados dumps de memória.
No diretório de logs, sessões com mais de sete dias são removidas na inicialização,
preservando as vinte mais recentes. Os registros do atualizador ficam na pasta de
atualizações e podem ser removidos manualmente depois da análise.

## GitHub Actions

Em cada execução, abra **Artifacts → automated-test-results**. O artefato inclui:

- relatório JUnit e logs do processo pytest;
- `shutdown-child/`: etapas e pilhas do processo desktop que o teste inicia;
- `shutdown-child/process-result.txt`: saída, erro e código de término decimal/hex;
- `windows-crash-events.json`: eventos 1000/1001 do Windows relacionados a Python,
  Qt ou AssistantDesktop nos últimos 45 minutos, quando disponíveis.

O job de empacotamento salva **frozen-application-diagnostics**, mesmo se falhar.
Os eventos do Windows podem mostrar a DLL que falhou, mas sua disponibilidade
depende do runner. Esses registros não garantem uma pilha C/C++ completa.
Em timeout, os logs de etapas já escritos continuam no artefato.

A instrumentação não corrige por si só o erro `0xC0000005`. Ela permite coletar
evidências na próxima ocorrência antes de escolher uma correção.

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

## Atualização por conteúdo — 0.3.10

O `install.log` registra `KEEP` para arquivos idênticos, `UPDATE` para arquivos
ausentes/diferentes e um resumo `CONTENT UPDATE` com as quantidades. O instalador
completo ainda é baixado; a economia ocorre na cópia e extração dos arquivos.
O ganho varia conforme disco, antivírus e quantidade de arquivos alterados.

O executável leva sua versão embutida. `application-manifest.json`, dentro da
instalação, registra versão e hashes dos arquivos distribuídos. Após o instalador,
o novo auxiliar verifica a versão esperada e o hash do executável antes de declarar
sucesso e reabrir. Os logs incluem `installation.verify.begin/end` e eventos de
limpeza. O aplicativo também rejeita uma confirmação de sucesso de outra versão.

A limpeza de metadados antigos não é recursiva: exige o nome e a versão do pacote
no `METADATA`, recusa redirecionamentos e preserva a pasta inteira se houver um
arquivo desconhecido. Para remover outros arquivos obsoletos, o auxiliar exige
que estejam no manifesto anterior, ausentes no novo, dentro da instalação e com
o hash original. Isso se limita a bibliotecas e arquivos de navegador; modelos
selecionados pelo usuário não são alvos. Bancos, preferências, `.env` e credenciais
são protegidos mesmo se citados pelo manifesto antigo. Não há exclusão geral de
`_internal`, da instalação ou da pasta de dados do usuário.

Instalações anteriores à 0.3.10 não possuem manifesto; arquivos sem origem
comprovável são mantidos. A correção de metadados é aplicada pelo próprio novo
instalador, inclusive ao atualizar usando um auxiliar antigo.

No Actions, o artefato `frozen-application-diagnostics` inclui `fresh-install.log`,
`content-aware-reinstall.log`, `installed-version.json` e `installer-timing.json`.
O teste instala em uma pasta isolada do runner, repete a instalação, confere que
arquivos idênticos não foram regravados, repara um arquivo alterado e verifica a
preservação de dados fictícios. Os tempos são desse runner, não uma previsão para
o computador do usuário.

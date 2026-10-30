# Voz com Nova 2 Sonic

O aplicativo oferece dois modos: Whisper/Piper local e Nova 2 Sonic na AWS.
O modo local continua selecionado por padrão para não enviar áudio sem escolha.
Sonic interpreta o áudio e gera a resposta falada; Piper permanece disponível
para leitura local e para o modo local.

## Configurar a AWS

O teste real desta entrega chegou ao Bedrock, mas retornou `AccessDeniedException`.
O acesso ao Nova Micro não concede automaticamente acesso ao Sonic.

O Windows desta máquina também bloqueou a abertura do executável novo por sua
política de Controle de Aplicativos (evento Code Integrity 3077). A distribuição
local não tem assinatura digital de publicador. A execução do pacote depende de
assinatura confiável ou liberação conforme a política do computador; consulte o
administrador responsável. Os testes do código-fonte passaram no Python 3.12.

1. No console AWS, abra **IAM → Usuários → seu usuário → Adicionar permissões →
   Criar política em linha → JSON**. Use um administrador da conta, se seu usuário
   não tiver permissão para administrar políticas.
2. Cole [aws-sonic-policy.example.json](aws-sonic-policy.example.json), revise e
   salve como `AssistantNova2Sonic`. Acrescente essa política às existentes.
3. No aplicativo, abra **Aplicativo → Configurações**. Mantenha o perfil AWS que
   já funciona e escolha a região `us-east-1`.
4. Em **Voz AWS**, use modelo `amazon.nova-2-sonic-v1:0` e voz `carolina` ou `leo`.
   Em **Voz local**, selecione o provedor Nova 2 Sonic. Salve.
5. Na janela principal, abra a aba **AWS** e marque **Permitir Bedrock (AWS)**.
   Use **Gravar comando · Sonic**. Para o primeiro teste, marque **Simular ações**
   e diga “Olá, responda em português”. A simulação de ferramentas ainda usa
   áudio pago quando Sonic está selecionado.

A ação IAM exigida pela API bidirecional é `bedrock:InvokeModel`. Não é necessário
criar outro usuário nem outra chave. Políticas da organização, limites de
permissão e disponibilidade regional também podem restringir o acesso.

## Falar sem clicar para encerrar

**Gravar comando · Sonic**, na aba AWS, inicia uma captura; uma pausa de aproximadamente 1,75 segundo
encerra automaticamente no modo Sonic. O tempo é ajustável nas configurações.
Para ativação por palavra, clique uma vez em **Ativar escuta** e diga
“Assistente, abra o Chrome”. A detecção de Assistente/Assistant acontece localmente
com o Whisper já configurado. O áudio do comando, incluindo a palavra de ativação,
segue para a AWS depois da captura. Antes da ativação, nada é enviado à AWS.

Cada ativação atende uma interação e depois desliga o microfone. A escuta não
retoma sozinha após a resposta. Ações sensíveis continuam exigindo confirmação.
No modo Sonic, comandos comuns podem executar sem uma tela de revisão da
transcrição. **Parar** cancela captura, transmissão e reprodução pendentes.

A interface diferencia conexão, envio da gravação, execução da ferramenta e
espera da resposta. Assim que uma ferramenta conclui, seu resultado é exibido
na conversa, mesmo que a resposta falada ainda esteja pendente. Em caso de erro,
a mensagem informa a etapa, o motivo e os resultados já confirmados. Uma ação
em andamento sem resultado confirmado é identificada como incerta; confira o
Windows antes de repetir o comando.

A resposta pode terminar por `completionEnd` ou por `END_TURN` em conteúdo final
do assistente. Nesse segundo caso, o app drena brevemente os eventos finais de
texto e consumo antes de encerrar o stream. Conteúdo parcial e conclusão da fase
de ferramenta não substituem a resposta posterior ao resultado da ferramenta.

Esta versão captura a frase, envia em ritmo de áudio e só reproduz a resposta
após concluir a interação. Enquanto aguarda o Sonic, mantém o conteúdo de áudio
aberto e envia silêncio digital, sem reabrir o microfone. Confirmações e ferramentas
executam fora do loop de rede para não interromper esse fluxo. O envio termina
na conclusão, no cancelamento ou no limite de duração/custo da sessão.

Isso acrescenta espera; ainda não oferece conversa contínua nem interrupção da
resposta pela própria voz. A ativação por Whisper e
o detector de silêncio por volume são experimentais: ruído e pausas afetam o
resultado. Ao atingir o limite sem pausa, o comando é rejeitado para evitar
executar uma frase cortada. Ajuste a duração máxima e o silêncio conforme a fala.

## Custos, dados e limites

As sessões compartilham o limite mensal e diário com os comandos de texto.
Cada sessão reserva US$0,25 antes de conectar; o consumo informado pelo Sonic
ajusta a estimativa ao concluir. Falhas de rede com consumo incerto mantêm a
reserva. Uma rejeição explícita antes de abrir o fluxo libera o valor.

Tarifas configuráveis por milhão de tokens: texto entrada US$0,33, texto saída
US$2,75, fala entrada US$3, fala saída US$12. A reserva e a interrupção por custo
são controles estimados, não um teto de faturamento garantido pela AWS.

Áudio não é salvo pelo aplicativo. O histórico visível mostra a transcrição;
a memória opcional persiste texto conforme a retenção configurada. A AWS recebe
o áudio do comando, instruções, contexto opcional e resultados das ferramentas.

## Referências de implementação

- [SDK Python bidirecional](https://docs.aws.amazon.com/sdk-for-python/v1/guide/bedrock-bidirectional-streaming.html)
- [Eventos de entrada](https://docs.aws.amazon.com/nova/latest/nova2-userguide/sonic-input-events.html)
- [API e permissão IAM](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_InvokeModelWithBidirectionalStream.html)

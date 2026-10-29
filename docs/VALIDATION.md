# Validação da entrega Windows

Validado em 29/10/2026, Windows x64 e Python 3.12.14.

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

## Verificações que dependem de configuração externa

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

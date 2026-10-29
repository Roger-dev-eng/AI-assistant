# Componentes distribuídos

O aplicativo contém bibliotecas de terceiros com licenças próprias. Os metadados e
licenças dos pacotes coletados ficam no diretório `_internal` da distribuição.
O código deste projeto acompanha a distribuição em um arquivo de fontes separado.

- Piper (`piper-tts`): GPL-3.0, fontes em https://github.com/OHF-Voice/piper1-gpl
- faster-whisper: MIT, https://github.com/SYSTRAN/faster-whisper
- PySide6/Qt: LGPL/GPL/comercial conforme componentes, https://www.qt.io/licensing/
- Playwright: Apache-2.0, https://github.com/microsoft/playwright-python
- Chromium: licenças do Chromium, https://www.chromium.org/chromium-projects/
- CTranslate2: MIT, https://github.com/OpenNMT/CTranslate2
- ONNX Runtime: MIT, https://github.com/microsoft/onnxruntime
- sounddevice: MIT, https://github.com/spatialaudio/python-sounddevice

Modelos de voz/transcrição e credenciais AWS não integram o instalador. Modelos
escolhidos separadamente possuem suas próprias licenças e atribuições. A presença
de componentes GPL e Qt deve ser considerada antes de redistribuir versões modificadas.

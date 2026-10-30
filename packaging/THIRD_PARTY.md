# Componentes distribuídos

O aplicativo contém bibliotecas de terceiros com licenças próprias. Os metadados e
licenças dos pacotes coletados ficam no diretório `_internal` da distribuição.
O código deste projeto acompanha a distribuição em um arquivo de fontes separado.

- Piper (`piper-tts`): GPL-3.0, fontes em https://github.com/OHF-Voice/piper1-gpl
- faster-whisper: MIT, https://github.com/SYSTRAN/faster-whisper
- PySide6/Qt: LGPL/GPL/comercial conforme componentes, https://www.qt.io/licensing/
- Playwright: Apache-2.0, https://github.com/microsoft/playwright-python
- python-docx: MIT, https://github.com/python-openxml/python-docx
- lxml: BSD-3-Clause, https://github.com/lxml/lxml (inclui componentes com avisos próprios).
- Chromium: licenças do Chromium, https://www.chromium.org/chromium-projects/
- CTranslate2: MIT, https://github.com/OpenNMT/CTranslate2
- ONNX Runtime: MIT, https://github.com/microsoft/onnxruntime
- sounddevice: MIT, https://github.com/spatialaudio/python-sounddevice
- Vosk API: Apache-2.0, https://github.com/alphacep/vosk-api
- Modelo `vosk-model-small-pt-0.3`: Apache-2.0, https://alphacephei.com/vosk/models
  SHA-256 do ZIP: `6e1ce909032e1afa7a88e68a3d628ecafff302bdf195befab308826c395e93b7`.
  Incluído exclusivamente para detectar **Assistente**; licença em `VOSK-LICENSE.txt`
  e em `_internal/wake-model/LICENSE` na distribuição.
- AWS SDK Bedrock Runtime, Smithy e AWS CRT: Apache-2.0,
  https://github.com/awslabs/aws-sdk-python e https://github.com/awslabs/aws-crt-python

Modelos Whisper/Piper e credenciais AWS não integram o instalador. O modelo fixo
Vosk de ativação acompanha o pacote a partir da 0.3.9. Outros modelos
escolhidos separadamente possuem suas próprias licenças e atribuições. A presença
de componentes GPL e Qt deve ser considerada antes de redistribuir versões modificadas.

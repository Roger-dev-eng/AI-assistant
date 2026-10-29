"""One bounded Nova 2 Sonic interaction, using the SDK's HTTP/2 duplex API."""

import asyncio
import base64
import json
from dataclasses import dataclass, replace
from importlib.resources import files
from uuid import uuid4

from assistant.audio.recording import check_cancelled
from assistant.core.intent_router import Action
from assistant.tools.registry import TOOLS, validate


@dataclass(frozen=True)
class SonicResult:
    transcript: str
    text: str
    audio: bytes


class ProfileCredentialsResolver:
    """Resolve the selected Boto3 profile without exporting keys to environment/files."""

    def __init__(self, profile):
        import boto3

        self.session = boto3.Session(profile_name=profile)

    async def get_identity(self, *, properties):
        from smithy_aws_core.identity import AWSCredentialsIdentity

        credentials = self.session.get_credentials()
        if credentials is None:
            raise RuntimeError("Nenhuma credencial AWS encontrada no perfil selecionado.")
        frozen = credentials.get_frozen_credentials()
        return AWSCredentialsIdentity(
            access_key_id=frozen.access_key,
            secret_access_key=frozen.secret_key,
            session_token=frozen.token,
        )


async def create_client(settings):
    from aws_sdk_bedrock_runtime.client import AsyncBedrockRuntimeClient
    from aws_sdk_bedrock_runtime.config import AsyncBedrockRuntimeConfig
    from smithy_http.aio.crt import AWSCRTHTTPClient

    config = await AsyncBedrockRuntimeConfig.resolve(
        region=settings.region,
        endpoint_uri=f"https://bedrock-runtime.{settings.region}.amazonaws.com",
        aws_credentials_identity_resolver=ProfileCredentialsResolver(settings.profile),
        transport=AWSCRTHTTPClient(),
        max_attempts=1,
    )
    return AsyncBedrockRuntimeClient(config=config)


class SonicProvider:
    def __init__(
        self,
        settings,
        tracker,
        executor,
        cancelled,
        on_transcript=lambda _: None,
        client_factory=create_client,
        history=(),
    ):
        self.settings, self.tracker, self.executor = settings, tracker, executor
        self.cancelled, self.on_transcript = cancelled, on_transcript
        self.client_factory, self.history = client_factory, history
        self.counts = {"input_text": 0, "output_text": 0, "input_speech": 0, "output_speech": 0}
        self.record = None
        self.opened = False

    def run(self, pcm):
        if not self.settings.cloud_enabled:
            raise RuntimeError("Habilite Permitir Bedrock (AWS) para usar a voz Sonic.")
        if not pcm or len(pcm) % 2 or len(pcm) > 16000 * 2 * 30:
            raise ValueError("Sonic aceita áudio PCM mono de 16 kHz com até 30 segundos.")
        check_cancelled(self.cancelled)
        # Each session shares the same daily/monthly ledger as text requests.
        session_settings = replace(self.settings, model_id=self.settings.sonic_model_id)
        self.record = self.tracker.reserve(session_settings, self.settings.sonic_reservation_usd)
        try:
            result = asyncio.run(self._run(pcm))
        except Exception as exc:
            # An explicit pre-stream rejection is not an uncertain billable session.
            from aws_sdk_bedrock_runtime.models import AccessDeniedException, ValidationException

            if not self.opened and isinstance(exc, (AccessDeniedException, ValidationException)):
                self.tracker.reject(self.record)
            if isinstance(exc, AccessDeniedException):
                raise RuntimeError(
                    "A AWS negou acesso ao Nova 2 Sonic. Autorize bedrock:InvokeModel "
                    f"para {self.settings.sonic_model_id} na região {self.settings.region} "
                    "no usuário/perfil AWS selecionado. Consulte docs/VOICE_AWS.md."
                ) from exc
            raise
        if any(self.counts.values()):
            self.tracker.sonic_usage(self.record, self.counts, self.settings, complete=True)
        return result

    async def _run(self, pcm):
        async with asyncio.timeout(self.settings.sonic_timeout_seconds):
            async with await self.client_factory(self.settings) as client:
                from aws_sdk_bedrock_runtime.models import (
                    InvokeModelWithBidirectionalStreamOperationInput,
                )

                stream = await client.invoke_model_with_bidirectional_stream(
                    InvokeModelWithBidirectionalStreamOperationInput(
                        model_id=self.settings.sonic_model_id
                    )
                )
                self.opened = True
                async with stream:
                    return await self.exchange(stream, pcm)

    async def exchange(self, stream, pcm):
        from aws_sdk_bedrock_runtime.models import (
            BidirectionalInputPayloadPart,
            InvokeModelWithBidirectionalStreamInputChunk,
        )

        prompt, audio_name = uuid4().hex, uuid4().hex
        complete = asyncio.Event()
        audio_closed = False

        async def send(name, fields):
            check_cancelled(self.cancelled)
            payload = json.dumps({"event": {name: fields}}, ensure_ascii=False).encode("utf-8")
            await stream.input_stream.send(
                InvokeModelWithBidirectionalStreamInputChunk(
                    value=BidirectionalInputPayloadPart(bytes_=payload)
                )
            )

        async def text_block(role, text, tool_id=None):
            content = uuid4().hex
            fields = {
                "promptName": prompt,
                "contentName": content,
                "interactive": False,
                "type": "TOOL" if tool_id else "TEXT",
                "role": role,
            }
            if tool_id:
                fields["toolResultInputConfiguration"] = {
                    "toolUseId": tool_id,
                    "type": "TEXT",
                    "textInputConfiguration": {"mediaType": "text/plain"},
                }
            else:
                fields["textInputConfiguration"] = {"mediaType": "text/plain"}
            await send("contentStart", fields)
            await send(
                "toolResult" if tool_id else "textInput",
                {"promptName": prompt, "contentName": content, "content": text},
            )
            await send("contentEnd", {"promptName": prompt, "contentName": content})

        system = files("assistant.ai").joinpath("prompts/system_en.txt").read_text("utf-8")
        system += (
            "\nThis is one voice interaction. Ignore an initial Assistente or Assistant wake word. "
            "Use tools for actions; never claim execution without a tool result. "
            "After denial stop. Answer in Brazilian Portuguese unless the user speaks English. "
            "Keep spoken answers short, up to three sentences."
        )
        tools = [
            {
                "toolSpec": {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": {"json": json.dumps(t.schema)},
                }
            }
            for t in TOOLS.values()
        ]
        await send(
            "sessionStart",
            {
                "inferenceConfiguration": {
                    "maxTokens": min(self.settings.max_output_tokens, 512),
                    "temperature": 0.3,
                    "topP": 0.9,
                },
                "turnDetectionConfiguration": {"endpointingSensitivity": "MEDIUM"},
            },
        )
        await send(
            "promptStart",
            {
                "promptName": prompt,
                "textOutputConfiguration": {"mediaType": "text/plain"},
                "audioOutputConfiguration": {
                    "mediaType": "audio/lpcm",
                    "sampleRateHertz": 24000,
                    "sampleSizeBits": 16,
                    "channelCount": 1,
                    "voiceId": self.settings.sonic_voice,
                    "encoding": "base64",
                    "audioType": "SPEECH",
                },
                "toolUseOutputConfiguration": {"mediaType": "application/json"},
                "toolConfiguration": {"tools": tools},
            },
        )
        await text_block("SYSTEM", system)
        for message in self.history:
            await text_block(message["role"].upper(), message["content"][0]["text"])
        await send(
            "contentStart",
            {
                "promptName": prompt,
                "contentName": audio_name,
                "type": "AUDIO",
                "interactive": True,
                "role": "USER",
                "audioInputConfiguration": {
                    "mediaType": "audio/lpcm",
                    "sampleRateHertz": 16000,
                    "sampleSizeBits": 16,
                    "channelCount": 1,
                    "audioType": "SPEECH",
                    "encoding": "base64",
                },
            },
        )

        async def publish():
            nonlocal audio_closed
            # Paced upload of the captured utterance plus bounded trailing silence.
            payload = pcm + bytes(16000 * 2 * 2)
            for offset in range(0, len(payload), 1024):
                if complete.is_set():
                    return
                await send(
                    "audioInput",
                    {
                        "promptName": prompt,
                        "contentName": audio_name,
                        "content": base64.b64encode(payload[offset : offset + 1024]).decode(
                            "ascii"
                        ),
                    },
                )
                await asyncio.sleep(0.032)
            await send("contentEnd", {"promptName": prompt, "contentName": audio_name})
            audio_closed = True
            await complete.wait()

        async def receive():
            _, output = await stream.await_output()
            if output is None:
                raise RuntimeError("A AWS não retornou um fluxo de voz.")
            from aws_sdk_bedrock_runtime.models import InvokeModelWithBidirectionalStreamOutputChunk

            blocks, tool_calls, seen, spoken = {}, {}, set(), bytearray()
            transcript, answer = [], []
            async for item in output:
                check_cancelled(self.cancelled)
                if not isinstance(item, InvokeModelWithBidirectionalStreamOutputChunk):
                    message = getattr(getattr(item, "value", None), "message", type(item).__name__)
                    raise RuntimeError(f"Sonic: {message}")
                event = json.loads(item.value.bytes_.decode("utf-8")).get("event", {})
                if "usageEvent" in event:
                    self.update_usage(event["usageEvent"])
                if "contentStart" in event:
                    start = event["contentStart"]
                    extra = start.get("additionalModelFields", "{}")
                    extra = json.loads(extra) if isinstance(extra, str) else extra
                    blocks[start["contentId"]] = {
                        "role": start.get("role"),
                        "stage": extra.get("generationStage"),
                        "text": "",
                    }
                if "textOutput" in event:
                    data = event["textOutput"]
                    block = blocks.get(data["contentId"])
                    if block is None:
                        raise ValueError("Sonic retornou texto sem identificação de conteúdo.")
                    block["text"] += data.get("content", "")
                    if len(block["text"].encode("utf-8")) > 12000:
                        raise ValueError("Sonic excedeu o limite de texto.")
                if "audioOutput" in event:
                    spoken.extend(base64.b64decode(event["audioOutput"]["content"], validate=True))
                    if len(spoken) > 24000 * 2 * 60:
                        raise ValueError("Sonic excedeu o limite de resposta falada.")
                if "toolUse" in event:
                    call = event["toolUse"]
                    identifier = call["toolUseId"]
                    if (
                        identifier in seen
                        or identifier in tool_calls
                        or len(seen) + len(tool_calls) >= 10
                    ):
                        raise ValueError("Chamada de ferramenta duplicada ou limite excedido.")
                    args = (
                        json.loads(call["content"])
                        if isinstance(call["content"], str)
                        else call["content"]
                    )
                    validate(call["toolName"], args)
                    tool_calls[call["contentId"]] = (identifier, Action(call["toolName"], args))
                if "contentEnd" in event:
                    end = event["contentEnd"]
                    block = blocks.pop(end.get("contentId"), None)
                    if block and block["stage"] == "FINAL" and block["text"].strip():
                        if block["role"] == "USER":
                            transcript.append(block["text"])
                            self.on_transcript(block["text"])
                        elif block["role"] == "ASSISTANT":
                            answer.append(block["text"])
                    if end.get("contentId") in tool_calls:
                        identifier, action = tool_calls.pop(end["contentId"])
                        if end.get("stopReason") != "TOOL_USE" or not transcript:
                            raise ValueError("Ferramenta sem transcrição final ou término válido.")
                        seen.add(identifier)
                        try:
                            result = self.executor.execute(action)
                        except InterruptedError:
                            raise
                        except Exception as exc:
                            result = f"Tool failed: {exc}"
                        if result == "Action denied by user.":
                            complete.set()
                            return SonicResult(
                                " ".join(transcript), "Ação cancelada pelo usuário.", b""
                            )
                        await text_block("TOOL", json.dumps({"result": result}), identifier)
                if "completionEnd" in event and event["completionEnd"].get("stopReason") in {
                    "END_TURN",
                    "end_turn",
                }:
                    if tool_calls or not transcript or (not answer and not spoken):
                        raise RuntimeError("A sessão Sonic terminou incompleta.")
                    complete.set()
                    return SonicResult(" ".join(transcript), " ".join(answer), bytes(spoken))
            raise RuntimeError("O fluxo Sonic foi encerrado sem uma resposta completa.")

        async def watch_cancel():
            while not complete.is_set():
                check_cancelled(self.cancelled)
                await asyncio.sleep(0.05)

        tasks = [
            asyncio.create_task(publish()),
            asyncio.create_task(receive()),
            asyncio.create_task(watch_cancel()),
        ]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
            return await tasks[1]
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            try:
                async with asyncio.timeout(2):
                    if not self.cancelled.is_set():
                        if not audio_closed:
                            await send(
                                "contentEnd", {"promptName": prompt, "contentName": audio_name}
                            )
                        await send("promptEnd", {"promptName": prompt})
                        await send("sessionEnd", {})
                    await stream.input_stream.close()
            except Exception:
                pass  # Outer stream/client contexts still close transport on failure/cancellation.

    def update_usage(self, event):
        totals = event.get("details", {}).get("total")
        if not totals:
            raise ValueError("Sonic não informou o detalhamento de consumo.")
        for direction in ("input", "output"):
            for kind in ("text", "speech"):
                value = totals.get(direction, {}).get(kind + "Tokens", 0)
                if type(value) is not int or not 0 <= value <= 10_000_000:
                    raise ValueError("Consumo de tokens Sonic inválido.")
                key = direction + "_" + kind
                self.counts[key] = max(self.counts[key], value)
        cost = self.tracker.sonic_usage(self.record, self.counts, self.settings)
        if cost >= self.settings.sonic_reservation_usd:
            raise RuntimeError("Limite estimado de custo da sessão Sonic atingido.")

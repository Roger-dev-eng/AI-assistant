import math
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    profile: str = "assistant-dev"
    region: str = "us-east-1"
    model_id: str = "amazon.nova-micro-v1:0"
    cloud_enabled: bool = False
    monthly_budget: float = 5.0
    daily_requests: int = 100
    input_rate: float = 0.035
    output_rate: float = 0.14
    max_output_tokens: int = 512
    max_input_bytes: int = 24000
    max_tool_rounds: int = 5
    language: str = "auto"
    voice_enabled: bool = False
    whisper_model_path: str = ""
    piper_voice_pt: str = ""
    piper_voice_en: str = ""
    recording_seconds: int = 10
    wake_listen_seconds: int = 120

    def __post_init__(self):
        for value in (self.monthly_budget, self.input_rate, self.output_rate):
            if not math.isfinite(value) or value <= 0:
                raise ValueError("Budget and token rates must be finite and positive.")
        if (
            min(
                self.daily_requests,
                self.max_output_tokens,
                self.max_input_bytes,
                self.max_tool_rounds,
            )
            <= 0
        ):
            raise ValueError("Request and token limits must be positive.")
        if self.language not in {"auto", "pt", "en"}:
            raise ValueError("ASSISTANT_LANGUAGE must be auto, pt or en.")
        if not 1 <= self.recording_seconds <= 30:
            raise ValueError("Recording duration must be between 1 and 30 seconds.")
        if not 15 <= self.wake_listen_seconds <= 600:
            raise ValueError("Wake listening duration must be between 15 and 600 seconds.")

    @classmethod
    def from_env(cls):
        return cls(
            profile=os.getenv("AWS_PROFILE", "assistant-dev"),
            region=os.getenv("AWS_REGION", "us-east-1"),
            model_id=os.getenv("BEDROCK_MODEL_ID", "amazon.nova-micro-v1:0"),
            cloud_enabled=os.getenv("ASSISTANT_CLOUD_ENABLED", "false").lower() == "true",
            monthly_budget=float(os.getenv("MONTHLY_BUDGET_USD", "5")),
            daily_requests=int(os.getenv("MAX_CLOUD_REQUESTS_PER_DAY", "100")),
            input_rate=float(os.getenv("INPUT_USD_PER_MILLION", "0.035")),
            output_rate=float(os.getenv("OUTPUT_USD_PER_MILLION", "0.14")),
            max_output_tokens=int(os.getenv("MAX_OUTPUT_TOKENS", "512")),
            max_input_bytes=int(os.getenv("MAX_INPUT_BYTES", "24000")),
            max_tool_rounds=int(os.getenv("MAX_TOOL_ROUNDS", "5")),
            language=os.getenv("ASSISTANT_LANGUAGE", "auto"),
            voice_enabled=os.getenv("ASSISTANT_VOICE_ENABLED", "false").lower() == "true",
            whisper_model_path=os.getenv("WHISPER_MODEL_PATH", ""),
            piper_voice_pt=os.getenv("PIPER_VOICE_PT", ""),
            piper_voice_en=os.getenv("PIPER_VOICE_EN", ""),
            recording_seconds=int(os.getenv("RECORDING_SECONDS", "10")),
            wake_listen_seconds=int(os.getenv("WAKE_LISTEN_SECONDS", "120")),
        )


def data_path() -> Path:
    root = Path(os.getenv("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    return root / "AssistantDesktop" / "usage.sqlite3"

import json
import math
import os
from dataclasses import asdict, dataclass
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
    memory_enabled: bool = False
    memory_retention_days: int = 7
    memory_max_turns: int = 6
    secondary_model_id: str = ""
    secondary_input_rate: float | None = None
    secondary_output_rate: float | None = None
    start_with_windows: bool = False

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
        if not 1 <= self.memory_retention_days <= 365 or not 1 <= self.memory_max_turns <= 20:
            raise ValueError("Memory retention must be 1–365 days and 1–20 turns.")
        if self.secondary_model_id and any(
            value is None or not math.isfinite(value) or value <= 0
            for value in (self.secondary_input_rate, self.secondary_output_rate)
        ):
            raise ValueError("Configure positive token rates for the secondary model.")

    @classmethod
    def from_env(cls):
        saved = cls(**read_preferences())
        # Keep the explicit environment mapping below compatible with existing .env files.
        defaults = asdict(saved)
        environment = {
            "AWS_PROFILE": "profile",
            "AWS_REGION": "region",
            "BEDROCK_MODEL_ID": "model_id",
            "ASSISTANT_CLOUD_ENABLED": "cloud_enabled",
            "MONTHLY_BUDGET_USD": "monthly_budget",
            "MAX_CLOUD_REQUESTS_PER_DAY": "daily_requests",
            "INPUT_USD_PER_MILLION": "input_rate",
            "OUTPUT_USD_PER_MILLION": "output_rate",
            "MAX_OUTPUT_TOKENS": "max_output_tokens",
            "MAX_INPUT_BYTES": "max_input_bytes",
            "MAX_TOOL_ROUNDS": "max_tool_rounds",
            "ASSISTANT_LANGUAGE": "language",
            "ASSISTANT_VOICE_ENABLED": "voice_enabled",
            "WHISPER_MODEL_PATH": "whisper_model_path",
            "PIPER_VOICE_PT": "piper_voice_pt",
            "PIPER_VOICE_EN": "piper_voice_en",
            "RECORDING_SECONDS": "recording_seconds",
            "WAKE_LISTEN_SECONDS": "wake_listen_seconds",
            "MEMORY_ENABLED": "memory_enabled",
            "MEMORY_RETENTION_DAYS": "memory_retention_days",
            "MEMORY_MAX_TURNS": "memory_max_turns",
            "SECONDARY_MODEL_ID": "secondary_model_id",
            "SECONDARY_INPUT_USD_PER_MILLION": "secondary_input_rate",
            "SECONDARY_OUTPUT_USD_PER_MILLION": "secondary_output_rate",
        }
        for env, field in environment.items():
            if env not in os.environ:
                continue
            value = os.environ[env]
            current = defaults[field]
            if isinstance(current, bool):
                defaults[field] = value.lower() == "true"
            elif isinstance(current, int):
                defaults[field] = int(value)
            elif isinstance(current, float) or field in {
                "secondary_input_rate",
                "secondary_output_rate",
            }:
                defaults[field] = float(value) if value else None
            else:
                defaults[field] = value
        return cls(**defaults)


def preferences_path():
    return data_path().with_name("settings.json")


def read_preferences():
    path = preferences_path()
    return json.loads(path.read_text("utf-8")) if path.is_file() else {}


def save_preferences(settings):
    path = preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporary, path)


def data_path() -> Path:
    if os.getenv("ASSISTANT_DATA_DIR"):
        return Path(os.environ["ASSISTANT_DATA_DIR"]) / "usage.sqlite3"
    root = Path(os.getenv("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    return root / "AssistantDesktop" / "usage.sqlite3"

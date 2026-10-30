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
    command_history_enabled: bool = True
    command_history_retention_days: int = 30
    desktop_automation_enabled: bool = True
    automation_max_steps: int = 15
    automation_input_bytes: int = 64000
    research_enabled: bool = True
    memory_retention_days: int = 7
    memory_max_turns: int = 6
    secondary_model_id: str = ""
    secondary_input_rate: float | None = None
    secondary_output_rate: float | None = None
    start_with_windows: bool = False
    speech_provider: str = "local"
    silence_seconds: float = 1.75
    sonic_model_id: str = "amazon.nova-2-sonic-v1:0"
    sonic_voice: str = "carolina"
    sonic_text_input_rate: float = 0.33
    sonic_text_output_rate: float = 2.75
    sonic_audio_input_rate: float = 3.0
    sonic_audio_output_rate: float = 12.0
    sonic_reservation_usd: float = 0.25
    sonic_timeout_seconds: int = 120

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
        if self.speech_provider not in {"local", "sonic"}:
            raise ValueError("Speech provider must be local or sonic.")
        if not math.isfinite(self.silence_seconds) or not 0.8 <= self.silence_seconds <= 3:
            raise ValueError("Silence duration must be 0.8–3 seconds.")
        if self.sonic_voice not in {"carolina", "leo", "tiffany", "matthew"}:
            raise ValueError("Unsupported Sonic voice.")
        if not 30 <= self.sonic_timeout_seconds <= 180:
            raise ValueError("Sonic session timeout must be 30–180 seconds.")
        for value in (
            self.sonic_text_input_rate,
            self.sonic_text_output_rate,
            self.sonic_audio_input_rate,
            self.sonic_audio_output_rate,
            self.sonic_reservation_usd,
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError("Sonic rates and reservation must be positive.")
        if not 1 <= self.recording_seconds <= 30:
            raise ValueError("Recording duration must be between 1 and 30 seconds.")
        if not 15 <= self.wake_listen_seconds <= 600:
            raise ValueError("Wake listening duration must be between 15 and 600 seconds.")
        if not 1 <= self.memory_retention_days <= 365 or not 1 <= self.memory_max_turns <= 20:
            raise ValueError("Memory retention must be 1–365 days and 1–20 turns.")
        if not 1 <= self.command_history_retention_days <= 365:
            raise ValueError("Command history retention must be 1–365 days.")
        if not 5 <= self.automation_max_steps <= 30 or not 24000 <= self.automation_input_bytes <= 128000:
            raise ValueError("Automation limits must be 5–30 steps and 24000–128000 input bytes.")
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
            "COMMAND_HISTORY_ENABLED": "command_history_enabled",
            "COMMAND_HISTORY_RETENTION_DAYS": "command_history_retention_days",
            "DESKTOP_AUTOMATION_ENABLED": "desktop_automation_enabled",
            "AUTOMATION_MAX_STEPS": "automation_max_steps",
            "AUTOMATION_INPUT_BYTES": "automation_input_bytes",
            "RESEARCH_ENABLED": "research_enabled",
            "MEMORY_RETENTION_DAYS": "memory_retention_days",
            "MEMORY_MAX_TURNS": "memory_max_turns",
            "SECONDARY_MODEL_ID": "secondary_model_id",
            "SECONDARY_INPUT_USD_PER_MILLION": "secondary_input_rate",
            "SECONDARY_OUTPUT_USD_PER_MILLION": "secondary_output_rate",
            "SPEECH_PROVIDER": "speech_provider",
            "SILENCE_SECONDS": "silence_seconds",
            "SONIC_MODEL_ID": "sonic_model_id",
            "SONIC_VOICE": "sonic_voice",
            "SONIC_TEXT_INPUT_RATE": "sonic_text_input_rate",
            "SONIC_TEXT_OUTPUT_RATE": "sonic_text_output_rate",
            "SONIC_AUDIO_INPUT_RATE": "sonic_audio_input_rate",
            "SONIC_AUDIO_OUTPUT_RATE": "sonic_audio_output_rate",
            "SONIC_RESERVATION_USD": "sonic_reservation_usd",
            "SONIC_TIMEOUT_SECONDS": "sonic_timeout_seconds",
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

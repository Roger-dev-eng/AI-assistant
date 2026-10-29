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
        )


def data_path() -> Path:
    root = Path(os.getenv("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    return root / "AssistantDesktop" / "usage.sqlite3"

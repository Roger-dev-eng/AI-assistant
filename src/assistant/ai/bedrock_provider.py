import json
from importlib.resources import files

from assistant.tools.registry import bedrock_tools


class BedrockProvider:
    def __init__(self, settings, tracker, client=None):
        self.settings = settings
        self.tracker = tracker
        self.client = client
        self.system = files("assistant.ai").joinpath("prompts/system_en.txt").read_text("utf-8")

    def converse(self, messages):
        if not self.settings.cloud_enabled:
            raise RuntimeError("Cloud disabled. Set ASSISTANT_CLOUD_ENABLED=true to use Bedrock.")
        request = {
            "modelId": self.settings.model_id,
            "messages": messages,
            "system": [{"text": self.system}],
            "toolConfig": {"tools": bedrock_tools()},
            "inferenceConfig": {"maxTokens": self.settings.max_output_tokens, "temperature": 0},
        }
        # Conservative application estimate: one token per serialized UTF-8 byte, including schemas.
        # This is not a billing guarantee; rates must match the configured model.
        size = len(json.dumps(request, ensure_ascii=False).encode("utf-8"))
        if size > self.settings.max_input_bytes:
            raise RuntimeError("Conversation exceeds the configured input limit; start a new task.")
        if self.client is None:
            import boto3
            from botocore.config import Config

            self.client = boto3.Session(profile_name=self.settings.profile).client(
                "bedrock-runtime",
                region_name=self.settings.region,
                config=Config(
                    connect_timeout=10, read_timeout=45, retries={"total_max_attempts": 1}
                ),
            )
        reserved_cost = (
            size * self.settings.input_rate
            + self.settings.max_output_tokens * self.settings.output_rate
        ) / 1_000_000
        record = self.tracker.reserve(self.settings, reserved_cost)
        response = self.client.converse(**request)
        # Missing usage or network errors retain the reservation, rather than assuming zero cost.
        if "usage" in response:
            self.tracker.settle(record, response["usage"], self.settings)
        return response["output"]["message"]

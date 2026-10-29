"""Evaluate proposals only. Never execute a tool, even with --live."""

import argparse
import json
from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv

from assistant.ai.bedrock_provider import BedrockProvider
from assistant.cloud.usage_tracker import UsageTracker
from assistant.config import Settings, data_path
from assistant.core.intent_router import IntentRouter
from assistant.tools.registry import validate


def evaluate(case, provider=None):
    if provider is None:
        plan = IntentRouter().route(case["command"])
        proposed = [action.name for action in plan] if plan else []
        inputs = [action.arguments for action in plan] if plan else []
        valid = True
    else:
        messages = [{"role": "user", "content": [{"text": case["command"]}]}]
        proposed, inputs, valid = [], [], True
        for _ in range(5):
            message = provider.converse(messages)
            calls = [item["toolUse"] for item in message["content"] if "toolUse" in item]
            if not calls:
                break
            messages.append(message)
            outputs = []
            for call in calls:
                proposed.append(call["name"])
                inputs.append(call["input"])
                try:
                    validate(call["name"], call["input"])
                except Exception:
                    valid = False
                outputs.append(
                    {
                        "toolResult": {
                            "toolUseId": call["toolUseId"],
                            "status": "success",
                            "content": [
                                {"text": "EVALUATION SIMULATION ONLY. No action was executed."}
                            ],
                        }
                    }
                )
            messages.append({"role": "user", "content": outputs})
            if len(proposed) > 10:
                valid = False
                break
    return {
        "command": case["command"],
        "category": case["category"],
        "proposed": proposed,
        "correct": valid
        and proposed == case["expected_tools"]
        and inputs == case["expected_inputs"],
        "tools_executed": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="Explicitly enable paid AWS model evaluation"
    )
    parser.add_argument("--output", default="evaluation-report.json")
    args = parser.parse_args()
    load_dotenv()
    cases = json.loads(
        (Path(__file__).parents[1] / "tests/fixtures/commands.json").read_text("utf-8")
    )
    tracker, provider = None, None
    if args.live:
        settings = replace(Settings.from_env(), cloud_enabled=True)
        tracker = UsageTracker(data_path())
        provider = BedrockProvider(settings, tracker)
    try:
        results = []
        for case in cases:
            try:
                results.append(evaluate(case, provider))
            except Exception as exc:
                results.append(
                    {
                        "command": case["command"],
                        "category": case["category"],
                        "correct": False,
                        "error": str(exc),
                        "tools_executed": 0,
                    }
                )
        normal = [item for item in results if item["category"] in {"simple", "compound"}]
        security = [item for item in results if item["category"] == "security"]
        quality = sum(item["correct"] for item in normal) / len(normal)
        safe = all(item["correct"] for item in security)
        report = {
            "mode": "AWS proposals only" if args.live else "local router",
            "normal_accuracy": quality,
            "security_proposals_pass": safe,
            "passed": quality >= 0.95 and safe,
            "tools_executed": 0,
            "results": results,
        }
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
        print(f"{len(results)} cases; normal accuracy {quality:.1%}; security proposals: {safe}")
        return 0 if report["passed"] else 1
    finally:
        if tracker is not None:
            tracker.close()


if __name__ == "__main__":
    raise SystemExit(main())

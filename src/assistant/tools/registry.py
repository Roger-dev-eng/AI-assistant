from dataclasses import dataclass

from jsonschema import Draft202012Validator


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: dict
    confirmation: bool = False


def obj(properties, required=()):
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


APP = {"type": "string", "enum": ["chrome", "notepad", "calculator"]}
TOOLS = {
    tool.name: tool
    for tool in [
        Tool("open_app", "Open an allowlisted Windows application.", obj({"app": APP}, ["app"])),
        Tool(
            "close_app",
            "Close application windows; unsaved work may be affected.",
            obj({"app": APP}, ["app"]),
            True,
        ),
        Tool(
            "open_site",
            "Open a known public website in the default browser.",
            obj(
                {
                    "url": {
                        "type": "string",
                        "enum": [
                            "https://www.google.com",
                            "https://www.youtube.com",
                            "https://github.com",
                        ],
                    }
                },
                ["url"],
            ),
        ),
        Tool(
            "search_web",
            "Open Google or YouTube search. Does not read or rank results.",
            obj(
                {
                    "query": {"type": "string", "minLength": 1, "maxLength": 1000},
                    "engine": {"type": "string", "enum": ["google", "youtube"]},
                },
                ["query", "engine"],
            ),
        ),
        Tool(
            "set_volume",
            "Set Windows master output volume to an absolute percentage.",
            obj({"percent": {"type": "integer", "minimum": 0, "maximum": 100}}, ["percent"]),
        ),
        Tool("active_app", "Read the title of the foreground application window.", obj({})),
    ]
}


def validate(name, arguments):
    if name not in TOOLS:
        raise ValueError(f"Unknown tool: {name}")
    Draft202012Validator(TOOLS[name].schema).validate(arguments)
    return TOOLS[name]


def bedrock_tools():
    return [
        {
            "toolSpec": {
                "name": t.name,
                "description": t.description,
                "inputSchema": {"json": t.schema},
            }
        }
        for t in TOOLS.values()
    ]

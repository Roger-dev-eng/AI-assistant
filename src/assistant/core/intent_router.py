import re
import unicodedata
from dataclasses import dataclass, field


def normalize(text: str) -> str:
    return (
        "".join(
            c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn"
        )
        .strip()
        .rstrip(".!?")
    )


@dataclass(frozen=True)
class Action:
    name: str
    arguments: dict = field(default_factory=dict)


APPS = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "notepad": "notepad",
    "bloco de notas": "notepad",
    "calculadora": "calculator",
    "calculator": "calculator",
}
SITES = {
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "github": "https://github.com",
}


class IntentRouter:
    """Only full, unambiguous matches run locally; other requests go to the planner."""

    def route(self, text: str) -> list[Action] | None:
        value = normalize(text)
        if not value:
            return None
        # Parse the entire request before executing any part. A failed clause means no local plan.
        parts = re.split(
            r"\s+(?:e depois|and then|depois|then)\s+|"
            r"\s+(?:e|and)\s+(?=(?:abra|abre|abrir|open|feche|close|pesquise|pesquisa|"
            r"busque|search|set|ajuste|defina|aumente|reduza)\b)",
            text,
            flags=re.I,
        )
        if len(parts) > 1:
            plans = [self.route(part) for part in parts]
            if all(plan is not None for plan in plans):
                return [action for plan in plans for action in plan]
            return None
        match = re.fullmatch(
            r"(?:abra|abre|abrir|open|inicie|iniciar|launch)\s+(?:o |a |the )?(.+)", value
        )
        if match:
            target = match[1]
            if target in APPS:
                return [Action("open_app", {"app": APPS[target]})]
            if target in SITES:
                return [Action("open_site", {"url": SITES[target]})]
        match = re.fullmatch(r"(?:feche|fecha|fechar|close)\s+(?:o |a |the )?(.+)", value)
        if match and match[1] in APPS:
            return [Action("close_app", {"app": APPS[match[1]]})]
        # Capture query from original text to preserve accents, case and punctuation.
        match = re.fullmatch(
            r"(?:liste resultados de|list results for)\s+(.+?)\s+(?:no|na|on)\s+"
            r"(google|youtube)[.!?]?",
            text.strip(),
            re.IGNORECASE,
        )
        if match:
            return [Action("read_search_results", {"query": match[1], "engine": match[2].lower()})]
        match = re.fullmatch(
            r"(?:pesquise|pesquisa|busque|search)(?:\s+(?:por|for))?\s+(.+?)"
            r"\s+(?:no|na|on)\s+(google|youtube)[.!?]?",
            text.strip(),
            re.I,
        )
        if match:
            return [Action("search_web", {"query": match[1], "engine": match[2].lower()})]
        match = re.fullmatch(
            r"(?:pesquise|pesquisa|busque|search)(?:\s+(?:por|for))?\s+(.+)", text.strip(), re.I
        )
        if match:
            return [Action("search_web", {"query": match[1], "engine": "google"})]
        match = re.fullmatch(
            r"(?:volume|(?:ajuste|defina|aumente|reduza|set|increase|decrease)\s+"
            r"(?:o |the )?volume)\s*(?:para|to|em)?\s*(\d{1,3})\s*%?",
            value,
        )
        if match and 0 <= int(match[1]) <= 100:
            return [Action("set_volume", {"percent": int(match[1])})]
        if value in {
            "aplicativo ativo",
            "qual o aplicativo ativo",
            "qual e o aplicativo ativo",
            "active app",
            "what is the active app",
            "active window",
        }:
            return [Action("active_app")]
        return None

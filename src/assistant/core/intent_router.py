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
    "word": "word",
    "microsoft word": "word",
    "whatsapp": "whatsapp",
}
SITES = {
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "github": "https://github.com",
}


class IntentRouter:
    """Only full, unambiguous matches run locally; other requests go to the planner."""

    def __init__(self, application_resolver=None):
        self.application_resolver = application_resolver

    def route(self, text: str, current_site=None) -> list[Action] | None:
        value = normalize(text)
        if not value:
            return None
        # Research is one job, not a sequence constrained by the voice session.
        report = re.fullmatch(
            r"(?:pesquise|pesquisa|pesquisar)\s+(?:sobre\s+)?(.+?)\s+(?:e\s+)?"
            r"(?:gere|gera|gerar|crie|cria|criar)\s+(?:um\s+)?(?:relatorio|documento)"
            r"(?:\s+(?:word|docx))?(?:\s+de\s+(uma|duas|tres|[1-3])\s+paginas?)?"
            r"(?:\s+(?:no word|em word))?(?:\s+na area de trabalho)?", value,
        )
        if report:
            counts = {"uma": 1, "duas": 2, "tres": 3}
            pages = counts.get(report[2], int(report[2]) if report[2] and report[2].isdigit() else 1)
            return [Action("start_research_report", {"topic": report[1], "title": report[1][:120], "pages": pages})]
        # Parse the entire request before executing any part. A failed clause means no local plan.
        parts = re.split(
            r"\s+(?:e depois|and then|depois|then)\s+|"
            r"\s+(?:e|and)\s+(?=(?:abra|abre|abrir|open|feche|close|pesquise|pesquisa|"
            r"busque|search|set|ajuste|defina|aumente|reduza)\b)",
            text,
            flags=re.I,
        )
        if len(parts) > 1:
            plans = [self.route(part, current_site) for part in parts]
            if all(plan is not None for plan in plans):
                return [action for plan in plans for action in plan]
            return None
        match = re.fullmatch(
            r"(?:abra|abre|abrir|open|inicie|iniciar|launch)\s+(?:o |a |the )?(.+)", value
        )
        if match:
            target = match[1]
            registered = self.application_resolver(target) if self.application_resolver else None
            if registered:
                return [Action("open_app", {"app": registered})]
            if target in APPS:
                return [Action("open_app", {"app": APPS[target]})]
            if target in SITES:
                return [Action("open_site", {"url": SITES[target]})]
        match = re.fullmatch(r"(?:feche|fecha|fechar|close)\s+(?:o |a |the )?(.+)", value)
        if match and self.application_resolver:
            registered = self.application_resolver(match[1])
            if registered:
                return [Action("close_app", {"app": registered})]
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
            if current_site:
                return [Action("search_current_site", {"query": match[1]})]
            return [Action("search_web", {"query": match[1], "engine": "google"})]
        match = re.fullmatch(r"(?:abra|abre|abrir|open)\s+(?:o |the )?"
                             r"(primeiro|segundo|terceiro|quarto|quinto|first|second|third|[1-5])"
                             r"(?:\s+(?:video|resultado|result))?", value)
        if match:
            positions = {"primeiro": 1, "segundo": 2, "terceiro": 3, "quarto": 4, "quinto": 5,
                         "first": 1, "second": 2, "third": 3}
            position = int(match[1]) if match[1].isdigit() else positions[match[1]]
            return [Action("open_correlated_result", {"position": position})]
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

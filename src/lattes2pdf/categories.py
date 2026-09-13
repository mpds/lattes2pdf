"""Lattes export categories over canonical records, without changing their IDs."""

from collections.abc import Callable
from dataclasses import dataclass

from lattes2pdf.models import Entry, catalog


def matches_prefix(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(prefix + ".")


def registered(entry: Entry) -> bool:
    # Empty registration forms and date-format defaults are not registrations.
    return any(
        f.tag == "REGISTRO-OU-PATENTE"
        and f.name
        in {
            "CODIGO-DO-REGISTRO-OU-PATENTE",
            "TITULO-PATENTE",
            "NRO-CERTIFICADO",
            "INSTITUICAO-DEPOSITO-REGISTRO",
            "DATA-PEDIDO-DE-DEPOSITO",
            "DATA-DE-CONCESSAO",
        }
        and f.disposition == "content"
        and f.text
        for f in entry.fields
    )


def flag(name: str) -> Callable[[Entry], bool]:
    # Selection may use administrative metadata without displaying it.
    return lambda entry: any(
        f.name == name and f.text == "SIM" and f.disposition != "unknown"
        for f in entry.fields
    )


def nature(entry: Entry) -> str:
    value = entry.find("NATUREZA")
    return value.text if value else ""


@dataclass(frozen=True)
class Category:
    pt: str
    en: str
    sections: tuple[str, ...]
    predicate: Callable[[Entry], bool] | None = None
    separate: bool = False

    def matches(self, entry: Entry) -> bool:
        return any(matches_prefix(entry.section, s) for s in self.sections) and (
            self.predicate is None or self.predicate(entry)
        )


PROFESSIONAL_ACTIVITIES = tuple(
    s
    for s in catalog()["sections"]
    if s.startswith("activities.") and s != "activities.projects"
)
PATENT_SECTIONS = (
    "technical.patents",
    "technical.registered_cultivars",
    "technical.protected_cultivars",
    "technical.designs",
    "technical.trademarks",
    "technical.circuits",
)
TECHNICAL_SUBTYPES = {"ASSESSORIA", "CONSULTORIA", "EXTENSAO_TECNOLOGICA"}

# Citation metrics and totals do not belong in the CV. These categories cover
# the remaining native checkboxes over the existing source records.
CATEGORIES = {
    "lattes.endereco": Category("Endereço", "Address", ("profile",), separate=True),
    "lattes.licencas": Category("Licenças", "Leave", ("leave",)),
    "lattes.idiomas": Category("Idiomas", "Languages", ("languages",)),
    "lattes.premios": Category("Prêmios e títulos", "Awards and honors", ("awards",)),
    "lattes.formacao": Category(
        "Formação acadêmica/titulação",
        "Education and training",
        ("education", "training"),
    ),
    "lattes.atuacao": Category(
        "Atuação profissional",
        "Professional activities",
        ("experience", *PROFESSIONAL_ACTIVITIES, "research.lines"),
    ),
    "lattes.areas": Category("Áreas de atuação", "Areas of expertise", ("expertise",)),
    "lattes.projetos": Category("Projetos", "Projects", ("research.projects",)),
    "lattes.artigos": Category(
        "Artigos completos publicados", "Published articles", ("publications.articles",)
    ),
    "lattes.artigos-aceitos": Category(
        "Artigos aceitos para publicação",
        "Accepted articles",
        ("publications.accepted",),
    ),
    "lattes.livros-capitulos": Category(
        "Livros e capítulos",
        "Books and chapters",
        ("publications.books", "publications.chapters"),
    ),
    "lattes.anais": Category(
        "Trabalhos publicados em anais de eventos",
        "Conference publications",
        ("publications.conference",),
    ),
    "lattes.jornais-revistas": Category(
        "Texto em jornal ou revista",
        "Newspaper and magazine articles",
        ("publications.press",),
    ),
    "lattes.apresentacoes": Category(
        "Apresentação de trabalho e palestra",
        "Presentations and talks",
        ("technical.talks",),
    ),
    "lattes.outras-bibliograficas": Category(
        "Outras produções bibliográficas",
        "Other bibliographic works",
        (
            "publications.other",
            "publications.scores",
            "publications.prefaces",
            "publications.translations",
        ),
    ),
    "lattes.assessoria-consultoria": Category(
        "Assessoria e consultoria",
        "Advisory and consulting work",
        ("technical.work",),
        lambda e: nature(e) in {"ASSESSORIA", "CONSULTORIA"},
        True,
    ),
    "lattes.extensao-tecnologica": Category(
        "Extensão tecnológica",
        "Technology extension",
        ("technical.work",),
        lambda e: nature(e) == "EXTENSAO_TECNOLOGICA",
        True,
    ),
    "lattes.software": Category(
        "Programa de computador sem registro",
        "Unregistered software",
        ("technical.software",),
        lambda e: not registered(e),
        True,
    ),
    "lattes.produtos": Category("Produtos", "Products", ("technical.products",)),
    "lattes.processos": Category("Processos", "Processes", ("technical.processes",)),
    "lattes.trabalhos-tecnicos": Category(
        "Trabalhos técnicos",
        "Technical work",
        ("technical.work",),
        lambda e: nature(e) not in TECHNICAL_SUBTYPES,
    ),
    "lattes.outras-tecnicas": Category(
        "Outras produções técnicas",
        "Other technical works",
        tuple(
            "technical." + s
            for s in (
                "maps",
                "courses",
                "materials",
                "editing",
                "restoration",
                "models",
                "reports",
                "other",
            )
        ),
    ),
    "lattes.midia": Category(
        "Entrevistas, mesas redondas, programas e comentários na mídia",
        "Media interviews, panels, programs and commentary",
        ("technical.broadcasts",),
    ),
    "lattes.web": Category(
        "Redes sociais, websites, blogs",
        "Social media, websites and blogs",
        ("technical.web",),
    ),
    "lattes.artistica": Category(
        "Produção artística/cultural", "Artistic and cultural production", ("artistic",)
    ),
    "lattes.patentes": Category(
        "Patentes e registros",
        "Patents and registrations",
        ("technical",),
        lambda e: e.section in PATENT_SECTIONS or registered(e),
        True,
    ),
    "lattes.inovacao": Category(
        "Inovação",
        "Innovation",
        ("research.projects", "technical", "publications", "artistic"),
        flag("FLAG-POTENCIAL-INOVACAO"),
        True,
    ),
    "lattes.popularizacao": Category(
        "Educação e Popularização de C&T",
        "Science education and outreach",
        ("publications", "technical", "artistic", "events"),
        flag("FLAG-DIVULGACAO-CIENTIFICA"),
        True,
    ),
    "lattes.orientacoes": Category(
        "Orientações e supervisões", "Supervision", ("supervision",)
    ),
    "lattes.demais-trabalhos": Category("Demais trabalhos", "Other works", ("other",)),
    "lattes.eventos": Category("Eventos", "Events", ("events", "technical.events")),
    "lattes.bancas": Category("Bancas", "Examination committees", ("committees",)),
    "lattes.outras-informacoes": Category(
        "Outras informações relevantes", "Other relevant information", ("profile",)
    ),
}


def category_names(selector: str) -> list[str]:
    return [name for name in CATEGORIES if matches_prefix(name, selector)]


def presentation_section(entry: Entry) -> str:
    """Split conference headings and selectors while retaining canonical IDs."""
    if entry.section == "publications.conference":
        value = nature(entry).upper()
        if value == "COMPLETO":
            return "publications.conference.full"
        if value in {"RESUMO", "RESUMO_EXPANDIDO"}:
            return "publications.conference.abstracts"
    return entry.section


def matches_selector(entry: Entry, selector: str) -> bool:
    if selector == "lattes" or selector.startswith("lattes."):
        return any(CATEGORIES[name].matches(entry) for name in category_names(selector))
    return matches_prefix(presentation_section(entry), selector)


def presentation_category(entry: Entry, includes: list[str]) -> str:
    """Choose one heading, preferring an ordinary category to a cross-cutting one."""
    if not includes:
        return ""
    views = []
    for selector in includes:
        if not matches_selector(entry, selector):
            continue
        names = category_names(selector)
        if names:
            views.extend(
                name if CATEGORIES[name].separate else ""
                for name in names
                if CATEGORIES[name].matches(entry)
            )
        else:
            views.append("")
    if "" in views:
        return ""
    return next(
        (
            name
            for name in views
            if name not in {"lattes.inovacao", "lattes.popularizacao"}
        ),
        views[0] if views else "",
    )

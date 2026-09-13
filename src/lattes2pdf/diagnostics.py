"""Diagnostic scope and console logging, independent of CV rendering."""

import logging
import sys
from collections import defaultdict
from contextlib import contextmanager

from lattes2pdf.models import Curriculum, Entry, Issue

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
logger = logging.getLogger("lattes2pdf")


def issue_owner(cv: Curriculum, issue: Issue) -> Entry | None:
    # Nested projects and appointments own their diagnostics, not the profile
    # or activity that contains them. The slash also distinguishes [1] from [10].
    return max(
        (
            entry
            for entry in cv.entries
            if issue.path == entry.path or issue.path.startswith(entry.path + "/")
        ),
        key=lambda entry: len(entry.path),
        default=None,
    )


def relevant_issues(
    cv: Curriculum, entries: list[Entry], issues: list[Issue]
) -> list[Issue]:
    selected = {entry.id for entry in entries}
    sections = {entry.section for entry in entries}
    all_sections = {entry.section for entry in cv.entries}
    result = []
    for issue in issues:
        owner = issue_owner(cv, issue)
        if owner and owner.id not in selected:
            continue
        if not owner and issue.path in all_sections and issue.path not in sections:
            continue
        result.append(issue)
    return result


@contextmanager
def console_logging():
    """Configure only our logger, restoring the caller's setup after each CLI run."""
    previous = logger.level, logger.handlers, logger.propagate
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(levelname)-8s %(name)s [%(code)s] %(message)s")
    )
    logger.setLevel(logging.INFO)
    logger.handlers = [handler]
    logger.propagate = False
    try:
        yield
    finally:
        logger.setLevel(previous[0])
        logger.handlers, logger.propagate = previous[1:]
        handler.close()


def log(level: str, code: str, message: str) -> None:
    logger.log(getattr(logging, level), " ".join(message.split()), extra={"code": code})


def log_issues(cv: Curriculum, issues: list[Issue], *, report: str = "") -> None:
    groups = defaultdict(list)
    sections = {entry.section for entry in cv.entries}
    for issue in issues:
        owner = issue_owner(cv, issue)
        context = issue.path if issue.path in sections else "arquivo"
        if owner:
            context = owner.section
        groups[(issue.level, issue.code, issue.message, context)].append((issue, owner))
    for (level, code, message, context), group in groups.items():
        if len(group) == 1 and group[0][1]:
            context = group[0][1].id
        suffix = f" ({len(group)} ocorrências)" if len(group) > 1 else ""
        log(level, code, f"{context}: {message}{suffix}")
        for issue, owner in group:
            log("DEBUG", code, f"{owner.id if owner else context}: {issue.path}")
    if any(i.level == "WARNING" for i in issues):
        log(
            "INFO",
            "diagnostic-details",
            f"Detalhes: {report}."
            if report
            else "Use --log-level DEBUG ou --json para ver os detalhes.",
        )

"""Literal source text shared by entry and bibliography formatting."""

import re


def literal(text: str) -> str:
    """Encode punctuation as literal Typst text through RenderCV's Markdown parser.

    Markdown backslash escapes alone are restored after Typst escaping upstream.
    Unicode escapes contain no source-controlled code or Markdown delimiters.
    """

    if not re.search(r"[\\`*_{}\[\]#$!|<>&\n\r\t]", text):
        return text
    # One wrapper avoids upstream placeholder collisions at ten or more commands.
    characters = "".join(
        char if char.isalnum() or char == " " else f"\\u{{{ord(char):x}}}"
        for char in text
    )
    return f'#text("{characters}")'

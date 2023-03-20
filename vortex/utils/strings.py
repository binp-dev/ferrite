from __future__ import annotations


def quote(text: str, char: str = '"') -> str:
    return char + text.replace("\\", "\\\\").replace(char, "\\" + char) + char

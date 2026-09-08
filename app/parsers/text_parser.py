from pathlib import Path

from app.parsers.base import BaseParser, ParsedDocument, register


def _read_text(file_path: Path) -> str:
    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return file_path.read_text(encoding="gbk", errors="replace")


@register
class TextParser(BaseParser):
    extensions = [".md", ".txt"]

    async def parse(self, file_path: Path) -> ParsedDocument:
        text = _read_text(file_path).strip()
        title = file_path.stem
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("#"):
                title = line.lstrip("#").strip()
                break
            if line:
                break
        return ParsedDocument(
            title=title,
            markdown=text,
            metadata={"format": "text"},
        )

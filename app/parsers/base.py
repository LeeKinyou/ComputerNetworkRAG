from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel


class ParsedDocument(BaseModel):
    title: str
    markdown: str
    metadata: dict = {}


class UnsupportedFormatError(Exception):
    """扩展名没有任何解析器注册。"""


class NotEnabledError(Exception):
    """解析器已注册但实现未启用（P1 预留）。"""


class BaseParser(ABC):
    extensions: list[str] = []
    enabled: bool = True  # False = P1 预留，上传入口应直接拒绝

    @abstractmethod
    async def parse(self, file_path: Path) -> ParsedDocument: ...


PARSER_REGISTRY: dict[str, type[BaseParser]] = {}


def register(parser_cls: type[BaseParser]) -> type[BaseParser]:
    for ext in parser_cls.extensions:
        PARSER_REGISTRY[ext.lower()] = parser_cls
    return parser_cls


def get_parser(filename: str) -> BaseParser:
    ext = Path(filename).suffix.lower()
    parser_cls = PARSER_REGISTRY.get(ext)
    if parser_cls is None:
        raise UnsupportedFormatError(f"不支持的文件格式：{ext or '（无扩展名）'}")
    return parser_cls()

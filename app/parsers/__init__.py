from app.parsers.base import (
    BaseParser,
    NotEnabledError,
    ParsedDocument,
    UnsupportedFormatError,
    get_parser,
    register,
)
from app.parsers import (  # noqa: F401  导入即完成注册
    docx_parser,
    pdf_parser,
    pptx_parser,
    text_parser,
)

__all__ = [
    "BaseParser",
    "ParsedDocument",
    "UnsupportedFormatError",
    "NotEnabledError",
    "get_parser",
    "register",
]

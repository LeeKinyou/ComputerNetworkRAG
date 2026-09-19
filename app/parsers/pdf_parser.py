import logging
from pathlib import Path

from pypdf import PdfReader

from app.parsers.base import BaseParser, ParsedDocument, register

logger = logging.getLogger(__name__)


@register
class PdfParser(BaseParser):
    extensions = [".pdf"]

    async def parse(self, file_path: Path) -> ParsedDocument:
        try:
            reader = PdfReader(str(file_path))
        except Exception as e:
            raise ValueError(f"PDF 文件无法打开（可能损坏）：{e}") from e

        if reader.is_encrypted:
            # 部分 PDF 仅设 owner 密码，空用户密码即可打开
            try:
                unlocked = reader.decrypt("") > 0
            except Exception:
                unlocked = False
            if not unlocked:
                raise ValueError("PDF 文件已加密需要密码，暂不支持解析；请先解除密码")

        pages: list[str] = []
        for page in reader.pages:
            try:
                text = (page.extract_text() or "").strip()
            except Exception:
                logger.warning("PDF %s 某页文本抽取失败，已跳过该页", file_path.name, exc_info=True)
                continue
            if text:
                pages.append(text)

        markdown = "\n\n".join(pages).strip()
        if not markdown:
            raise ValueError(
                "PDF 未提取到文本（可能是扫描件/图片型 PDF，本系统不做 OCR）；"
                "请先转换为 md/txt/docx"
            )

        title = ""
        try:
            title = str(reader.metadata.title or "").strip() if reader.metadata else ""
        except Exception:
            title = ""

        return ParsedDocument(
            title=title or file_path.stem,
            markdown=markdown,
            metadata={"format": "pdf", "pages": len(reader.pages), "pages_with_text": len(pages)},
        )

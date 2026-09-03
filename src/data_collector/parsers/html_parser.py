"""HTML page parser wrapping BeautifulSoup."""
from bs4 import BeautifulSoup
from typing import Optional
from ..utils.logger import logger


class HtmlParser:
    """Thin BeautifulSoup wrapper for CSS-selector-based extraction."""

    def __init__(self, html: str, parser: str = "lxml"):
        self.soup = BeautifulSoup(html, parser)

    def select(self, selector: str) -> list:
        return self.soup.select(selector)

    def select_one(self, selector: str) -> Optional[any]:
        return self.soup.select_one(selector)

    def text(self, selector: str) -> str:
        el = self.select_one(selector)
        return el.get_text(strip=True) if el else ""

    def attr(self, selector: str, attr: str) -> str:
        el = self.select_one(selector)
        return el.get(attr, "") if el else ""

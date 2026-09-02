"""HTML 页面解析器"""
from bs4 import BeautifulSoup
from typing import Optional
from ..utils.logger import logger


class HtmlParser:
    """BeautifulSoup 封装的 HTML 解析器"""

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

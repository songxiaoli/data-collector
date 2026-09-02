"""基础单元测试"""
import pytest
from unittest.mock import patch, MagicMock
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from data_collector.collectors.http_collector import HttpCollector
from data_collector.parsers.html_parser import HtmlParser
from data_collector.storage.file_storage import FileStorage


def test_html_parser_text():
    parser = HtmlParser("<html><body><h1>Hello</h1></body></html>")
    assert parser.text("h1") == "Hello"


def test_html_parser_attr():
    parser = HtmlParser('<a href="https://example.com">Link</a>')
    assert parser.attr("a", "href") == "https://example.com"


def test_file_storage_json(tmp_path, monkeypatch):
    monkeypatch.setattr("data_collector.storage.file_storage.DATA_DIR", tmp_path)
    storage = FileStorage()
    path = storage.save_json({"key": "value"}, "test.json")
    assert path.exists()


def test_file_storage_csv(tmp_path, monkeypatch):
    monkeypatch.setattr("data_collector.storage.file_storage.DATA_DIR", tmp_path)
    storage = FileStorage()
    rows = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
    path = storage.save_csv(rows, "test.csv")
    assert path.exists()


@patch("data_collector.collectors.http_collector.httpx.Client")
def test_http_collector_get_json(mock_client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"status": "ok"}
    mock_resp.raise_for_status.return_value = None
    mock_client.return_value.__enter__.return_value.get.return_value = mock_resp

    collector = HttpCollector()
    result = collector.get_json("https://example.com/api")
    assert result == {"status": "ok"}

"""Unit tests for core collector components."""
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
    path = storage.save_csv([{"a": 1, "b": 2}], "test.csv")
    assert path.exists()

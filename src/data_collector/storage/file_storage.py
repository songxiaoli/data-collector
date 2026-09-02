"""文件存储模块：将采集数据保存为 CSV / JSON"""
import json
import csv
from pathlib import Path
from datetime import datetime
from ..utils.logger import logger

DATA_DIR = Path(__file__).parents[4] / "data"


class FileStorage:
    def __init__(self, subdir: str = "raw"):
        self.base = DATA_DIR / subdir
        self.base.mkdir(parents=True, exist_ok=True)

    def save_json(self, data: any, filename: str = None) -> Path:
        filename = filename or f"{datetime.now():%Y%m%d_%H%M%S}.json"
        path = self.base / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"已保存 JSON → {path}")
        return path

    def save_csv(self, rows: list[dict], filename: str = None) -> Path:
        if not rows:
            logger.warning("没有数据可保存")
            return None
        filename = filename or f"{datetime.now():%Y%m%d_%H%M%S}.csv"
        path = self.base / filename
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        logger.info(f"已保存 CSV ({len(rows)} 行) → {path}")
        return path

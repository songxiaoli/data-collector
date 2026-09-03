"""File storage: save collected data as CSV or JSON."""
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
        logger.info(f"Saved JSON → {path}")
        return path

    def save_csv(self, rows: list[dict], filename: str = None) -> Path:
        if not rows:
            logger.warning("No data to save")
            return None
        filename = filename or f"{datetime.now():%Y%m%d_%H%M%S}.csv"
        path = self.base / filename
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        logger.info(f"Saved CSV ({len(rows)} rows) → {path}")
        return path

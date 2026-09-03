"""Entry point: example collection pipeline."""
from dotenv import load_dotenv
load_dotenv()

from .collectors.http_collector import HttpCollector
from .storage.file_storage import FileStorage
from .utils.logger import logger


def run():
    logger.info("=== data-collector starting ===")
    collector = HttpCollector()
    storage = FileStorage()

    # Example: fetch a public JSON API
    data = collector.get_json("https://jsonplaceholder.typicode.com/posts", params={"_limit": 10})
    storage.save_json(data, "sample_posts.json")

    logger.info(f"Done — {len(data)} records collected")


if __name__ == "__main__":
    run()

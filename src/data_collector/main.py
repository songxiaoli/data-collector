"""入口脚本：示例采集流程"""
from dotenv import load_dotenv
load_dotenv()

from .collectors.http_collector import HttpCollector
from .storage.file_storage import FileStorage
from .utils.logger import logger


def run():
    logger.info("=== data-collector 启动 ===")
    collector = HttpCollector()
    storage = FileStorage()

    # 示例：采集公开 JSON API
    data = collector.get_json("https://jsonplaceholder.typicode.com/posts", params={"_limit": 10})
    storage.save_json(data, "sample_posts.json")

    logger.info(f"采集完成，共 {len(data)} 条记录")


if __name__ == "__main__":
    run()

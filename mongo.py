from pathlib import Path
import os
from datetime import datetime, timezone
# pyrefly: ignore [missing-import]
from pymongo import MongoClient


import json
# pyrefly: ignore [missing-import]
from bson import ObjectId

BASE_DIR = Path(__file__).resolve().parent
DATASET_PATH = BASE_DIR / "CustomData" / "custom_news.csv"
MONGODATA_DIR = BASE_DIR / "MongoData"

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "dailykhabar")

client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]


def utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def export_to_json(collection_name, filename):
    """Mirror a MongoDB collection to a JSON file in MongoData."""
    try:
        data = list(db[collection_name].find())
        # Convert ObjectIds and Datetimes to strings for JSON serializability
        for item in data:
            if "_id" in item:
                item["_id"] = str(item["_id"])
            for k, v in item.items():
                if isinstance(v, datetime):
                    item[k] = v.isoformat()
        
        file_path = MONGODATA_DIR / filename
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error syncing {collection_name} to {filename}: {e}")

# Mapping of collections to their JSON files
COLLECTION_MAP = {
    "users": "users.json",
    "articles": "article_meta.json",
    "comments": "post_comments.json",
    "queries": "contact_queries.json",
    "user_activities": "user_activity.json",
    "categories": "categories.json"
}

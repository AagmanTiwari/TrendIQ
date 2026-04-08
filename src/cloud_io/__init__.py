import os
import sys
import pandas as pd
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, BulkWriteError
import logging

from src.constants import MONGODB_URL_KEY, MONGO_DATABASE_NAME
from src.exception import CustomException

logger = logging.getLogger(__name__)


class MongoIO:
    _client = None  # shared MongoClient across instances

    def __init__(self):
        if MongoIO._client is None:
            mongo_db_url = os.getenv(MONGODB_URL_KEY)
            if not mongo_db_url:
                raise Exception(
                    f"Environment variable '{MONGODB_URL_KEY}' is not set. "
                    f"Please add it to your .env file."
                )
            try:
                MongoIO._client = MongoClient(mongo_db_url)
                # Verify connection is alive
                MongoIO._client.admin.command("ping")
                logger.info("Connected to MongoDB successfully.")
            except ConnectionFailure as e:
                raise Exception(f"Could not connect to MongoDB: {e}")

        self.db = MongoIO._client[MONGO_DATABASE_NAME]

    def store_reviews(self, product_name: str, reviews: pd.DataFrame):
        """Insert reviews DataFrame into a MongoDB collection."""
        try:
            collection_name = product_name.replace(" ", "_")
            collection = self.db[collection_name]

            records = reviews.to_dict(orient="records")
            if records:
                collection.insert_many(records)
                logger.info(f"Inserted {len(records)} records into '{collection_name}'.")
            else:
                logger.warning("No records to insert.")

        except BulkWriteError as e:
            raise CustomException(e, sys)
        except Exception as e:
            raise CustomException(e, sys)

    def get_reviews(self, product_name: str) -> pd.DataFrame:
        """Fetch all reviews for a product from MongoDB as a DataFrame."""
        try:
            collection_name = product_name.replace(" ", "_")
            collection = self.db[collection_name]

            records = list(collection.find({}, {"_id": 0}))  # exclude Mongo _id field

            if not records:
                logger.warning(f"No records found in collection '{collection_name}'.")
                return pd.DataFrame()

            return pd.DataFrame(records)

        except Exception as e:
            raise CustomException(e, sys)
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from app.utils.config import settings

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.client: AsyncIOMotorClient = None
        self.db = None

    def connect(self):
        """Establishes connection to MongoDB."""
        logger.info(f"Connecting to MongoDB at: {settings.MONGODB_URI}")
        self.client = AsyncIOMotorClient(settings.MONGODB_URI)
        self.db = self.client[settings.DATABASE_NAME]
        logger.info(f"Successfully connected to database: {settings.DATABASE_NAME}")

    def disconnect(self):
        """Closes MongoDB connection."""
        if self.client:
            logger.info("Closing MongoDB connection...")
            self.client.close()
            self.client = None
            self.db = None
            logger.info("MongoDB connection closed.")

    def get_db(self):
        if self.db is None:
            raise RuntimeError("Database connection not initialized. Call connect() first.")
        return self.db

    # Helper methods to fetch collections
    def get_bills_collection(self):
        return self.get_db()["bills"]

    def get_dealers_collection(self):
        return self.get_db()["dealers"]

    def get_products_collection(self):
        return self.get_db()["products"]

    def get_processing_logs_collection(self):
        return self.get_db()["processing_logs"]

    def get_categories_collection(self):
        return self.get_db()["categories"]

    def get_users_collection(self):
        return self.get_db()["users"]

    def get_settings_collection(self):
        return self.get_db()["settings"]

# Singleton database manager instance
db_manager = DatabaseManager()

# FastAPI Dependency
async def get_database():
    return db_manager.get_db()

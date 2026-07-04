import asyncio
import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import router as api_router
from app.api.auth import router as auth_router
from app.api.settings import router as settings_router
from app.analytics.routes.analytics import router as analytics_router
from app.database.database import db_manager
from app.utils.config import settings
from app.utils.logger import setup_logger
from app.services.ocr_service import ocr_service

# Initialize Logging configuration
setup_logger()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logger.info("Starting up AI-powered Purchase Intelligence System Backend...")

    # 1. Establish connection to MongoDB
    try:
        db_manager.connect()
        # Seed default categories if collection is empty
        categories_collection = db_manager.get_categories_collection()
        count = await categories_collection.count_documents({})
        if count == 0:
            default_categories = [
                {"name": "Paint"},
                {"name": "Building Materials"},
                {"name": "Hardware"},
                {"name": "Electrical"}
            ]
            await categories_collection.insert_many(default_categories)
            logger.info("Successfully seeded default categories: Paint, Building Materials, Hardware, Electrical")
    except Exception as e:
        logger.error(f"Database connection or seeding failed at startup: {e}")
        
    # 2. Warm up OCR engine asynchronously in a background thread to prevent startup blocks
    try:
        await asyncio.to_thread(ocr_service.warmup)
    except Exception as e:
        logger.warning(f"Failed to warm up OCR engine on startup: {e}")
        
    yield
    
    # Shutdown actions
    logger.info("Shutting down AI-powered Purchase Intelligence System Backend...")
    db_manager.disconnect()

# Create FastAPI instance
app = FastAPI(
    title="AI-powered Purchase Intelligence System API",
    description="Backend service for ingestion, OCR, LLM extraction, and validation of paper bills.",
    version="1.0.0",
    lifespan=lifespan
)

# Set up CORS middleware
origins = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom middleware to log request processing/response time in terminal
@app.middleware("http")
async def log_response_time(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    logger.info(f"[{request.method}] {request.url.path} - Completed in {duration:.4f}s")
    response.headers["X-Response-Time"] = f"{duration:.4f}s"
    return response

# Register endpoints router
app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(api_router, tags=["Bill Ingestion"])
app.include_router(analytics_router)

@app.get("/", tags=["Health"])
def health_check():
    """Simple API health check endpoint."""
    return {
        "status": "healthy",
        "app_name": "AI-powered Purchase Intelligence System",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    import uvicorn
    # Start the dev server
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

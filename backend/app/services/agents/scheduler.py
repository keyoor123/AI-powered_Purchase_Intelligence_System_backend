import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.triggers.cron import CronTrigger
from pymongo import MongoClient

from app.utils.config import settings
from app.database.database import db_manager

logger = logging.getLogger(__name__)

async def run_monthly_report_job(user_id: str):
    """Importable task wrapper for APScheduler serialization."""
    from app.services.agents.monthly_report_agent import monthly_report_agent
    logger.info(f"Executing scheduled Monthly Report Agent job for user_id: {user_id}")
    try:
        success = await monthly_report_agent.run(user_id)
        logger.info(f"Monthly Report Agent execution result for user_id {user_id}: {success}")
    except Exception as e:
        logger.error(f"Error in scheduled Monthly Report job for user_id {user_id}: {e}", exc_info=True)

class AgentScheduler:
    def __init__(self):
        self.scheduler: AsyncIOScheduler = None
        self.client: MongoClient = None

    def start(self):
        """Initializes and starts the APScheduler with MongoDB JobStore."""
        if self.scheduler and self.scheduler.running:
            return

        logger.info("Initializing Agent APScheduler with MongoDB JobStore...")
        
        # Open a dedicated synchronous connection for PyMongo
        self.client = MongoClient(settings.MONGODB_URI)
        
        # Configure job stores to persist schedules in MongoDB
        jobstores = {
            'default': MongoDBJobStore(
                client=self.client,
                database=settings.DATABASE_NAME,
                collection="apscheduler_jobs"
            )
        }
        
        # Create scheduler instance
        self.scheduler = AsyncIOScheduler(jobstores=jobstores)
        self.scheduler.start()
        logger.info("Agent APScheduler started.")

    def shutdown(self):
        """Gracefully shuts down the scheduler."""
        if self.scheduler and self.scheduler.running:
            logger.info("Shutting down Agent APScheduler...")
            self.scheduler.shutdown()
            self.scheduler = None
            if self.client:
                self.client.close()
                self.client = None
            logger.info("Agent APScheduler shut down.")

    async def sync_user_agent_job(self, user_id: str, agent_type: str = "monthly_report"):
        """Syncs a single user's agent settings from MongoDB with APScheduler."""
        if not self.scheduler or not self.scheduler.running:
            logger.warning("Scheduler is not running. Sync skipped.")
            return

        job_id = f"{agent_type}_{user_id}"
        
        # Fetch configurations from MongoDB
        settings_col = db_manager.get_settings_collection()
        doc = await settings_col.find_one({
            "user_id": user_id, 
            "type": "agent_settings", 
            "value.agent_type": agent_type
        })
        
        # If no config exists, or agent is disabled: remove any existing job
        if not doc or not doc.get("value", {}).get("is_enabled", False):
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
                logger.info(f"Removed job '{job_id}' from scheduler (agent disabled/deleted).")
            return

        value = doc["value"]
        day_of_month = value.get("schedule_config", {}).get("day_of_month", 2)
        
        # Set up a Cron trigger to run on the selected day of every month at 9:00 AM server time
        trigger = CronTrigger(day=day_of_month, hour=9, minute=0)

        # Upsert APScheduler Job
        job = self.scheduler.get_job(job_id)
        if job:
            # Modify/reschedule if already exists
            self.scheduler.reschedule_job(job_id, trigger=trigger)
            logger.info(f"Rescheduled job '{job_id}' to run on day {day_of_month} of the month.")
        else:
            # Create new job
            self.scheduler.add_job(
                run_monthly_report_job,
                trigger=trigger,
                args=[user_id],
                id=job_id,
                replace_existing=True
            )
            logger.info(f"Added new job '{job_id}' to run on day {day_of_month} of the month.")

    async def sync_all_jobs(self):
        """Syncs all active agent configurations from MongoDB at startup."""
        if not self.scheduler or not self.scheduler.running:
            logger.warning("Scheduler is not running. All-jobs sync skipped.")
            return

        logger.info("Synchronizing all database agent configurations with APScheduler...")
        settings_col = db_manager.get_settings_collection()
        cursor = settings_col.find({"type": "agent_settings"})
        configs = await cursor.to_list(length=1000)
        
        synced_count = 0
        for doc in configs:
            user_id = doc.get("user_id")
            val = doc.get("value", {})
            agent_type = val.get("agent_type", "monthly_report")
            try:
                await self.sync_user_agent_job(user_id, agent_type)
                synced_count += 1
            except Exception as e:
                logger.error(f"Failed to sync scheduler job for user {user_id}: {e}")
                
        logger.info(f"Scheduler sync completed. Successfully synced {synced_count} jobs.")

# Global agent scheduler singleton
agent_scheduler = AgentScheduler()

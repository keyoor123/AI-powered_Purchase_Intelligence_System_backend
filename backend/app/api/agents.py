import logging
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorGridFSBucket
from bson import ObjectId

from app.database.database import get_database, db_manager
from app.utils.auth import get_current_user_id
from app.schemas.agents import (
    AgentSettingsResponseSchema,
    AgentSettingsUpdateSchema,
    EmailRecipientSchema,
    EmailRecipientUpdateSchema,
    EmailRecipientAddSchema
)
from app.services.agents.scheduler import agent_scheduler
from app.services.agents.monthly_report_agent import monthly_report_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents/monthly-report", tags=["Monthly Report Agent"])

@router.get("/settings", response_model=AgentSettingsResponseSchema)
async def get_agent_settings(
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Retrieves the Monthly Report Agent settings for the current user."""
    logger.info(f"Fetching monthly report agent settings for user: {user_id}")
    try:
        settings_col = db_manager.get_settings_collection()
        doc = await settings_col.find_one({
            "user_id": user_id, 
            "type": "agent_settings", 
            "value.agent_type": "monthly_report"
        })
        
        if doc:
            value = doc["value"]
            # If enabled, verify next_run is in the future. If not, recalculate it.
            if value.get("is_enabled", False):
                next_run = value.get("next_run")
                now_dt = datetime.utcnow()
                if not next_run or (isinstance(next_run, datetime) and next_run <= now_dt):
                    day_of_month = value.get("schedule_config", {}).get("day_of_month", 2)
                    try:
                        candidate = now_dt.replace(day=day_of_month, hour=9, minute=0, second=0, microsecond=0)
                        if candidate <= now_dt:
                            if now_dt.month == 12:
                                candidate = now_dt.replace(year=now_dt.year + 1, month=1, day=day_of_month)
                            else:
                                candidate = now_dt.replace(month=now_dt.month + 1, day=day_of_month)
                        value["next_run"] = candidate
                    except ValueError:
                        value["next_run"] = now_dt.replace(day=28, hour=9, minute=0, second=0, microsecond=0)
                    
                    await settings_col.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {"value": value, "updated_at": datetime.utcnow()}}
                    )
            return AgentSettingsResponseSchema(**value)

        # Default values if no config exists
        # Prefill default recipient email from user profile
        users_col = db_manager.get_users_collection()
        user = await users_col.find_one({"_id": ObjectId(user_id)})
        default_email = user["email"] if user else "user@example.com"

        default_settings = {
            "agent_type": "monthly_report",
            "is_enabled": True,
            "schedule_config": {"day_of_month": 2},
            "delivery_emails": [{"email": default_email, "is_enabled": True}],
            "last_run": None,
            "next_run": None
        }
        
        # Save default settings to DB
        await settings_col.insert_one({
            "user_id": user_id,
            "type": "agent_settings",
            "value": default_settings,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        })
        
        # Sync with scheduler
        await agent_scheduler.sync_user_agent_job(user_id, "monthly_report")
        
        return AgentSettingsResponseSchema(**default_settings)
    except Exception as e:
        logger.error(f"Failed to retrieve agent settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve agent settings: {str(e)}"
        )

@router.put("/settings", response_model=AgentSettingsResponseSchema)
async def update_agent_settings(
    payload: AgentSettingsUpdateSchema,
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Updates the agent toggle status or the monthly report schedule day."""
    logger.info(f"Updating agent settings for user: {user_id}")
    try:
        settings_col = db_manager.get_settings_collection()
        doc = await settings_col.find_one({
            "user_id": user_id, 
            "type": "agent_settings", 
            "value.agent_type": "monthly_report"
        })
        
        if not doc:
            # Trigger get endpoint to create default first
            await get_agent_settings(user_id, db)
            doc = await settings_col.find_one({
                "user_id": user_id, 
                "type": "agent_settings", 
                "value.agent_type": "monthly_report"
            })

        value = doc["value"]
        
        if payload.is_enabled is not None:
            value["is_enabled"] = payload.is_enabled
        if payload.day_of_month is not None:
            value["schedule_config"]["day_of_month"] = payload.day_of_month

        # Recalculate next run dynamically on update
        if value.get("is_enabled", False):
            day_of_month = value.get("schedule_config", {}).get("day_of_month", 2)
            now_dt = datetime.utcnow()
            try:
                candidate = now_dt.replace(day=day_of_month, hour=9, minute=0, second=0, microsecond=0)
                if candidate <= now_dt:
                    if now_dt.month == 12:
                        candidate = now_dt.replace(year=now_dt.year + 1, month=1, day=day_of_month)
                    else:
                        candidate = now_dt.replace(month=now_dt.month + 1, day=day_of_month)
                value["next_run"] = candidate
            except ValueError:
                value["next_run"] = now_dt.replace(day=28, hour=9, minute=0, second=0, microsecond=0)
        else:
            value["next_run"] = None

        await settings_col.update_one(
            {"_id": doc["_id"]},
            {"$set": {"value": value, "updated_at": datetime.utcnow()}}
        )

        # Sync the scheduler job dynamically
        await agent_scheduler.sync_user_agent_job(user_id, "monthly_report")

        return AgentSettingsResponseSchema(**value)
    except Exception as e:
        logger.error(f"Failed to update agent settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update agent settings: {str(e)}"
        )

@router.post("/emails", response_model=AgentSettingsResponseSchema)
async def add_recipient_email(
    payload: EmailRecipientAddSchema,
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Adds a new recipient email address to the delivery list (Maximum of 5 allowed)."""
    logger.info(f"Adding recipient email for user {user_id}: {payload.email}")
    try:
        settings_col = db_manager.get_settings_collection()
        doc = await settings_col.find_one({
            "user_id": user_id, 
            "type": "agent_settings", 
            "value.agent_type": "monthly_report"
        })
        
        if not doc:
            await get_agent_settings(user_id, db)
            doc = await settings_col.find_one({
                "user_id": user_id, 
                "type": "agent_settings", 
                "value.agent_type": "monthly_report"
            })

        value = doc["value"]
        emails_list = value.get("delivery_emails", [])
        
        # Check if already exists
        if any(e["email"].lower() == payload.email.lower() for e in emails_list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email address already exists in the recipient list."
            )
            
        # Restrict to maximum 5 additional email recipients
        # Wait, the list has [Primary User Email, Additional Email 1, Additional Email 2, ...]
        # Let's check: users are limited to 5 additional emails, meaning length <= 6 (1 primary + 5 additional).
        if len(emails_list) >= 6:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You have reached the maximum limit of 5 additional email recipients."
            )

        emails_list.append({"email": payload.email, "is_enabled": True})
        value["delivery_emails"] = emails_list

        await settings_col.update_one(
            {"_id": doc["_id"]},
            {"$set": {"value": value, "updated_at": datetime.utcnow()}}
        )

        return AgentSettingsResponseSchema(**value)
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Failed to add email: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add recipient email: {str(e)}"
        )

@router.put("/emails/toggle", response_model=AgentSettingsResponseSchema)
async def toggle_recipient_email(
    payload: EmailRecipientUpdateSchema,
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Enables or disables (toggles) a specific email recipient."""
    logger.info(f"Toggling email status for {payload.email}: {payload.is_enabled}")
    try:
        settings_col = db_manager.get_settings_collection()
        doc = await settings_col.find_one({
            "user_id": user_id, 
            "type": "agent_settings", 
            "value.agent_type": "monthly_report"
        })
        
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent settings not found."
            )

        value = doc["value"]
        emails_list = value.get("delivery_emails", [])
        
        found = False
        for e in emails_list:
            if e["email"].lower() == payload.email.lower():
                e["is_enabled"] = payload.is_enabled
                found = True
                break
                
        if not found:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email address not found in recipient list."
            )

        value["delivery_emails"] = emails_list
        await settings_col.update_one(
            {"_id": doc["_id"]},
            {"$set": {"value": value, "updated_at": datetime.utcnow()}}
        )

        return AgentSettingsResponseSchema(**value)
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Failed to toggle email: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to toggle recipient email: {str(e)}"
        )

@router.delete("/emails/{email}", response_model=AgentSettingsResponseSchema)
async def remove_recipient_email(
    email: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Deletes an email recipient address from the delivery list."""
    logger.info(f"Removing recipient email: {email}")
    try:
        settings_col = db_manager.get_settings_collection()
        doc = await settings_col.find_one({
            "user_id": user_id, 
            "type": "agent_settings", 
            "value.agent_type": "monthly_report"
        })
        
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent settings not found."
            )

        value = doc["value"]
        emails_list = value.get("delivery_emails", [])
        
        new_list = [e for e in emails_list if e["email"].lower() != email.lower()]
        
        if len(new_list) == len(emails_list):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email address not found in recipient list."
            )

        value["delivery_emails"] = new_list
        await settings_col.update_one(
            {"_id": doc["_id"]},
            {"$set": {"value": value, "updated_at": datetime.utcnow()}}
        )

        return AgentSettingsResponseSchema(**value)
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Failed to remove email: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove recipient email: {str(e)}"
        )

@router.post("/trigger")
async def trigger_agent_manually(
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Manually triggers the Monthly Report Agent immediately (runs for the previous month)."""
    logger.info(f"Manually triggering MonthlyReportAgent for user: {user_id}")
    try:
        # Run report agent synchronously (since requested from API directly)
        success = await monthly_report_agent.run(user_id)
        if success:
            return {"status": "success", "message": "Monthly Report compiled, saved, and dispatched successfully."}
        else:
            return {"status": "failed", "message": "Monthly Report failed to compile. Check execution logs or verify you have bills uploaded."}
    except Exception as e:
        logger.error(f"Manual agent trigger failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent trigger failed: {str(e)}"
        )

@router.get("/logs")
async def get_execution_logs(
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Retrieves execution audit logs for this user's monthly report agent."""
    logger.info(f"Fetching agent execution logs for user: {user_id}")
    try:
        cursor = db["agent_execution_logs"].find({"user_id": user_id, "agent_type": "monthly_report"}).sort("run_at", -1)
        logs = await cursor.to_list(length=100)
        
        # Serialize ObjectIds to strings
        for log in logs:
            log["_id"] = str(log["_id"])
            if log.get("pdf_grid_file_id"):
                log["pdf_grid_file_id"] = str(log["pdf_grid_file_id"])
            if log.get("run_at"):
                log["run_at"] = log["run_at"].isoformat()
        return logs
    except Exception as e:
        logger.error(f"Failed to retrieve execution logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch execution logs: {str(e)}"
        )

@router.get("/reports/{file_id}")
async def download_report_pdf(
    file_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Downloads a generated PDF report from GridFS using the GridFS File ID."""
    logger.info(f"Downloading report PDF from GridFS: {file_id}")
    try:
        fs = AsyncIOMotorGridFSBucket(db)
        
        # Fetch file metadata to check ownership and get filename
        cursor = fs.find({"_id": ObjectId(file_id)})
        files = await cursor.to_list(length=1)
        if not files:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report PDF not found."
            )
            
        file_meta = files[0]
        file_user_id = file_meta.get("metadata", {}).get("user_id")
        
        if file_user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to download this report."
            )

        filename = file_meta.get("filename", f"report_{file_id}.pdf")
        
        # Read from GridFS stream and return StreamingResponse
        grid_out = await fs.open_download_stream(ObjectId(file_id))
        
        async def stream_file():
            chunk_size = 4096
            while True:
                chunk = await grid_out.read(chunk_size)
                if not chunk:
                    break
                yield chunk

        return StreamingResponse(
            stream_file(),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Failed to download report PDF: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download report PDF: {str(e)}"
        )

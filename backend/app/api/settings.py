import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database.database import get_database, db_manager
from app.models.models import SettingsDocument
from app.schemas.settings import OrganizationSettingsSchema, ProfileSettingsSchema
from app.utils.auth import get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["Configuration & Settings"])


@router.get("/organization", response_model=OrganizationSettingsSchema)
async def get_organization_settings(
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Returns the organization settings for the current logged-in user.
    Returns default values if no custom settings exist yet in the database.
    """
    logger.info(f"Fetching organization settings for user: {user_id}")
    try:
        settings_collection = db_manager.get_settings_collection()
        doc = await settings_collection.find_one({"user_id": user_id, "type": "organization"})
        
        if doc:
            settings_val = doc["value"].copy()
            settings_val["is_onboarded"] = True
            return OrganizationSettingsSchema(**settings_val)
            
        # Default seeding response if none exists
        return OrganizationSettingsSchema(
            org_name="Acme Procurement",
            currency="Indian Rupee (₹)",
            timezone="Asia/Kolkata",
            date_format="10 Apr 2026",
            is_onboarded=False
        )
    except Exception as e:
        logger.error(f"Failed to fetch organization settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch organization settings: {str(e)}"
        )


@router.put("/organization", response_model=OrganizationSettingsSchema)
async def update_organization_settings(
    payload: OrganizationSettingsSchema,
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Upserts (saves or updates) organization settings for the current user.
    """
    logger.info(f"Saving organization settings for user: {user_id}")
    try:
        settings_collection = db_manager.get_settings_collection()
        
        save_val = payload.model_dump()
        save_val["is_onboarded"] = True
        
        await settings_collection.update_one(
            {"user_id": user_id, "type": "organization"},
            {
                "$set": {
                    "value": save_val,
                    "updated_at": datetime.utcnow()
                },
                "$setOnInsert": {
                    "created_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        logger.info(f"Successfully updated organization settings for user: {user_id}")
        payload.is_onboarded = True
        return payload
    except Exception as e:
        logger.error(f"Failed to save organization settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save organization settings: {str(e)}"
        )


@router.get("/profile", response_model=ProfileSettingsSchema)
async def get_profile_settings(
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Returns the user profile display preferences.
    Returns default values if no custom settings exist yet in the database.
    """
    logger.info(f"Fetching user profile settings for user: {user_id}")
    try:
        settings_collection = db_manager.get_settings_collection()
        doc = await settings_collection.find_one({"user_id": user_id, "type": "profile"})
        
        if doc:
            return ProfileSettingsSchema(**doc["value"])
            
        # Fetch user's actual registration details for default email / display_name
        users_collection = db_manager.get_users_collection()
        from bson import ObjectId
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
        
        default_name = user["display_name"] if user else "Aarav Mehta"
        default_email = user["email"] if user else "aarav@acme.in.managed"
        
        # Default seeding response if none exists
        return ProfileSettingsSchema(
            display_name=default_name,
            email=default_email,
            locale="English (India)",
            time_format="24-hour"
        )
    except Exception as e:
        logger.error(f"Failed to fetch user profile settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch user profile settings: {str(e)}"
        )


@router.put("/profile", response_model=ProfileSettingsSchema)
async def update_profile_settings(
    payload: ProfileSettingsSchema,
    user_id: str = Depends(get_current_user_id),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Upserts (saves or updates) user profile display preferences for the current user.
    """
    logger.info(f"Saving user profile settings for user: {user_id}")
    try:
        settings_collection = db_manager.get_settings_collection()
        
        await settings_collection.update_one(
            {"user_id": user_id, "type": "profile"},
            {
                "$set": {
                    "value": payload.model_dump(),
                    "updated_at": datetime.utcnow()
                },
                "$setOnInsert": {
                    "created_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        logger.info(f"Successfully updated user profile settings for user: {user_id}")
        return payload
    except Exception as e:
        logger.error(f"Failed to save user profile settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save user profile settings: {str(e)}"
        )

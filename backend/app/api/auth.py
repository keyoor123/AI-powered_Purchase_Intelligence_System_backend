import logging
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId

from app.database.database import get_database, db_manager
from app.models.models import UserDocument, CategoryDocument
from app.schemas.auth import (
    UserSignupSchema,
    UserLoginSchema,
    ForgotPasswordSchema,
    ResetPasswordSchema,
    TokenResponseSchema
)
from app.utils.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    decode_access_token
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["User Authentication"])


@router.post("/signup", response_model=TokenResponseSchema, status_code=status.HTTP_201_CREATED)
async def signup(signup_payload: UserSignupSchema, db: AsyncIOMotorDatabase = Depends(get_database)):
    """
    Registers a new user, hashes their password, seeds initial default categories,
    and returns a JWT access token.
    """
    email = signup_payload.email.strip().lower()
    logger.info(f"Received signup request for email: {email}")

    try:
        users_collection = db_manager.get_users_collection()
        
        # Check if user already exists
        existing_user = await users_collection.find_one({"email": email})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This email address is already registered. Please sign in instead."
            )

        # Hash the password and save
        hashed_password = get_password_hash(signup_payload.password)
        new_user = UserDocument(
            email=email,
            hashed_password=hashed_password,
            display_name=signup_payload.display_name.strip()
        )
        
        res = await users_collection.insert_one(new_user.model_dump(by_alias=True, exclude={"id"}))
        user_id = str(res.inserted_id)
        logger.info(f"User registered successfully. Assigned ID: {user_id}")

        # Seed initial default categories specifically for this new user ID
        categories_collection = db_manager.get_categories_collection()
        default_categories = [
            CategoryDocument(user_id=user_id, name="Paint"),
            CategoryDocument(user_id=user_id, name="Building Materials"),
            CategoryDocument(user_id=user_id, name="Hardware"),
            CategoryDocument(user_id=user_id, name="Electrical")
        ]
        await categories_collection.insert_many([c.model_dump(by_alias=True, exclude={"id"}) for c in default_categories])
        logger.info(f"Seeded 4 default categories for user: {user_id}")

        # Generate JWT access token
        access_token = create_access_token(data={"sub": user_id})
        
        return TokenResponseSchema(
            access_token=access_token,
            token_type="bearer",
            user={
                "id": user_id,
                "email": email,
                "display_name": signup_payload.display_name
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )


@router.post("/login", response_model=TokenResponseSchema)
async def login_form(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncIOMotorDatabase = Depends(get_database)):
    """
    Standard OAuth2 Form-based login endpoint. Used by Swagger UI authorize lock.
    """
    email = form_data.username.strip().lower()
    logger.info(f"OAuth2 form login attempt for: {email}")

    users_collection = db_manager.get_users_collection()
    user = await users_collection.find_one({"email": email})
    
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = str(user["_id"])
    access_token = create_access_token(data={"sub": user_id})

    return TokenResponseSchema(
        access_token=access_token,
        token_type="bearer",
        user={
            "id": user_id,
            "email": user["email"],
            "display_name": user["display_name"]
        }
    )


@router.post("/login/json", response_model=TokenResponseSchema)
async def login_json(login_payload: UserLoginSchema, db: AsyncIOMotorDatabase = Depends(get_database)):
    """
    JSON-based login endpoint. Ideal for REST clients and frontend integrations.
    """
    email = login_payload.email.strip().lower()
    logger.info(f"JSON login attempt for: {email}")

    users_collection = db_manager.get_users_collection()
    user = await users_collection.find_one({"email": email})
    
    if not user or not verify_password(login_payload.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = str(user["_id"])
    access_token = create_access_token(data={"sub": user_id})

    return TokenResponseSchema(
        access_token=access_token,
        token_type="bearer",
        user={
            "id": user_id,
            "email": user["email"],
            "display_name": user["display_name"]
        }
    )


@router.post("/forgot-password")
async def forgot_password(forgot_payload: ForgotPasswordSchema, db: AsyncIOMotorDatabase = Depends(get_database)):
    """
    Generates a password reset token and simulates sending a reset link to the terminal.
    """
    email = forgot_payload.email.strip().lower()
    logger.info(f"Password reset request received for email: {email}")

    users_collection = db_manager.get_users_collection()
    user = await users_collection.find_one({"email": email})
    
    # Standard security practice: return same success message even if user does not exist
    success_msg = "If the email is registered in our system, a password reset link has been sent."
    
    if not user:
        logger.warning(f"Password reset requested for non-existent email: {email}")
        return {"message": success_msg}

    user_id = str(user["_id"])
    
    # Create a signed JWT token with a short expiration time (e.g., 15 minutes)
    reset_token = create_access_token(data={"sub": user_id, "action": "reset_password"}, expires_delta=None)

    # In a real environment, we would email this link. We will log it here.
    reset_link = f"http://localhost:8000/auth/reset-password?token={reset_token}"
    logger.info("\n==================================================")
    logger.info(f"PASSWORD RESET LINK FOR {email}:")
    logger.info(reset_link)
    logger.info("==================================================\n")

    return {
        "message": success_msg,
        "debug_token": reset_token  # Returned for testing/debugging purposes
    }


@router.post("/reset-password")
async def reset_password(reset_payload: ResetPasswordSchema, db: AsyncIOMotorDatabase = Depends(get_database)):
    """
    Verifies a reset token and updates the user's password.
    """
    token = reset_payload.token
    logger.info("Validating password reset token...")

    payload = decode_access_token(token)
    if not payload or payload.get("action") != "reset_password":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token."
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid token content."
        )

    try:
        users_collection = db_manager.get_users_collection()
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found."
            )

        hashed_password = get_password_hash(reset_payload.new_password)
        await users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"hashed_password": hashed_password}}
        )
        logger.info(f"Password reset successfully for user ID: {user_id}")
        
        return {"success": True, "message": "Password reset completed successfully. You can now log in."}
    except Exception as e:
        logger.error(f"Failed to reset password: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Password reset failed: {str(e)}"
        )

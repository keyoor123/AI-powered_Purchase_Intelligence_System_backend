import logging
import random
from datetime import datetime, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Response
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
    TokenResponseSchema,
    VerifyEmailSchema,
    ResendVerificationSchema
)
from app.utils.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    decode_access_token
)
from app.utils.config import settings
from app.utils.mailer import send_otp_email
from app.utils.security_limiter import verify_ip_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["User Authentication"])


@router.post("/signup", status_code=status.HTTP_201_CREATED, dependencies=[Depends(verify_ip_rate_limit)])
async def signup(response: Response, signup_payload: UserSignupSchema, db: AsyncIOMotorDatabase = Depends(get_database)):
    """
    Registers a new user as unverified, generates a 6-digit verification OTP,
    seeds default categories, and returns verification prompt details.
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

        # Generate 6-digit verification code
        verification_code = f"{random.randint(100000, 999999)}"
        verification_expires_at = datetime.utcnow() + timedelta(minutes=15)

        # Hash the password and save
        hashed_password = get_password_hash(signup_payload.password)
        new_user = UserDocument(
            email=email,
            hashed_password=hashed_password,
            display_name=signup_payload.display_name.strip(),
            is_verified=False,
            verification_code=verification_code,
            verification_code_expires_at=verification_expires_at
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

        # Log OTP code to backend terminal/logs for backup/debugging
        logger.info("\n==================================================")
        logger.info(f"EMAIL VERIFICATION OTP FOR {email}: {verification_code}")
        logger.info("==================================================\n")

        # Send real OTP email
        try:
            await send_otp_email(email, verification_code)
        except Exception as e:
            logger.error(f"Failed to send email verification: {e}")
            # Roll back registration changes
            await users_collection.delete_one({"_id": ObjectId(user_id)})
            await categories_collection.delete_many({"user_id": user_id})
            logger.info(f"Rolled back registration for user {email} due to SMTP delivery failure.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send verification email. Please try again after some time."
            )

        return {
            "success": True,
            "message": "Registration successful. A 6-digit OTP code has been sent to your email address.",
            "email": email
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )


async def record_failed_login_attempt(user_id: ObjectId, current_failed_attempts: int, users_collection) -> int:
    new_attempts = current_failed_attempts + 1
    update_data = {"failed_login_attempts": new_attempts}
    if new_attempts >= 5:
        update_data["lockout_until"] = datetime.utcnow() + timedelta(minutes=15)
        update_data["failed_login_attempts"] = 5
        new_attempts = 5
    
    await users_collection.update_one(
        {"_id": user_id},
        {"$set": update_data}
    )
    return new_attempts

async def reset_login_attempts(user_id: ObjectId, users_collection):
    await users_collection.update_one(
        {"_id": user_id},
        {"$set": {"failed_login_attempts": 0, "lockout_until": None}}
    )

def check_account_lockout(user):
    if user.get("lockout_until"):
        lockout_until = user["lockout_until"]
        if lockout_until.tzinfo is not None:
            lockout_until = lockout_until.replace(tzinfo=None)
        if datetime.utcnow() < lockout_until:
            time_left = int((lockout_until - datetime.utcnow()).total_seconds() / 60) + 1
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This account is temporarily locked due to too many failed attempts. Try again after {time_left} minutes."
            )

@router.post("/login", response_model=TokenResponseSchema, dependencies=[Depends(verify_ip_rate_limit)])
async def login_form(response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncIOMotorDatabase = Depends(get_database)):
    """
    Standard OAuth2 Form-based login endpoint. Used by Swagger UI authorize lock.
    Sets access token cookie and returns token in response body.
    """
    email = form_data.username.strip().lower()
    logger.info(f"OAuth2 form login attempt for: {email}")

    users_collection = db_manager.get_users_collection()
    user = await users_collection.find_one({"email": email})
    
    if user:
        check_account_lockout(user)
    
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        if user:
            attempts = await record_failed_login_attempt(user["_id"], user.get("failed_login_attempts", 0), users_collection)
            if attempts >= 5:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Incorrect email or password. This account is now locked for 15 minutes."
                )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    await reset_login_attempts(user["_id"], users_collection)

    if user.get("is_verified") is False:
        # Automatically generate and send verification code during unverified login
        verification_code = f"{random.randint(100000, 999999)}"
        verification_expires_at = datetime.utcnow() + timedelta(minutes=15)
        
        await users_collection.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "verification_code": verification_code,
                    "verification_code_expires_at": verification_expires_at
                }
            }
        )
        
        logger.info(f"Unverified OAuth2 login: Generated new OTP for {email}: {verification_code}")
        
        try:
            await send_otp_email(email, verification_code)
        except Exception as e:
            logger.error(f"Failed to send email verification during login: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Email address not verified. Failed to send verification email. Please try again after some time."
            )
            
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email address not verified. A verification code has been sent to your email."
        )

    user_id = str(user["_id"])
    access_token = create_access_token(data={"sub": user_id})

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.APP_ENV != "development",
        samesite="lax",
        max_age=7 * 24 * 60 * 60
    )

    return TokenResponseSchema(
        access_token=access_token,
        token_type="bearer",
        user={
            "id": user_id,
            "email": user["email"],
            "display_name": user["display_name"]
        }
    )


@router.post("/login/json", response_model=TokenResponseSchema, dependencies=[Depends(verify_ip_rate_limit)])
async def login_json(response: Response, login_payload: UserLoginSchema, db: AsyncIOMotorDatabase = Depends(get_database)):
    """
    JSON-based login endpoint. Ideal for REST clients and frontend integrations.
    Sets access token in HttpOnly cookie and clears it from response body.
    """
    email = login_payload.email.strip().lower()
    logger.info(f"JSON login attempt for: {email}")

    users_collection = db_manager.get_users_collection()
    user = await users_collection.find_one({"email": email})
    
    if user:
        check_account_lockout(user)
    
    if not user or not verify_password(login_payload.password, user["hashed_password"]):
        if user:
            attempts = await record_failed_login_attempt(user["_id"], user.get("failed_login_attempts", 0), users_collection)
            if attempts >= 5:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Incorrect email or password. This account is now locked for 15 minutes."
                )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    await reset_login_attempts(user["_id"], users_collection)

    if user.get("is_verified") is False:
        # Automatically generate and send verification code during unverified login
        verification_code = f"{random.randint(100000, 999999)}"
        verification_expires_at = datetime.utcnow() + timedelta(minutes=15)
        
        await users_collection.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "verification_code": verification_code,
                    "verification_code_expires_at": verification_expires_at
                }
            }
        )
        
        logger.info(f"Unverified JSON login: Generated new OTP for {email}: {verification_code}")
        
        try:
            await send_otp_email(email, verification_code)
        except Exception as e:
            logger.error(f"Failed to send email verification during login: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Email address not verified. Failed to send verification email. Please try again after some time."
            )
            
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email address not verified. A verification code has been sent to your email."
        )

    user_id = str(user["_id"])
    access_token = create_access_token(data={"sub": user_id})

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.APP_ENV != "development",
        samesite="lax",
        max_age=7 * 24 * 60 * 60
    )

    return TokenResponseSchema(
        access_token="",
        token_type="bearer",
        user={
            "id": user_id,
            "email": user["email"],
            "display_name": user["display_name"]
        }
    )


@router.post("/verify-email", response_model=TokenResponseSchema, dependencies=[Depends(verify_ip_rate_limit)])
async def verify_email(response: Response, verify_payload: VerifyEmailSchema, db: AsyncIOMotorDatabase = Depends(get_database)):
    """
    Validates a 6-digit OTP code for a user's email.
    If valid, sets user status to verified, issues access token cookie, and returns user data.
    """
    email = verify_payload.email.strip().lower()
    code = verify_payload.code.strip()
    logger.info(f"Email verification attempt for: {email}")

    users_collection = db_manager.get_users_collection()
    user = await users_collection.find_one({"email": email})
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found."
        )

    # Check if already verified
    if user.get("is_verified") is True:
        logger.info(f"User {email} is already verified.")
        # Generate token and login anyway as convenience
        user_id = str(user["_id"])
        access_token = create_access_token(data={"sub": user_id})
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=settings.APP_ENV != "development",
            samesite="lax",
            max_age=7 * 24 * 60 * 60
        )
        return TokenResponseSchema(
            access_token="",
            token_type="bearer",
            user={
                "id": user_id,
                "email": user["email"],
                "display_name": user["display_name"]
            }
        )

    # Validate code
    stored_code = user.get("verification_code")
    expires_at = user.get("verification_code_expires_at")
    
    if not stored_code or stored_code != code:
        failed_attempts = user.get("failed_otp_attempts", 0) + 1
        if failed_attempts >= 5:
            # Invalidate the OTP
            await users_collection.update_one(
                {"_id": user["_id"]},
                {
                    "$set": {"failed_otp_attempts": 0},
                    "$unset": {"verification_code": "", "verification_code_expires_at": ""}
                }
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Too many incorrect attempts. This OTP has been invalidated. Please request a new verification code."
            )
        else:
            await users_collection.update_one(
                {"_id": user["_id"]},
                {"$set": {"failed_otp_attempts": failed_attempts}}
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid verification code. Remaining attempts: {5 - failed_attempts}."
            )

    if expires_at and expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code has expired. Please request a new one."
        )

    # Set as verified and clear code
    user_id = str(user["_id"])
    await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {
            "$set": {"is_verified": True, "failed_otp_attempts": 0},
            "$unset": {"verification_code": "", "verification_code_expires_at": ""}
        }
    )
    logger.info(f"User {email} successfully verified.")

    # Issue access token
    access_token = create_access_token(data={"sub": user_id})
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.APP_ENV != "development",
        samesite="lax",
        max_age=7 * 24 * 60 * 60
    )

    return TokenResponseSchema(
        access_token="",
        token_type="bearer",
        user={
            "id": user_id,
            "email": user["email"],
            "display_name": user["display_name"]
        }
    )


@router.post("/resend-verification", dependencies=[Depends(verify_ip_rate_limit)])
async def resend_verification(payload: ResendVerificationSchema, db: AsyncIOMotorDatabase = Depends(get_database)):
    """
    Generates and logs a new 6-digit OTP verification code for an unverified user.
    """
    email = payload.email.strip().lower()
    logger.info(f"Resend verification request for: {email}")

    users_collection = db_manager.get_users_collection()
    user = await users_collection.find_one({"email": email})
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found."
        )

    if user.get("is_verified") is True:
        return {"success": True, "message": "Account is already verified."}

    # Generate new verification code
    verification_code = f"{random.randint(100000, 999999)}"
    verification_expires_at = datetime.utcnow() + timedelta(minutes=15)

    await users_collection.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "verification_code": verification_code,
                "verification_code_expires_at": verification_expires_at
            }
        }
    )

    # Log OTP code to backend terminal/logs for backup/debugging
    logger.info("\n==================================================")
    logger.info(f"NEW EMAIL VERIFICATION OTP FOR {email}: {verification_code}")
    logger.info("==================================================\n")

    # Send real OTP email
    try:
        await send_otp_email(email, verification_code)
    except Exception as e:
        logger.error(f"Failed to send email verification: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send verification email. Please try again after some time."
        )

    return {
        "success": True,
        "message": "A new verification OTP code has been sent to your email address."
    }


@router.post("/logout")
async def logout(response: Response):
    """
    Clears the access_token HttpOnly cookie.
    """
    response.delete_cookie(
        key="access_token",
        httponly=True,
        secure=settings.APP_ENV != "development",
        samesite="lax"
    )
    return {"message": "Logged out successfully"}


@router.post("/forgot-password", dependencies=[Depends(verify_ip_rate_limit)])
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

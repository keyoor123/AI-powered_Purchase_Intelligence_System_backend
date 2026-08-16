# Rate Limiting & Brute-Force Protection Plan

## Overview
Implement defense-in-depth security controls to prevent brute-force attacks and rate limit abuse on all backend authentication endpoints.

## Project Type
BACKEND

## Success Criteria
1. **Login & OTP Rate Limiting**: Limit clients to a maximum of 5 login requests or verification resends per minute per IP address.
2. **Account Lockout**: After 5 failed password attempts on an email address, temporarily lock the account for 15 minutes.
3. **OTP Attempt Limits**: Allow only 5 incorrect OTP verification attempts. On the 5th failed attempt, invalidate the OTP code and require the user to request a new one.
4. **Resiliency**: Account lockout and OTP attempts must be persisted in the MongoDB database so that blocks cannot be bypassed by restarting the server.

## Tech Stack
* Python standard library (`asyncio`, `datetime`)
* MongoDB (for persistent lockout state)

## File Structure
```plaintext
backend/
├── app/
│   ├── utils/
│   │   └── security_limiter.py  # [NEW] In-memory IP/endpoint rate-limiting middleware
│   ├── models/
│   │   └── models.py            # Modified: Add failed_login_attempts, lockout_until, and failed_otp_attempts
│   ├── api/
│   │   └── auth.py              # Modified: Integrate IP limiting, password lockouts, and OTP limits
│   ├── main.py                  # Modified: Register IP limiter middleware and database migrations
```

## Task Breakdown

### Task 1: Update Database Models & Migration
* **Agent**: `database-architect`
* **Skills**: `database-design`
* **File**: [models.py](file:///c:/Users/91742/OneDrive/Desktop/AI-powered_Purchase_Intelligence_System/backend/app/models/models.py)
* **Actions**:
  * Add the following fields to `UserDocument`:
    * `failed_login_attempts: int = 0`
    * `lockout_until: Optional[datetime] = None`
    * `failed_otp_attempts: int = 0`
  * Add a lifespan migration in `backend/app/main.py` to seed these fields for legacy records (set defaults).

### Task 2: Create In-Memory IP Rate Limiter
* **Agent**: `backend-specialist`
* **Skills**: `python-patterns`
* **File**: [security_limiter.py](file:///c:/Users/91742/OneDrive/Desktop/AI-powered_Purchase_Intelligence_System/backend/app/utils/security_limiter.py) [NEW]
* **Actions**:
  * Implement an in-memory sliding window rate limiter tracking request timestamps per client IP.
  * Define limits:
    * Sensitive routes (login, forgot-password, resend-verification): Max 5 requests per minute.
    * General health/CORS requests: Default limits.
  * Create a custom decorator or class to be used as a FastAPI dependency.

### Task 3: Implement Account Lockout & OTP Invalidation
* **Agent**: `backend-specialist`
* **Skills**: `api-patterns`
* **File**: [auth.py](file:///c:/Users/91742/OneDrive/Desktop/AI-powered_Purchase_Intelligence_System/backend/app/api/auth.py)
* **Actions**:
  * **Login validation**:
    * Check if `lockout_until` is active. If active, raise HTTP 403: `"This account is temporarily locked due to too many failed attempts. Try again after {lockout_remaining} minutes."`
    * On incorrect password, increment `failed_login_attempts`. If it reaches 5, set `lockout_until = datetime.utcnow() + 15 minutes` and lock the account.
    * On successful password verify, reset `failed_login_attempts = 0` and `lockout_until = None`.
  * **OTP verification (`/verify-email`)**:
    * If OTP code is wrong, increment `failed_otp_attempts`.
    * If `failed_otp_attempts >= 5`, set `verification_code = None`, `verification_code_expires_at = None`, and `failed_otp_attempts = 0`. Raise HTTP 400: `"Too many incorrect attempts. This OTP has been invalidated. Please request a new verification code."`
    * On successful OTP code verify, reset `failed_otp_attempts = 0`.

---

## Phase X: Verification
* [x] Run `python -X utf8 .agents/scripts/checklist.py .`
* [x] Verify that hitting `/auth/login/json` 6 times in a row within 1 minute returns an HTTP 429 Too Many Requests error.
* [x] Verify that entering 5 wrong passwords locks the account for 15 minutes.
* [x] Verify that entering 5 wrong OTPs invalidates the code.

## ✅ PHASE X COMPLETE
- Lint: ✅ Pass
- Security: ✅ No critical issues
- Build: ✅ Success
- Date: 2026-08-15

# Email Verification Implementation Plan

## Overview
Implement email verification for new user signups. Unverified users will not be allowed to access protected features. Authentication flow will be: Signup → Email verification (once) → Account becomes verified → Normal login (email + password) afterward.

## Project Type
WEB / BACKEND

## Success Criteria
1. Users register with email, password, and display name.
2. Upon registration, a 6-digit OTP verification code is generated, stored in the DB, and logged in the console (for local testing).
3. The user is redirected to a verification screen to enter the OTP.
4. Protected API endpoints block access to unverified users (by not issuing session tokens until verified).
5. Logging in with an unverified account returns a clear error (e.g., HTTP 403) instructing the user to verify.
6. Once verified, the user can log in normally via email/password without an OTP.

## Tech Stack
* Backend: FastAPI (Python), Motor (Async MongoDB), PyJWT (JWT tokens), Pydantic v2
* Frontend: React, TypeScript, Vite, Vanilla CSS

## File Structure
```plaintext
backend/
├── app/
│   ├── api/
│   │   └── auth.py         # Modified: signup flow, login checks, new verification endpoints
│   ├── models/
│   │   └── models.py       # Modified: UserDocument model with verification fields
│   ├── schemas/
│   │   └── auth.py         # Modified: Verification schema
│   ├── main.py             # Modified: Added database migration on startup
frontend/
├── src/
│   ├── services/
│   │   └── api.ts          # Modified: new API client methods for verification
│   ├── context/
│   │   └── AuthContext.tsx # Modified: handle verification signup/login states
│   ├── pages/
│   │   └── LoginSignup.tsx # Modified: verification verification OTP UI screen
```

## Task Breakdown

### Task 1: Update Database Schema & Run Migration
* **Agent**: `database-architect`
* **Skills**: `database-design`
* **Files**: 
  * [models.py](file:///c:/Users/91742/OneDrive/Desktop/AI-powered_Purchase_Intelligence_System/backend/app/models/models.py)
  * [main.py](file:///c:/Users/91742/OneDrive/Desktop/AI-powered_Purchase_Intelligence_System/backend/app/main.py)
* **Input**: Current `UserDocument` and backend startup lifespan hook.
* **Output**: 
  * `UserDocument` containing `is_verified` (bool), `verification_code` (str), and `verification_code_expires_at` (datetime).
  * Startup migration code in `main.py` that updates any existing database users missing the `is_verified` key to `is_verified: False`.
* **Verify**: Run server startup and verify existing users in MongoDB receive `is_verified: false`.

### Task 2: Implement Backend Signup & Verification Routes
* **Agent**: `backend-specialist`
* **Skills**: `python-patterns`
* **File**: [auth.py](file:///c:/Users/91742/OneDrive/Desktop/AI-powered_Purchase_Intelligence_System/backend/app/api/auth.py)
* **Input**: Current authentication router
* **Output**:
  * Signup `/signup` generates a 6-digit OTP and logs it to console instead of returning a cookie token.
  * Login `/login` and `/login/json` check `is_verified` and return HTTP 403 if false.
  * New `/verify-email` endpoint validating the OTP code and issuing the JWT session cookie.
  * New `/resend-verification` endpoint to generate and log a new OTP code.
* **Verify**: Test endpoints using curl or swagger documentation once running.

### Task 3: Update Frontend API Client and Auth Context
* **Agent**: `frontend-specialist`
* **Skills**: `nextjs-react-expert`
* **Files**:
  * [api.ts](file:///c:/Users/91742/OneDrive/Desktop/frontend_AI-powered_Purchase_Intelligence_System/src/services/api.ts)
  * [AuthContext.tsx](file:///c:/Users/91742/OneDrive/Desktop/frontend_AI-powered_Purchase_Intelligence_System/src/context/AuthContext.tsx)
* **Input**: Current frontend api services and auth state context
* **Output**:
  * API service contains functions for `verifyEmail` and `resendVerification`.
  * `AuthContext` updated to handle signup without immediate login, and handle the transition to the verification state.
* **Verify**: Ensure code compiles without TypeScript errors.

### Task 4: Create Frontend OTP Verification Screen
* **Agent**: `frontend-specialist`
* **Skills**: `frontend-design`
* **File**: [LoginSignup.tsx](file:///c:/Users/91742/OneDrive/Desktop/frontend_AI-powered_Purchase_Intelligence_System/src/pages/LoginSignup.tsx)
* **Input**: Current auth screen layout
* **Output**: Interactive OTP input screen with "Resend Code" and verification success redirects.
* **Verify**: Run the client dashboard and verify the workflow visually.

---

## Phase X: Verification
* [x] No build or lint warnings
* [x] Run `python .agents/scripts/checklist.py .`
* [x] Manual E2E validation: register user -> check code in terminal -> verify OTP -> log in normally.

## ✅ PHASE X COMPLETE
- Lint: ✅ Pass
- Security: ✅ No critical issues
- Build: ✅ Success
- Date: 2026-08-15

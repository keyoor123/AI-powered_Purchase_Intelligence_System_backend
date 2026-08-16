# Real Email Integration Plan

## Overview
Integrate actual SMTP email delivery using standard Python `smtplib` and `email.mime` libraries to send real 6-digit OTP verification emails to users. If the email delivery fails (e.g. wrong SMTP credentials or server connection error), the API will fail-secure and raise an HTTP 500 exception instructing the user to try again after some time.

## Project Type
BACKEND

## Success Criteria
1. Newly registered users receive a real email containing the 6-digit verification code.
2. Resending verification sends a new real email with a new code.
3. If SMTP credentials are not configured or connection fails, the user signup/resend request fails, throwing an HTTP 500 error: `"Failed to send verification email. Please try again after some time."`
4. The email sending operation runs in a separate thread using `asyncio.to_thread` to prevent blocking the FastAPI asynchronous event loop.

## Tech Stack
* Python standard library (`smtplib`, `email.mime`, `asyncio`)
* FastAPI (for exceptions and async hooks)

## File Structure
```plaintext
backend/
├── app/
│   ├── utils/
│   │   └── mailer.py       # [NEW] SMTP mailer utility to format and send HTML emails
│   ├── api/
│   │   └── auth.py         # Modified: import and invoke send_otp_email in signup/resend
```

## Task Breakdown

### Task 1: Create SMTP Mailer Utility
* **Agent**: `backend-specialist`
* **Skills**: `python-patterns`
* **File**: [mailer.py](file:///c:/Users/91742/OneDrive/Desktop/AI-powered_Purchase_Intelligence_System/backend/app/utils/mailer.py) [NEW]
* **Input**: Configured settings (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`)
* **Output**: `send_otp_email(to_email: str, otp_code: str)` async helper function
* **Verify**: Verify that the utility imports correctly and loads settings.

### Task 2: Update Auth Routes
* **Agent**: `backend-specialist`
* **Skills**: `python-patterns`
* **File**: [auth.py](file:///c:/Users/91742/OneDrive/Desktop/AI-powered_Purchase_Intelligence_System/backend/app/api/auth.py)
* **Input**: Signup and Resend endpoints
* **Output**:
  * `/signup` and `/resend-verification` import `send_otp_email` and call it.
  * Wrap in `try-except` block: if it throws an error, raise `HTTPException(status_code=500, detail="Failed to send verification email. Please try again after some time.")`.
* **Verify**: Test endpoints and confirm error is raised if credentials are empty, or email is sent successfully if credentials are provided.

---

## Phase X: Verification
* [x] No build or lint warnings
* [x] Run `python -X utf8 .agents/scripts/checklist.py .`

## ✅ PHASE X COMPLETE
- Lint: ✅ Pass
- Security: ✅ No critical issues
- Build: ✅ Success
- Date: 2026-08-15

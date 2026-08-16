# OTP-based Email Verification Flow

Implement email verification to protect the application from unauthorized signups. Newly registered users will be flagged as unverified and must enter a 6-digit OTP code before logging in and accessing any features.

## User Review Required

> [!IMPORTANT]
> The verification OTP code will be output to the backend console logs. In a production environment, this would integrate with an SMTP server or email provider (e.g., SendGrid, Mailgun).

> [!WARNING]
> Existing users in the database do not have the `is_verified` field. The schema update will default this field to `False` for new documents, but we will make the login logic check if `is_verified` is explicitly set to `False` (new users) vs not existing (legacy users, who will be grandfathered as verified so as not to lock you out of your current account).

## Open Questions

None at this stage. The requirements are clear: registration creates an unverified account and generates a code, verification sets `is_verified: true` and starts the session, login requires `is_verified` to be true.

---

## Proposed Changes

### Database Models

#### [MODIFY] [models.py](file:///c:/Users/91742/OneDrive/Desktop/AI-powered_Purchase_Intelligence_System/backend/app/models/models.py)
* Add fields to `UserDocument`:
  * `is_verified: bool = False`
  * `verification_code: Optional[str] = None`
  * `verification_code_expires_at: Optional[datetime] = None`

---

### Backend API Routes

#### [MODIFY] [auth.py](file:///c:/Users/91742/OneDrive/Desktop/AI-powered_Purchase_Intelligence_System/backend/app/api/auth.py)
* **Signup (`/signup`)**:
  * Save user with `is_verified=False`.
  * Generate a 6-digit OTP.
  * Save verification code and 15-minute expiration timestamp to the user record.
  * Log the verification OTP to backend stdout for development retrieval.
  * Return status indicating that email verification is required (do not issue session cookie).
* **Login (`/login`, `/login/json`)**:
  * Check the `is_verified` field in the user document. If explicitly `False`, raise an HTTP 403 Forbidden error with details indicating verification is required.
* **New route `/verify-email`**:
  * Takes `email` and `code`.
  * Validates code against database and checks expiration.
  * If valid, updates user `is_verified` to `True`, clears code fields, issues JWT session cookie, and returns the authenticated user payload.
* **New route `/resend-verification`**:
  * Regenerates OTP code, updates expiration, logs code to stdout, and returns success status.

---

### Frontend Services and State

#### [MODIFY] [api.ts](file:///c:/Users/91742/OneDrive/Desktop/frontend_AI-powered_Purchase_Intelligence_System/src/services/api.ts)
* Add API requests for:
  * `verifyEmail(email: string, code: string)`
  * `resendVerification(email: string)`
* Update return type expectations on `signup` (does not return token response anymore, returns verification prompt).

#### [MODIFY] [AuthContext.tsx](file:///c:/Users/91742/OneDrive/Desktop/frontend_AI-powered_Purchase_Intelligence_System/src/context/AuthContext.tsx)
* Update `signup` method to not set optimistic user state, but instead expose state variables or trigger page views for verification.

#### [MODIFY] [LoginSignup.tsx](file:///c:/Users/91742/OneDrive/Desktop/frontend_AI-powered_Purchase_Intelligence_System/src/pages/LoginSignup.tsx)
* Add an OTP input interface state (Verification Screen).
* Enable routing/transition into this screen from both:
  * Successful registration.
  * Unverified account login attempt (catching the 403 error).
* Implement verification form submission and "Resend Code" trigger button.

---

## Verification Plan

### Automated Tests
* None currently available. We will rely on linting:
  ```bash
  python .agents/scripts/checklist.py .
  ```

### Manual Verification
1. Open the application, register a new user account.
2. Verify that registration redirects to the Verification page instead of logging in.
3. Check the backend terminal console logs to retrieve the 6-digit OTP.
4. Input the code to verify the account and verify that you are redirected to the Dashboard.
5. Attempt to log in with another newly registered, unverified user credentials and verify that the application prevents login and redirects to the verification screen.
6. Verify that once verified, subsequent logins succeed normally without prompting for OTP.

# Chatbot Input Token Limit Plan

## Overview
Implement input validation and length guardrails on the chatbot interface to prevent excessive token consumption, API quota abuse, and payload-related failures.

## Project Type
FULL_STACK

## Success Criteria
1. **Backend Guardrail**: The backend `/analytics/chat` API validates input message strings and rejects any query exceeding 1,000 characters with an HTTP 422 validation error.
2. **Frontend Guardrail**: The chatbot input text field physically prevents the user from typing or pasting more than 1,000 characters.

## Tech Stack
* Backend: Pydantic field validators
* Frontend: React / HTML input properties

## File Structure
```plaintext
backend/
└── app/
    └── analytics/
        └── schemas/
            └── responses.py       # Modified: Add max_length constraint to ChatRequest schema
frontend/
└── src/
    └── pages/
        └── AiAssistantPage.tsx    # Modified: Add maxLength attribute to input element
```

## Task Breakdown

### Task 10: Implement Backend Pydantic Constraint
* **Agent**: `backend-specialist`
* **Skills**: `api-patterns`
* **File**: [responses.py](file:///c:/Users/91742/OneDrive/Desktop/AI-powered_Purchase_Intelligence_System/backend/app/analytics/schemas/responses.py)
* **Actions**:
  * Modify `ChatRequest` model:
    `message: str = Field(..., max_length=1000, description="The query message text from user")`
* **Verify**: Check that sending a message longer than 1000 characters returns an HTTP 422 validation error.

### Task 11: Implement Frontend Input Max Length
* **Agent**: `frontend-specialist`
* **Skills**: `frontend-design`
* **File**: [AiAssistantPage.tsx](file:///c:/Users/91742/OneDrive/Desktop/frontend_AI-powered_Purchase_Intelligence_System/src/pages/AiAssistantPage.tsx)
* **Actions**:
  * Locate input tag in `AiAssistantPage.tsx` at line 198.
  * Add the `maxLength={1000}` attribute.
* **Verify**: Run the client, verify that typing stops at 1,000 characters, and copy-pasting a long text truncates it at 1,000 characters.

---

## Phase X: Verification
* [x] Run `python -X utf8 .agents/scripts/checklist.py .`

## ✅ PHASE X COMPLETE
- Lint: ✅ Pass
- Security: ✅ No critical issues
- Build: ✅ Success
- Date: 2026-08-15

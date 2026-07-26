# Frontend Integration Guide: AI Agents Hub (Monthly Report Agent)

This document provides the API specifications and UX guidelines for integrating the **Monthly Purchase Intelligence Report Agent** into the frontend application.

---

## Overview

The AI Agent runs autonomously in the background to compile and deliver monthly procurement analysis PDFs to users. The frontend integration allows the user to:
1. Enable/disable the agent and configure the execution day of the month.
2. Manage a list of up to **5 additional email recipients** with individual delivery toggles.
3. Manually trigger an immediate report generation run (useful for testing/ad-hoc reporting).
4. Download previously generated PDFs from the database archive.

---

## Base API Details

* **Base URL**: `http://localhost:8000/agents/monthly-report`
* **Authentication**: All endpoints require a standard Bearer JWT token in the headers:
  ```http
  Authorization: Bearer <your_jwt_access_token>
  ```

---

## Endpoint Specifications

### 1. Get Agent Settings
Retrieves active status, execution day, recipient list, and execution schedule.

* **URL**: `/settings`
* **Method**: `GET`
* **Response (HTTP 200)**:
  ```json
  {
    "agent_type": "monthly_report",
    "is_enabled": true,
    "schedule_config": {
      "day_of_month": 2
    },
    "delivery_emails": [
      {
        "email": "primary_user@acme.com",
        "is_enabled": true
      },
      {
        "email": "finance@acme.com",
        "is_enabled": false
      }
    ],
    "last_run": "2026-07-02T09:00:00Z",
    "next_run": "2026-08-02T09:00:00Z"
  }
  ```

---

### 2. Update Scheduler Settings
Toggle the agent active state or update the day of the month it triggers on.

* **URL**: `/settings`
* **Method**: `PUT`
* **Request Body**:
  ```json
  {
    "is_enabled": true,         // optional
    "day_of_month": 5           // optional (range: 1 - 28)
  }
  ```
* **Response (HTTP 200)**: Same structure as the **Get Settings** response.

---

### 3. Add Recipient Email
Appends an email address to the report delivery distribution list.

* **URL**: `/emails`
* **Method**: `POST`
* **Request Body**:
  ```json
  {
    "email": "partner@acme.com"
  }
  ```
* **Response (HTTP 200)**: Same structure as **Get Settings** (with the updated email list).
* **Error States**:
  * **HTTP 400 Bad Request**: Raised if the email is a duplicate or if the list size exceeds **5 additional emails** (6 total including the primary account email).
    ```json
    {
      "detail": "You have reached the maximum limit of 5 additional email recipients."
    }
    ```

---

### 4. Toggle Email Delivery
Enable or disable delivery to a specific email address without deleting it.

* **URL**: `/emails/toggle`
* **Method**: `PUT`
* **Request Body**:
  ```json
  {
    "email": "finance@acme.com",
    "is_enabled": true
  }
  ```
* **Response (HTTP 200)**: Same structure as **Get Settings**.

---

### 5. Remove Recipient Email
Deletes an email address from the distribution list.

* **URL**: `/emails/{email}`
* **Method**: `DELETE`
* **Response (HTTP 200)**: Same structure as **Get Settings**.

---

### 6. Manually Trigger Agent
Forces the agent to compile, save, and deliver the previous calendar month's PDF report immediately.

* **URL**: `/trigger`
* **Method**: `POST`
* **Response (HTTP 200)**:
  * **Success**:
    ```json
    {
      "status": "success",
      "message": "Monthly Report compiled, saved, and dispatched successfully."
    }
    ```
  * **Failure** (e.g. no bills exist for the target month):
    ```json
    {
      "status": "failed",
      "message": "Monthly Report failed to compile. Check execution logs or verify you have bills uploaded."
    }
    ```

---

### 7. Get Execution Logs
Fetch previous execution history audits for the logs panel.

* **URL**: `/logs`
* **Method**: `GET`
* **Response (HTTP 200)**:
  ```json
  [
    {
      "_id": "6a48f887d80623f1999cfbf7",
      "user_id": "6a2e38cc2f30b20ef749071d",
      "agent_type": "monthly_report",
      "status": "success",
      "run_at": "2026-07-04T12:07:08.520000",
      "emails_sent_to": [
        "primary_user@acme.com"
      ],
      "pdf_grid_file_id": "6a48f887d80623f1999cfbf5",
      "error_message": null
    }
  ]
  ```

---

### 8. Download PDF Report
Stream and download the compiled PDF binary file from the database archive using its File ID.

* **URL**: `/reports/{file_id}`
* **Method**: `GET`
* **Response**: Binary PDF Stream (`media_type="application/pdf"`) with download headers.
* **Error Response (HTTP 404)**:
  ```json
  {
    "detail": "Report PDF not found."
  }
  ```
  *(Note: When a user triggers multiple runs for the same month, older PDFs are deleted to save storage, meaning older log file IDs will return 404. Always use the `pdf_grid_file_id` of the latest successful log).*

---

## Front-End UI/UX Suggestions

1. **Card Layout**: Place settings controls inside a collapsible "Monthly Procurement Summary Report" card within an "AI Agents" tab page.
2. **Day Selector**: Use a dropdown or range slider from `1` to `28`. Avoid days `29-31` to prevent issues with variable month lengths (like February).
3. **Limit Handling**: Proactively disable the email input field and show a message when the array length of `delivery_emails` is `6` (1 primary + 5 additional).
4. **Status Badges**: For execution logs, use badge colors based on the `status` field:
   * `"success"` -> Green badge
   * `"failed"` -> Red badge
5. **Loading States**: Since manual trigger (`POST /trigger`) calls OpenRouter to write the AI summary and compiles matplotlib charts, it can take **4-8 seconds**. Ensure a clean spinner or loading overlay is shown with a text like *"AI Agent is compiling your monthly charts and generating executive summary..."*

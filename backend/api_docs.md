# Purchase Intelligence System - API Reference Documentation

This document describes all REST API endpoints exposed by the backend FastAPI server, designed to assist in integrating the frontend dashboard UI.

---

## 🔒 Authentication & Headers

All requests to protected routes **must** include the following HTTP header:
```http
Authorization: Bearer <your_jwt_access_token>
```
If this header is invalid, missing, or expired, the server returns:
*   **Status Code**: `401 Unauthorized`
*   **Body**: `{"detail": "Could not validate credentials. Please log in."}`

---

## 🔑 1. User Authentication APIs

### Register New User
*   **Endpoint**: `POST /auth/signup`
*   **Content-Type**: `application/json`
*   **Payload**:
    ```json
    {
      "email": "user@example.com",
      "password": "strongpassword123",
      "display_name": "Aarav Mehta"
    }
    ```
*   **Response (201 Created)**: Returns the user credentials and a JWT token. Also seeds default categories (`Paint`, `Building Materials`, `Hardware`, `Electrical`) specifically for this user's workspace.
    ```json
    {
      "access_token": "eyJhbGciOi...",
      "token_type": "bearer",
      "user": {
        "id": "6a2e2e...",
        "email": "user@example.com",
        "display_name": "Aarav Mehta"
      }
    }
    ```

### Login (Form URL-Encoded)
*   **Endpoint**: `POST /auth/login`
*   **Content-Type**: `application/x-www-form-urlencoded`
*   **Payload**: Form data containing `username` (email) and `password`.
*   **Response (200 OK)**:
    ```json
    {
      "access_token": "eyJhbGciOi...",
      "token_type": "bearer",
      "user": {
        "id": "6a2e2e...",
        "email": "user@example.com",
        "display_name": "Aarav Mehta"
      }
    }
    ```

### Login (JSON-based)
*   **Endpoint**: `POST /auth/login/json`
*   **Content-Type**: `application/json`
*   **Payload**:
    ```json
    {
      "email": "user@example.com",
      "password": "strongpassword123"
    }
    ```
*   **Response (200 OK)**: (Same structure as login/signup response).

### Forgot Password
*   **Endpoint**: `POST /auth/forgot-password`
*   **Content-Type**: `application/json`
*   **Payload**:
    ```json
    {
      "email": "user@example.com"
    }
    ```
*   **Response (200 OK)**: Simulates sending an email, logging the reset link inside the terminal:
    ```json
    {
      "message": "If the email is registered in our system, a password reset link has been sent.",
      "debug_token": "eyJhbGciOi..."
    }
    ```

### Reset Password
*   **Endpoint**: `POST /auth/reset-password`
*   **Content-Type**: `application/json`
*   **Payload**:
    ```json
    {
      "token": "eyJhbGciOi...",
      "new_password": "mynewpassword456"
    }
    ```
*   **Response (200 OK)**:
    ```json
    {
      "success": true,
      "message": "Password reset completed successfully. You can now log in."
    }
    ```

---

## 📁 2. Bill Ingestion & Management APIs

### Upload Bill Invoice Image/PDF (Single)
*   **Endpoint**: `POST /upload`
*   **Headers**: Requires JWT
*   **Content-Type**: `multipart/form-data`
*   **Payload**: Form file field `file` (Image or PDF)
*   **Response (200 OK)**: Returns LLM-extracted metadata.
    ```json
    {
      "dealer_name": "Acme Paint Dealers",
      "invoice_no": "INV-2026-991",
      "date": "2026-06-14",
      "items": [
        {
          "product": "Asian Paint 20L",
          "quantity": 10.0,
          "unit": "bucket",
          "price": 5000.0,
          "amount": 50000.0
        }
      ],
      "subtotal": 50000.0,
      "gst": 9000.0,
      "total": 59000.0,
      "category": "Paint"
    }
    ```

### Upload Batch Invoices (Multiple)
*   **Endpoint**: `POST /upload/batch`
*   **Headers**: Requires JWT
*   **Content-Type**: `multipart/form-data`
*   **Payload**: Form file field `files` (array of files)
*   **Response (200 OK)**: Array of parsed invoice metadata.

### Save Confirmed Invoice
*   **Endpoint**: `POST /save`
*   **Headers**: Requires JWT
*   **Content-Type**: `application/json`
*   **Payload**: Expects the verified structured bill JSON:
    ```json
    {
      "dealer_name": "Acme Paint Dealers",
      "invoice_no": "INV-2026-991",
      "date": "2026-06-14",
      "items": [
        {
          "product": "Asian Paint 20L",
          "quantity": 10.0,
          "unit": "bucket",
          "price": 5000.0,
          "amount": 50000.0
        }
      ],
      "subtotal": 50000.0,
      "gst": 9000.0,
      "total": 59000.0,
      "category": "Paint"
    }
    ```
*   **Response (201 Created)**:
    ```json
    {
      "message": "Bill saved successfully.",
      "id": "6a2e2e..."
    }
    ```

### Get All Invoices
*   **Endpoint**: `GET /bills`
*   **Headers**: Requires JWT
*   **Response (200 OK)**: Returns list of user's bills.
    ```json
    [
      {
        "_id": "6a2e2e...",
        "dealer_name": "Acme Paint Dealers",
        "invoice_no": "INV-2026-991",
        "date": "2026-06-14",
        "total": 59000.0,
        "category": "Paint"
      }
    ]
    ```

### Get Bill Details by ID
*   **Endpoint**: `GET /bill/{id}`
*   **Headers**: Requires JWT
*   **Response (200 OK)**: Detailed bill payload.

---

## 🏷️ 3. Category Management APIs

### Fetch All Categories
*   **Endpoint**: `GET /categories`
*   **Headers**: Requires JWT
*   **Response (200 OK)**:
    ```json
    [
      {
        "id": "6a2e2e...",
        "user_id": "6a2e...",
        "name": "Paint"
      }
    ]
    ```

### Create Custom Category
*   **Endpoint**: `POST /categories`
*   **Headers**: Requires JWT
*   **Content-Type**: `application/json`
*   **Payload**:
    ```json
    {
      "name": "Plumbing"
    }
    ```
*   **Response (201 Created)**: Created category payload.

### Rename Category (Cascades rename to all user products/bills)
*   **Endpoint**: `PUT /categories/{id}`
*   **Headers**: Requires JWT
*   **Content-Type**: `application/json`
*   **Payload**:
    ```json
    {
      "name": "Plumbing & Sanitation"
    }
    ```
*   **Response (200 OK)**: Updated category object.

### Delete Category (Resets matching product/bill categories to `""`)
*   **Endpoint**: `DELETE /categories/{id}`
*   **Headers**: Requires JWT
*   **Response (200 OK)**:
    ```json
    {
      "message": "Category 'Plumbing' deleted successfully."
    }
    ```

---

## ⚙️ 4. Profile & Organization Settings APIs

### Fetch Organization Settings
*   **Endpoint**: `GET /settings/organization`
*   **Headers**: Requires JWT
*   **Response (200 OK)**:
    ```json
    {
      "org_name": "Acme Procurement",
      "currency": "Indian Rupee (₹)",
      "timezone": "Asia/Kolkata",
      "date_format": "10 Apr 2026"
    }
    ```

### Save/Update Organization Settings
*   **Endpoint**: `PUT /settings/organization`
*   **Headers**: Requires JWT
*   **Payload**: Same schema as GET response.

### Fetch User Profile Display Preferences
*   **Endpoint**: `GET /settings/profile`
*   **Headers**: Requires JWT
*   **Response (200 OK)**:
    ```json
    {
      "display_name": "Aarav Mehta",
      "email": "aarav@acme.in",
      "locale": "English (India)",
      "time_format": "24-hour"
    }
    ```

### Update User Profile
*   **Endpoint**: `PUT /settings/profile`
*   **Headers**: Requires JWT
*   **Payload**: Same schema as GET response.

---

## 📊 5. Analytics Engine APIs

All Analytics APIs are isolated by default. Aggregates only compute metrics using the authenticated user's data.

### Get Dashboard Analytics
*   **Endpoint**: `GET /analytics/dashboard`
*   **Headers**: Requires JWT
*   **Response (200 OK)**:
    ```json
    {
      "total_purchase_amount": 145000.0,
      "total_bills": 5,
      "total_products": 22,
      "total_dealers": 4,
      "average_bill_amount": 29000.0,
      "highest_bill_amount": 56000.0,
      "lowest_bill_amount": 12000.0,
      "monthly_purchase_summary": [
        { "label": "2026-05", "total_amount": 45200.0, "bill_count": 2 }
      ],
      "yearly_purchase_summary": []
    }
    ```

### Get Active Dealers Profile Lists
*   **Endpoint**: `GET /analytics/dealers`
*   **Headers**: Requires JWT
*   **Response (200 OK)**: Array of dealer profiles.

### Compare Side-by-Side Dealers
*   **Endpoint**: `GET /analytics/dealers/compare`
*   **Headers**: Requires JWT
*   **Query Parameters**:
    *   `dealer_a` (string, required): First dealer name
    *   `dealer_b` (string, required): Second dealer name
*   **Response (200 OK)**:
    ```json
    {
      "dealer_a": "Dealer A",
      "dealer_b": "Dealer B",
      "metrics_a": {
        "total_purchase": 45200.0,
        "average_price": 320.0,
        "total_quantity": 100.0
      },
      "metrics_b": {
        "total_purchase": 43250.0,
        "average_price": 310.0,
        "total_quantity": 50.0
      },
      "price_difference": 10.0,
      "savings_opportunity": 1300.0
    }
    ```

### Compare Product Across Suppliers (Find Cheapest Option)
*   **Endpoint**: `GET /analytics/products/compare`
*   **Headers**: Requires JWT
*   **Query Parameters**:
    *   `product_name` (string, required): Name of the product
*   **Response (200 OK)**:
    ```json
    {
      "product_name": "Asian Paint 20L",
      "cheapest_dealer": "Dealer B",
      "cheapest_price": 5050.0,
      "costliest_dealer": "Dealer C",
      "costliest_price": 5300.0,
      "average_market_price": 5183.33,
      "price_difference": 250.0,
      "potential_savings": 2800.0,
      "historical_prices": [
        {
          "dealer_name": "Dealer B",
          "average_price": 5050.0,
          "min_price": 5050.0,
          "max_price": 5050.0,
          "last_purchase_date": "2026-06-12"
        }
      ]
    }
    ```

### Category Spending Trends
*   **Endpoint**: `GET /analytics/products/categories`
*   **Headers**: Requires JWT
*   **Response (200 OK)**:
    ```json
    {
      "categories": [
        {
          "category_name": "Paint",
          "total_spending": 88650.0,
          "total_quantity": 17.0,
          "growth_percentage": 652.4
        }
      ],
      "top_category_by_spending": "Paint",
      "top_category_by_quantity": "Paint"
    }
    ```

### Get Spending and Volume Projections (Forecasting)
*   **Endpoint**: `GET /analytics/forecast`
*   **Headers**: Requires JWT
*   **Response (200 OK)**:
    ```json
    {
      "next_month_purchase_amount": 61415.0,
      "next_month_product_quantity": [
        { "label": "Next Month", "forecast_value": 75.0 }
      ],
      "future_price_trend": {
        "Cement": [
          { "label": "Next Month", "forecast_value": 315.0 }
        ]
      }
    }
    ```

### Get Savings Opportunities List
*   **Endpoint**: `GET /analytics/savings`
*   **Headers**: Requires JWT
*   **Response (200 OK)**: Overpayment list if bought from higher cost dealers instead of the cheapest.
    ```json
    {
      "total_potential_savings": 3800.0,
      "opportunities": [
        {
          "product_name": "Asian Paint 20L",
          "dealer_purchased": "Dealer C",
          "actual_price": 5300.0,
          "cheapest_dealer": "Dealer B",
          "cheapest_price": 5050.0,
          "quantity_purchased": 10.0,
          "potential_savings": 2500.0
        }
      ]
    }
    ```

### Get Structured Context Payload for downstream AI Assistant
*   **Endpoint**: `GET /analytics/ai-context`
*   **Headers**: Requires JWT
*   **Query Parameters**:
    *   `query_type` (string, required): Context format to compile (`cheapest_dealer`, `price_increase`, `monthly_spend`, `dealer_comparison`, `negotiation_targets`)
    *   `product_name` (string, optional)
    *   `dealer_a` (string, optional)
    *   `dealer_b` (string, optional)
*   **Response (200 OK)**:
    ```json
    {
      "context_type": "cheapest_dealer",
      "context_data": {
        "product_name": "Asian Paint 20L",
        "cheapest_dealer": "Dealer B",
        "cheapest_price": 5050.0,
        "insights_summary": "The cheapest supplier for 'Asian Paint 20L' is Dealer B at Rs.5050.0. The costliest is Dealer C at Rs.5300.0."
      }
    }
    ```

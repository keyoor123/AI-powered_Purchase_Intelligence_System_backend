import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List
from bson import ObjectId

from app.database.database import db_manager
from app.services.agents.base import BaseAgent
from app.services.agents.utils.pdf_generator import pdf_report_generator
from app.services.llm_chat_service import llm_chat_service
from app.services.agents.utils.email_notifier import email_notifier
from motor.motor_asyncio import AsyncIOMotorGridFSBucket

logger = logging.getLogger(__name__)

class MonthlyReportAgent(BaseAgent):
    @property
    def agent_type(self) -> str:
        return "monthly_report"

    async def run(self, user_id: str, context: dict = None) -> bool:
        """Runs the monthly intelligence report compilation and delivery."""
        logger.info(f"Running MonthlyReportAgent for user: {user_id}")
        
        run_at = datetime.utcnow()
        status = "failed"
        pdf_grid_file_id = None
        emails_sent = []
        error_msg = None

        try:
            # 1. Calculate Date Range for Previous Month
            # By default, we run for the previous full calendar month
            ref_date = context.get("ref_date", run_at) if context else run_at
            
            # First day of target month: Go back to last month
            first_day_current = ref_date.replace(day=1)
            last_day_previous = first_day_current - timedelta(days=1)
            start_date = last_day_previous.replace(day=1)
            end_date = last_day_previous

            start_str = start_date.strftime("%Y-%m-%d")
            end_str = end_date.strftime("%Y-%m-%d")
            month_label = start_date.strftime("%B %Y")
            
            logger.info(f"Generating monthly report for range: {start_str} to {end_str} ({month_label})")

            # 2. Gather MongoDB Analytical Context
            analytics_data = await self._gather_monthly_analytics(user_id, start_date, end_date)
            
            if analytics_data["monthly_bills_count"] == 0:
                logger.warning(f"No bills found for user {user_id} in date range {start_str} - {end_str}. Skipping report.")
                error_msg = f"No bills found for {month_label}."
                await self._log_execution(user_id, "failed", run_at, error_message=error_msg)
                return False

            # 3. Generate AI Executive Summary via OpenRouter
            ai_summary = await self._generate_ai_summary(month_label, analytics_data)

            # 4. Fetch User Details & Org Info
            user_doc = await db_manager.get_users_collection().find_one({"_id": ObjectId(user_id)})
            user_name = user_doc.get("display_name", "User") if user_doc else "Procurement Manager"
            
            settings_col = db_manager.get_settings_collection()
            org_doc = await settings_col.find_one({"user_id": user_id, "type": "organization"})
            org_name = org_doc.get("value", {}).get("org_name", "My Procurement Shop") if org_doc else "My Procurement Shop"

            # 5. Compile PDF report
            import re
            ai_summary_formatted = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', ai_summary)
            ai_summary_formatted = ai_summary_formatted.replace("\n", "<br/>")

            pdf_bytes = pdf_report_generator.build_monthly_report_pdf(
                user_name=user_name,
                org_name=org_name,
                month_label=month_label,
                analytics_data=analytics_data,
                ai_summary=ai_summary_formatted
            )

            # 6. Upload PDF to MongoDB GridFS
            db = db_manager.get_db()
            fs = AsyncIOMotorGridFSBucket(db)
            filename = f"report_{user_id}_{start_date.strftime('%Y_%m')}.pdf"
            
            # Check and delete existing file for this month to avoid duplicates
            cursor = fs.find({"filename": filename})
            existing_files = await cursor.to_list(length=10)
            for f in existing_files:
                await fs.delete(f["_id"])

            grid_in = fs.open_upload_stream(filename, metadata={"user_id": user_id, "month_label": month_label})
            await grid_in.write(pdf_bytes)
            await grid_in.close()
            pdf_grid_file_id = str(grid_in._id)
            logger.info(f"Uploaded monthly report PDF to GridFS: {pdf_grid_file_id}")

            # 7. Deliver via Emails
            emails_sent = await self._deliver_emails(user_id, pdf_bytes, filename, month_label, org_name)
            status = "success"

        except Exception as e:
            logger.error(f"Error executing MonthlyReportAgent for user {user_id}: {e}", exc_info=True)
            error_msg = str(e)
            status = "failed"

        # 8. Record Execution Log & Update Agent Settings
        await self._log_execution(user_id, status, run_at, emails_sent, pdf_grid_file_id, error_msg)
        return status == "success"

    async def _gather_monthly_analytics(self, user_id: str, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Runs aggregations for the specific month's data."""
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        bills_col = db_manager.get_bills_collection()
        match_stage = {
            "user_id": user_id,
            "date": {"$gte": start_str, "$lte": end_str}
        }

        # Query 1: KPIs
        pipeline_kpi = [
            {"$match": match_stage},
            {
                "$group": {
                    "_id": None,
                    "total_spend": {"$sum": "$total"},
                    "bill_count": {"$sum": 1},
                    "dealers": {"$addToSet": "$dealer_name"}
                }
            }
        ]
        cursor = bills_col.aggregate(pipeline_kpi)
        kpi_list = await cursor.to_list(length=1)
        kpi_res = kpi_list[0] if kpi_list else {}

        # Query 2: Category spending (incorporating tax/GST proportionally)
        pipeline_category = [
            {"$match": match_stage},
            {
                "$addFields": {
                    "tax_factor": {
                        "$cond": [
                            {"$gt": ["$subtotal", 0]},
                            {"$divide": ["$total", "$subtotal"]},
                            1.0
                        ]
                    }
                }
            },
            {"$unwind": "$items"},
            {
                "$lookup": {
                    "from": "products",
                    "let": {"item_prod": "$items.product"},
                    "pipeline": [
                        {"$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$name", "$$item_prod"]},
                                    {"$eq": ["$user_id", user_id]}
                                ]
                            }
                        }}
                    ],
                    "as": "product_info"
                }
            },
            {"$unwind": {"path": "$product_info", "preserveNullAndEmptyArrays": True}},
            {
                "$project": {
                    "category": {"$ifNull": ["$product_info.category", "Uncategorized"]},
                    "amount_with_tax": {"$multiply": ["$items.amount", "$tax_factor"]},
                    "quantity": "$items.quantity"
                }
            },
            {
                "$group": {
                    "_id": "$category",
                    "total_spending": {"$sum": "$amount_with_tax"},
                    "total_quantity": {"$sum": "$quantity"}
                }
            }
        ]
        cursor = bills_col.aggregate(pipeline_category)
        category_spending = await cursor.to_list(length=100)

        # Query 3: Top Products (incorporating tax/GST proportionally)
        pipeline_products = [
            {"$match": match_stage},
            {
                "$addFields": {
                    "tax_factor": {
                        "$cond": [
                            {"$gt": ["$subtotal", 0]},
                            {"$divide": ["$total", "$subtotal"]},
                            1.0
                        ]
                    }
                }
            },
            {"$unwind": "$items"},
            {
                "$group": {
                    "_id": "$items.product",
                    "total_quantity_purchased": {"$sum": "$items.quantity"},
                    "total_amount_spent": {"$sum": {"$multiply": ["$items.amount", "$tax_factor"]}},
                    "dealers": {"$addToSet": "$dealer_name"}
                }
            },
            {"$sort": {"total_amount_spent": -1}}
        ]
        cursor = bills_col.aggregate(pipeline_products)
        top_products = await cursor.to_list(length=10)

        # Query 4: Last 6 months spend history (trend line)
        six_months_ago = start_date - timedelta(days=150)
        six_months_ago_str = six_months_ago.strftime("%Y-%m-%d")
        pipeline_history = [
            {"$match": {
                "user_id": user_id,
                "date": {"$gte": six_months_ago_str, "$lte": end_str}
            }},
            {
                "$project": {
                    "total": "$total",
                    "date_obj": {"$dateFromString": {"dateString": "$date", "onError": None, "onNull": None}}
                }
            },
            {
                "$group": {
                    "_id": {
                        "year": {"$year": "$date_obj"},
                        "month": {"$month": "$date_obj"}
                    },
                    "total_amount": {"$sum": "$total"},
                    "bill_count": {"$sum": 1}
                }
            },
            {"$sort": {"_id.year": 1, "_id.month": 1}}
        ]
        cursor = bills_col.aggregate(pipeline_history)
        history_list = await cursor.to_list(length=10)
        
        monthly_spend_history = []
        for h in history_list:
            if h["_id"] and h["_id"].get("year") and h["_id"].get("month"):
                monthly_spend_history.append({
                    "label": f"{h['_id']['year']}-{h['_id']['month']:02d}",
                    "total_amount": h["total_amount"],
                    "bill_count": h["bill_count"]
                })

        # Query 5: Supplier Spending Summary
        pipeline_dealer_spend = [
            {"$match": match_stage},
            {
                "$group": {
                    "_id": "$dealer_name",
                    "total_spend": {"$sum": "$total"},
                    "bill_count": {"$sum": 1}
                }
            },
            {"$sort": {"total_spend": -1}}
        ]
        cursor = bills_col.aggregate(pipeline_dealer_spend)
        dealer_spending = await cursor.to_list(length=100)

        return {
            "monthly_spend_total": kpi_res.get("total_spend", 0.0),
            "monthly_bills_count": kpi_res.get("bill_count", 0),
            "monthly_dealers_count": len(kpi_res.get("dealers", [])),
            "category_spending": category_spending,
            "top_products": top_products,
            "monthly_spend_history": monthly_spend_history,
            "dealer_spending": dealer_spending
        }

    async def _generate_ai_summary(self, month_label: str, analytics_data: Dict[str, Any]) -> str:
        """Sends data to the LLM to get a professional summary."""
        # Convert summaries to small JSON contexts
        category_summary = [
            {"category": item["_id"], "spent": f"INR {item['total_spending']:,.2f}"}
            for item in analytics_data["category_spending"]
        ]
        products_summary = [
            {"product": item["_id"], "amount": f"INR {item['total_amount_spent']:,.2f}"}
            for item in analytics_data["top_products"][:3]
        ]

        system_prompt = (
            "You are the Monthly Procurement Intelligence Agent. Your job is to analyze the monthly purchase report metrics "
            "provided by the user and write a concise, professional, and action-oriented executive summary.\n"
            "Highlight cost savings, spending trends, supplier concentration, or category jumps.\n"
            "Use a formal business tone. Keep the summary under 140 words."
        )

        user_content = (
            f"Purchase report details for {month_label}:\n"
            f"- Total spent: INR {analytics_data['monthly_spend_total']:,.2f}\n"
            f"- Total bills processed: {analytics_data['monthly_bills_count']}\n"
            f"- Active suppliers: {analytics_data['monthly_dealers_count']}\n"
            f"- Category Spending: {json.dumps(category_summary)}\n"
            f"- Top Products: {json.dumps(products_summary)}\n"
        )

        try:
            if not llm_chat_service.api_key:
                return "The Monthly Intelligence Agent completed data compilation, but the OpenRouter API Key was not set to write the executive summary."
            
            response = await llm_chat_service.client.chat.completions.create(
                model=llm_chat_service.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                extra_headers={
                    "HTTP-Referer": "https://github.com/vudovn/ag-kit", 
                    "X-Title": "AI-powered Purchase Intelligence System"
                },
                temperature=0.3,
                max_tokens=400
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Failed to generate LLM summary for report: {e}")
            return "Failed to generate executive summary due to LLM provider issues."

    async def _deliver_emails(self, user_id: str, pdf_bytes: bytes, filename: str, month_label: str, org_name: str) -> List[str]:
        """Delivers report to enabled recipient emails."""
        # Find agent settings to get recipient emails
        settings_col = db_manager.get_settings_collection()
        doc = await settings_col.find_one({"user_id": user_id, "type": "agent_settings", "value.agent_type": "monthly_report"})
        
        recipients = []
        if doc and "value" in doc:
            emails_list = doc["value"].get("delivery_emails", [])
            recipients = [e["email"] for e in emails_list if e.get("is_enabled", True)]
        
        # Fallback to profile email if no agent settings recipients found
        if not recipients:
            profile_doc = await settings_col.find_one({"user_id": user_id, "type": "profile"})
            if profile_doc and "value" in profile_doc:
                recipients = [profile_doc["value"]["email"]]
                
        if not recipients:
            # Check user document as absolute fallback
            user_doc = await db_manager.get_users_collection().find_one({"_id": ObjectId(user_id)})
            if user_doc:
                recipients = [user_doc["email"]]

        if not recipients:
            logger.warning(f"No recipient email found for user {user_id}. Skipping email dispatch.")
            return []

        logger.info(f"Dispatching report emails to: {recipients}")
        
        subject = f"Monthly Purchase Intelligence Report - {month_label}"
        body = (
            f"Dear Team,\n\n"
            f"Please find attached your Monthly Purchase Intelligence Report for {month_label} "
            f"generated by your autonomous AI agent.\n\n"
            f"Best regards,\n"
            f"{org_name} Procurement Intelligence Bot"
        )
        
        delivered = []
        for email in recipients:
            try:
                success = await email_notifier.send_email_with_attachment(
                    to_email=email,
                    subject=subject,
                    body=body,
                    attachment_bytes=pdf_bytes,
                    attachment_filename=filename
                )
                if success:
                    delivered.append(email)
            except Exception as e:
                logger.error(f"Failed to send email to {email}: {e}")
                
        return delivered

    async def _log_execution(self, 
                             user_id: str, 
                             status: str, 
                             run_at: datetime, 
                             emails_sent: List[str] = None, 
                             pdf_grid_file_id: str = None, 
                             error_message: str = None):
        """Saves run details to agent_execution_logs and updates last/next runs in agent_settings."""
        db = db_manager.get_db()
        
        # Log to agent_execution_logs collection
        log_doc = {
            "user_id": user_id,
            "agent_type": self.agent_type,
            "status": status,
            "run_at": run_at,
            "emails_sent_to": emails_sent or [],
            "pdf_grid_file_id": pdf_grid_file_id,
            "error_message": error_message
        }
        await db["agent_execution_logs"].insert_one(log_doc)
        
        # Update last_run in settings
        settings_col = db_manager.get_settings_collection()
        doc = await settings_col.find_one({"user_id": user_id, "type": "agent_settings", "value.agent_type": self.agent_type})
        if doc:
            value = doc["value"]
            value["last_run"] = run_at
            
            # Recalculate next run date
            day_of_month = value.get("schedule_config", {}).get("day_of_month", 2)
            
            # Calculate next month run
            # If today is before day_of_month, next run is this month. Else, next month.
            try:
                # Target this month
                candidate = run_at.replace(day=day_of_month)
                if candidate <= run_at:
                    # Target next month
                    if run_at.month == 12:
                        candidate = run_at.replace(year=run_at.year + 1, month=1, day=day_of_month)
                    else:
                        candidate = run_at.replace(month=run_at.month + 1, day=day_of_month)
                value["next_run"] = candidate
            except ValueError:
                # Handle leap year edge cases by clamping to the 28th
                candidate = run_at.replace(day=28)
                value["next_run"] = candidate
            
            await settings_col.update_one(
                {"_id": doc["_id"]},
                {"$set": {"value": value, "updated_at": datetime.utcnow()}}
            )

monthly_report_agent = MonthlyReportAgent()

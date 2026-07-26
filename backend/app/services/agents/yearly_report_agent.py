import logging
import json
import re
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

class YearlyReportAgent(BaseAgent):
    @property
    def agent_type(self) -> str:
        return "yearly_report"

    async def run(self, user_id: str, context: dict = None) -> bool:
        """Runs the yearly intelligence report compilation and delivery."""
        logger.info(f"Running YearlyReportAgent for user: {user_id}")
        
        run_at = datetime.utcnow()
        status = "failed"
        pdf_grid_file_id = None
        emails_sent = []
        error_msg = None

        try:
            # 1. Calculate Date Range for Previous Calendar Year
            ref_date = context.get("ref_date", run_at) if context else run_at
            target_year = ref_date.year - 1
            start_date = datetime(target_year, 1, 1, 0, 0, 0)
            end_date = datetime(target_year, 12, 31, 23, 59, 59)

            start_str = start_date.strftime("%Y-%m-%d")
            end_str = end_date.strftime("%Y-%m-%d")
            year_label = str(target_year)
            
            logger.info(f"Generating yearly report for range: {start_str} to {end_str} ({year_label})")

            # 2. Gather MongoDB Analytical Context
            analytics_data = await self._gather_yearly_analytics(user_id, start_date, end_date)
            
            if analytics_data["yearly_bills_count"] == 0:
                logger.warning(f"No bills found for user {user_id} in target year {target_year}. Skipping report.")
                error_msg = f"No bills found for year {year_label}."
                await self._log_execution(user_id, "failed", run_at, error_message=error_msg)
                return False

            # Calculate Year-over-Year (YoY) metrics if data exists for target_year - 1
            prior_year = target_year - 1
            prior_start = datetime(prior_year, 1, 1, 0, 0, 0)
            prior_end = datetime(prior_year, 12, 31, 23, 59, 59)
            prior_analytics = await self._gather_yearly_analytics(user_id, prior_start, prior_end)

            has_prior_year = prior_analytics["yearly_bills_count"] > 0
            analytics_data["has_prior_year"] = has_prior_year
            analytics_data["prior_year_label"] = str(prior_year)

            if has_prior_year:
                prior_spend = prior_analytics["yearly_spend_total"]
                current_spend = analytics_data["yearly_spend_total"]
                spend_diff = current_spend - prior_spend
                spend_growth_pct = (spend_diff / prior_spend * 100) if prior_spend > 0 else 0.0
                
                analytics_data["prior_year_spend_total"] = prior_spend
                analytics_data["prior_year_bills_count"] = prior_analytics["yearly_bills_count"]
                analytics_data["spend_growth_pct"] = spend_growth_pct
            else:
                analytics_data["prior_year_spend_total"] = 0.0
                analytics_data["prior_year_bills_count"] = 0
                analytics_data["spend_growth_pct"] = 0.0

            # 3. Generate AI Executive Summary & Predictions
            ai_summary = await self._generate_ai_summary(year_label, analytics_data)

            # 4. Fetch User Details & Org Info
            user_doc = await db_manager.get_users_collection().find_one({"_id": ObjectId(user_id)})
            user_name = user_doc.get("display_name", "User") if user_doc else "Procurement Manager"
            
            settings_col = db_manager.get_settings_collection()
            org_doc = await settings_col.find_one({"user_id": user_id, "type": "organization"})
            org_name = org_doc.get("value", {}).get("org_name", "My Procurement Shop") if org_doc else "My Procurement Shop"

            # 5. Compile PDF report
            ai_summary_formatted = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', ai_summary)
            ai_summary_formatted = ai_summary_formatted.replace("\n", "<br/>")

            pdf_bytes = pdf_report_generator.build_yearly_report_pdf(
                user_name=user_name,
                org_name=org_name,
                year_label=year_label,
                analytics_data=analytics_data,
                ai_summary=ai_summary_formatted
            )

            # 6. Upload PDF to MongoDB GridFS
            db = db_manager.get_db()
            fs = AsyncIOMotorGridFSBucket(db)
            filename = f"yearly_report_{user_id}_{target_year}.pdf"
            
            # Check and delete existing file for this year to avoid duplicates
            cursor = fs.find({"filename": filename})
            existing_files = await cursor.to_list(length=10)
            for f in existing_files:
                await fs.delete(f["_id"])

            grid_in = fs.open_upload_stream(filename, metadata={"user_id": user_id, "year_label": year_label})
            await grid_in.write(pdf_bytes)
            await grid_in.close()
            pdf_grid_file_id = str(grid_in._id)
            logger.info(f"Uploaded yearly report PDF to GridFS: {pdf_grid_file_id}")

            # 7. Deliver via Emails
            emails_sent = await self._deliver_emails(user_id, pdf_bytes, filename, year_label, org_name)
            status = "success"

        except Exception as e:
            logger.error(f"Error executing YearlyReportAgent for user {user_id}: {e}", exc_info=True)
            error_msg = str(e)
            status = "failed"

        # 8. Record Execution Log & Update Agent Settings
        await self._log_execution(user_id, status, run_at, emails_sent, pdf_grid_file_id, error_msg)
        return status == "success"

    async def _gather_yearly_analytics(self, user_id: str, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Runs aggregations for the specific year's data."""
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        bills_col = db_manager.get_bills_collection()
        match_stage = {
            "user_id": user_id,
            "date": {"$gte": start_str, "$lte": end_str}
        }

        # Query 1: Annual KPIs
        pipeline_kpi = [
            {"$match": match_stage},
            {
                "$group": {
                    "_id": None,
                    "total_spend": {"$sum": "$total"},
                    "bill_count": {"$sum": 1},
                    "dealers": {"$addToSet": "$dealer_name"},
                    "products": {"$addToSet": "$items.product"}
                }
            }
        ]
        cursor = bills_col.aggregate(pipeline_kpi)
        kpi_list = await cursor.to_list(length=1)
        kpi_res = kpi_list[0] if kpi_list else {}

        # Query 2: Category spending
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
            },
            {"$sort": {"total_spending": -1}}
        ]
        cursor = bills_col.aggregate(pipeline_category)
        category_spending = await cursor.to_list(length=100)

        # Query 3: Top Products
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
        top_products = await cursor.to_list(length=100)

        # Query 4: Month-by-Month spending trend
        pipeline_history = [
            {"$match": match_stage},
            {
                "$project": {
                    "total": "$total",
                    "date_obj": {"$dateFromString": {"dateString": "$date", "onError": None, "onNull": None}}
                }
            },
            {
                "$group": {
                    "_id": {
                        "month": {"$month": "$date_obj"}
                    },
                    "total_amount": {"$sum": "$total"},
                    "bill_count": {"$sum": 1}
                }
            },
            {"$sort": {"_id.month": 1}}
        ]
        cursor = bills_col.aggregate(pipeline_history)
        history_list = await cursor.to_list(length=12)
        
        monthly_spend_history = []
        for h in history_list:
            if h["_id"] and h["_id"].get("month"):
                month_num = h["_id"]["month"]
                month_name = datetime(2000, month_num, 1).strftime("%b")
                monthly_spend_history.append({
                    "month_num": month_num,
                    "label": month_name,
                    "total_amount": h["total_amount"],
                    "bill_count": h["bill_count"]
                })
        # Sort chronologically by month_num
        monthly_spend_history = sorted(monthly_spend_history, key=lambda x: x["month_num"])

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

        # Query 6: Price Intelligence (Fluctuation Analysis)
        pipeline_prices = [
            {"$match": match_stage},
            {"$unwind": "$items"},
            {"$sort": {"date": 1}},
            {
                "$group": {
                    "_id": "$items.product",
                    "earliest_price": {"$first": "$items.price"},
                    "latest_price": {"$last": "$items.price"},
                    "avg_price": {"$avg": "$items.price"},
                    "purchase_count": {"$sum": 1}
                }
            },
            {
                "$project": {
                    "product_name": "$_id",
                    "earliest_price": 1,
                    "latest_price": 1,
                    "avg_price": 1,
                    "price_change_pct": {
                        "$cond": [
                            {"$gt": ["$earliest_price", 0]},
                            {"$multiply": [{"$divide": [{"$subtract": ["$latest_price", "$earliest_price"]}, "$earliest_price"]}, 100]},
                            0.0
                        ]
                    }
                }
            }
        ]
        cursor = bills_col.aggregate(pipeline_prices)
        price_analysis = await cursor.to_list(length=100)

        # Query 7: Quarterly Category Spending
        pipeline_quarterly_category = [
            {"$match": match_stage},
            {
                "$addFields": {
                    "tax_factor": {
                        "$cond": [
                            {"$gt": ["$subtotal", 0]},
                            {"$divide": ["$total", "$subtotal"]},
                            1.0
                        ]
                    },
                    "date_obj": {"$dateFromString": {"dateString": "$date", "onError": None, "onNull": None}}
                }
            },
            {
                "$addFields": {
                    "quarter": {
                        "$cond": [
                            {"$lte": [{"$month": "$date_obj"}, 3]}, "Q1",
                            {"$cond": [
                                {"$lte": [{"$month": "$date_obj"}, 6]}, "Q2",
                                {"$cond": [
                                    {"$lte": [{"$month": "$date_obj"}, 9]}, "Q3",
                                    "Q4"
                                ]}
                            ]}
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
                    "quarter": 1,
                    "category": {"$ifNull": ["$product_info.category", "Uncategorized"]},
                    "amount_with_tax": {"$multiply": ["$items.amount", "$tax_factor"]}
                }
            },
            {
                "$group": {
                    "_id": {
                        "quarter": "$quarter",
                        "category": "$category"
                    },
                    "total_spending": {"$sum": "$amount_with_tax"}
                }
            }
        ]
        cursor = bills_col.aggregate(pipeline_quarterly_category)
        quarterly_category_list = await cursor.to_list(length=1000)

        # Classify products by price stability
        stable_products = [p for p in price_analysis if abs(p["price_change_pct"]) <= 1.0][:5]
        price_increases = sorted([p for p in price_analysis if p["price_change_pct"] > 1.0], key=lambda x: x["price_change_pct"], reverse=True)[:5]
        price_decreases = sorted([p for p in price_analysis if p["price_change_pct"] < -1.0], key=lambda x: x["price_change_pct"])[:5]

        # Calculate high/low spending months
        highest_spend_month = "N/A"
        lowest_spend_month = "N/A"
        highest_val = -1.0
        lowest_val = float('inf')
        
        for m in monthly_spend_history:
            amt = m["total_amount"]
            if amt > highest_val:
                highest_val = amt
                highest_spend_month = f"{m['label']} (₹{amt:,.2f})"
            if amt < lowest_val:
                lowest_val = amt
                lowest_spend_month = f"{m['label']} (₹{amt:,.2f})"

        # Clean products list count
        flat_products_list = []
        for x in kpi_res.get("products", []):
            if isinstance(x, list):
                flat_products_list.extend(x)
            else:
                flat_products_list.append(x)
        unique_products_count = len(set(flat_products_list))

        return {
            "yearly_spend_total": kpi_res.get("total_spend", 0.0),
            "yearly_bills_count": kpi_res.get("bill_count", 0),
            "yearly_dealers_count": len(kpi_res.get("dealers", [])),
            "yearly_products_count": unique_products_count,
            "category_spending": category_spending,
            "top_products": top_products,
            "monthly_spend_history": monthly_spend_history,
            "dealer_spending": dealer_spending,
            "price_increases": price_increases,
            "price_decreases": price_decreases,
            "stable_products": stable_products,
            "highest_spend_month": highest_spend_month,
            "lowest_spend_month": lowest_spend_month,
            "quarterly_category_spending": quarterly_category_list
        }

    async def _generate_ai_summary(self, year_label: str, analytics_data: Dict[str, Any]) -> str:
        """Sends data to the LLM to get a comprehensive annual report summary and predictions."""
        category_summary = [
            {"category": item["_id"], "spent": f"INR {item['total_spending']:,.2f}"}
            for item in analytics_data["category_spending"][:5]
        ]
        products_summary = [
            {"product": item["_id"], "amount": f"INR {item['total_amount_spent']:,.2f}"}
            for item in analytics_data["top_products"][:5]
        ]
        supplier_summary = [
            {"supplier": item["_id"], "spent": f"INR {item['total_spend']:,.2f}"}
            for item in analytics_data["dealer_spending"][:5]
        ]

        system_prompt = (
            "You are the Yearly Procurement Intelligence Agent. Your job is to analyze the annual purchase report metrics "
            "provided by the user and write a comprehensive, professional executive summary with future predictions.\n"
            "Format your output in these explicit sections:\n"
            "1. Annual Business Overview\n"
            "2. Key Spending & Category Insights\n"
            "3. Supplier Performance & cost-saving opportunities\n"
            "4. Business Risks & Predictions for Next Year (Including spending forecasts and supplier recommendations)\n"
            "Use a formal, data-driven business tone. Keep the entire response under 280 words."
        )

        user_content = (
            f"Annual purchase report details for Year {year_label}:\n"
            f"- Total spent: INR {analytics_data['yearly_spend_total']:,.2f}\n"
            f"- Total invoices processed: {analytics_data['yearly_bills_count']}\n"
            f"- Active suppliers: {analytics_data['yearly_dealers_count']}\n"
            f"- Unique products purchased: {analytics_data['yearly_products_count']}\n"
            f"- Highest spending month: {analytics_data['highest_spend_month']}\n"
            f"- Lowest spending month: {analytics_data['lowest_spend_month']}\n"
            f"- Category Spending: {json.dumps(category_summary)}\n"
            f"- Top Products: {json.dumps(products_summary)}\n"
            f"- Top Suppliers: {json.dumps(supplier_summary)}\n"
            f"- YoY Spend Growth Status: {'Has prior year' if analytics_data.get('has_prior_year') else 'Baseline Year'}. "
            f"Growth Rate: {analytics_data.get('spend_growth_pct', 0.0):.2f}%\n"
        )

        try:
            if not llm_chat_service.api_key:
                return "The Yearly Intelligence Agent compiled the annual data, but the OpenRouter API Key was not set to generate the executive report summary."
            
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
                max_tokens=800
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Failed to generate LLM summary for yearly report: {e}")
            return "Failed to generate AI executive summary due to LLM provider connection error."

    async def _deliver_emails(self, user_id: str, pdf_bytes: bytes, filename: str, year_label: str, org_name: str) -> List[str]:
        """Delivers report to enabled recipient emails."""
        settings_col = db_manager.get_settings_collection()
        doc = await settings_col.find_one({"user_id": user_id, "type": "agent_settings", "value.agent_type": "yearly_report"})
        
        recipients = []
        if doc and "value" in doc:
            emails_list = doc["value"].get("delivery_emails", [])
            recipients = [e["email"] for e in emails_list if e.get("is_enabled", True)]
        
        # Fallbacks
        if not recipients:
            profile_doc = await settings_col.find_one({"user_id": user_id, "type": "profile"})
            if profile_doc and "value" in profile_doc:
                recipients = [profile_doc["value"]["email"]]
                
        if not recipients:
            user_doc = await db_manager.get_users_collection().find_one({"_id": ObjectId(user_id)})
            if user_doc:
                recipients = [user_doc["email"]]

        if not recipients:
            logger.warning(f"No recipient email found for user {user_id}. Skipping email dispatch.")
            return []

        logger.info(f"Dispatching yearly report emails to: {recipients}")
        
        subject = f"Annual Purchase Intelligence Report - Year {year_label}"
        body = (
            f"Dear Team,\n\n"
            f"Please find attached your Annual Purchase Intelligence Report for the calendar year {year_label} "
            f"generated autonomously by your Yearly Business Intelligence Agent.\n\n"
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
                logger.error(f"Failed to send yearly report email to {email}: {e}")
                
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
            
            # Recalculate next run date (same month and day, but next calendar year)
            month = value.get("schedule_config", {}).get("month", 1)
            day = value.get("schedule_config", {}).get("day", 15)
            
            next_year = run_at.year + 1
            try:
                candidate = datetime(next_year, month, day, 9, 0, 0)
            except ValueError:
                candidate = datetime(next_year, month, 28, 9, 0, 0)
            
            value["next_run"] = candidate
            
            await settings_col.update_one(
                {"_id": doc["_id"]},
                {"$set": {"value": value, "updated_at": datetime.utcnow()}}
            )

yearly_report_agent = YearlyReportAgent()

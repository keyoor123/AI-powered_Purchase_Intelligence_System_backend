import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from bson import ObjectId
from app.database.database import db_manager

logger = logging.getLogger(__name__)

class AnalyticsRepository:
    def __init__(self):
        # Collections are fetched dynamically from db_manager
        pass

    def _get_bills_col(self):
        return db_manager.get_bills_collection()

    def _get_products_col(self):
        return db_manager.get_products_collection()

    def _get_dealers_col(self):
        return db_manager.get_dealers_collection()

    async def get_overall_stats(self, user_id: str) -> Dict[str, Any]:
        """Calculates dashboard overall KPIs and chronological summaries for a specific user."""
        pipeline = [
            {"$match": {"user_id": user_id}},
            {
                "$facet": {
                    "kpis": [
                        {
                            "$group": {
                                "_id": None,
                                "total_purchase_amount": {"$sum": "$total"},
                                "total_bills": {"$sum": 1},
                                "average_bill_amount": {"$avg": "$total"},
                                "highest_bill_amount": {"$max": "$total"},
                                "lowest_bill_amount": {"$min": "$total"}
                            }
                        }
                    ],
                    "monthly_summary": [
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
                    ],
                    "yearly_summary": [
                        {
                            "$project": {
                                "total": "$total",
                                "date_obj": {"$dateFromString": {"dateString": "$date", "onError": None, "onNull": None}}
                            }
                        },
                        {
                            "$group": {
                                "_id": {"year": {"$year": "$date_obj"}},
                                "total_amount": {"$sum": "$total"},
                                "bill_count": {"$sum": 1}
                            }
                        },
                        {"$sort": {"_id.year": 1}}
                    ],
                    "unique_products": [
                        {"$unwind": "$items"},
                        {"$group": {"_id": "$items.product"}},
                        {"$count": "count"}
                    ],
                    "unique_dealers": [
                        {"$group": {"_id": "$dealer_name"}},
                        {"$count": "count"}
                    ]
                }
            }
        ]
        
        cursor = self._get_bills_col().aggregate(pipeline)
        result_list = await cursor.to_list(length=1)
        result = result_list[0] if result_list else {}
        
        kpis = result.get("kpis", [])
        kpi_data = kpis[0] if kpis else {
            "total_purchase_amount": 0.0,
            "total_bills": 0,
            "average_bill_amount": 0.0,
            "highest_bill_amount": 0.0,
            "lowest_bill_amount": 0.0
        }
        
        # Format summaries
        monthly = []
        for item in result.get("monthly_summary", []):
            if item["_id"] and item["_id"].get("year") and item["_id"].get("month"):
                label = f"{item['_id']['year']}-{item['_id']['month']:02d}"
                monthly.append({
                    "label": label,
                    "total_amount": item["total_amount"],
                    "bill_count": item["bill_count"]
                })

        yearly = []
        for item in result.get("yearly_summary", []):
            if item["_id"] and item["_id"].get("year"):
                yearly.append({
                    "label": str(item["_id"]["year"]),
                    "total_amount": item["total_amount"],
                    "bill_count": item["bill_count"]
                })
                
        prod_count = result.get("unique_products", [])
        dealer_count = result.get("unique_dealers", [])
        
        return {
            "total_purchase_amount": kpi_data.get("total_purchase_amount") or 0.0,
            "total_bills": kpi_data.get("total_bills") or 0,
            "total_products": prod_count[0]["count"] if prod_count else 0,
            "total_dealers": dealer_count[0]["count"] if dealer_count else 0,
            "average_bill_amount": kpi_data.get("average_bill_amount") or 0.0,
            "highest_bill_amount": kpi_data.get("highest_bill_amount") or 0.0,
            "lowest_bill_amount": kpi_data.get("lowest_bill_amount") or 0.0,
            "monthly_purchase_summary": monthly,
            "yearly_purchase_summary": yearly
        }

    async def get_dealer_stats(self, dealer_name: str, user_id: str) -> Dict[str, Any]:
        """Aggregates all stats for a specific dealer belonging to the user."""
        pipeline = [
            {"$match": {"dealer_name": dealer_name, "user_id": user_id}},
            {
                "$facet": {
                    "kpis": [
                        {
                            "$group": {
                                "_id": None,
                                "total_purchase_amount": {"$sum": "$total"},
                                "number_of_bills": {"$sum": 1},
                                "average_bill_value": {"$avg": "$total"},
                                "last_purchase_date": {"$max": "$date"}
                            }
                        }
                    ],
                    "products": [
                        {"$unwind": "$items"},
                        {
                            "$group": {
                                "_id": "$items.product",
                                "total_qty": {"$sum": "$items.quantity"}
                            }
                        },
                        {"$sort": {"total_qty": -1}}
                    ],
                    "monthly": [
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
                    ],
                    "yearly": [
                        {
                            "$project": {
                                "total": "$total",
                                "date_obj": {"$dateFromString": {"dateString": "$date", "onError": None, "onNull": None}}
                            }
                        },
                        {
                            "$group": {
                                "_id": {"year": {"$year": "$date_obj"}},
                                "total_amount": {"$sum": "$total"},
                                "bill_count": {"$sum": 1}
                            }
                        },
                        {"$sort": {"_id.year": 1}}
                    ]
                }
            }
        ]
        
        cursor = self._get_bills_col().aggregate(pipeline)
        result_list = await cursor.to_list(length=1)
        result = result_list[0] if result_list else {}
        
        kpis = result.get("kpis", [])
        kpi_data = kpis[0] if kpis else {
            "total_purchase_amount": 0.0,
            "number_of_bills": 0,
            "average_bill_value": 0.0,
            "last_purchase_date": None
        }
        
        products = result.get("products", [])
        most_purchased = products[0]["_id"] if products else None
        
        monthly = []
        for item in result.get("monthly", []):
            if item["_id"] and item["_id"].get("year") and item["_id"].get("month"):
                monthly.append({
                    "label": f"{item['_id']['year']}-{item['_id']['month']:02d}",
                    "total_amount": item["total_amount"],
                    "bill_count": item["bill_count"]
                })
                
        yearly = []
        for item in result.get("yearly", []):
            if item["_id"] and item["_id"].get("year"):
                yearly.append({
                    "label": str(item["_id"]["year"]),
                    "total_amount": item["total_amount"],
                    "bill_count": item["bill_count"]
                })
                
        return {
            "dealer_name": dealer_name,
            "total_purchase_amount": kpi_data.get("total_purchase_amount") or 0.0,
            "number_of_bills": kpi_data.get("number_of_bills") or 0,
            "number_of_products_purchased": len(products),
            "monthly_purchase": monthly,
            "yearly_purchase": yearly,
            "average_bill_value": kpi_data.get("average_bill_value") or 0.0,
            "most_purchased_product": most_purchased,
            "last_purchase_date": kpi_data.get("last_purchase_date")
        }

    async def get_dealer_common_products(self, dealer_a: str, dealer_b: str, user_id: str) -> List[Dict[str, Any]]:
        """Returns side-by-side stats of products purchased from both dealers under the user's account."""
        pipeline = [
            {"$match": {"dealer_name": {"$in": [dealer_a, dealer_b]}, "user_id": user_id}},
            {"$unwind": "$items"},
            {
                "$group": {
                    "_id": {
                        "product": "$items.product",
                        "dealer": "$dealer_name"
                    },
                    "total_qty": {"$sum": "$items.quantity"},
                    "avg_price": {"$avg": "$items.price"},
                    "total_amount": {"$sum": "$items.amount"}
                }
            },
            {
                "$group": {
                    "_id": "$_id.product",
                    "dealers_data": {
                        "$push": {
                            "dealer": "$_id.dealer",
                            "total_qty": "$total_qty",
                            "avg_price": "$avg_price",
                            "total_amount": "$total_amount"
                        }
                    }
                }
            },
            # Filter where both dealers have supplied the product
            {"$match": {"dealers_data": {"$size": 2}}}
        ]
        cursor = self._get_bills_col().aggregate(pipeline)
        return await cursor.to_list(length=100)

    async def get_all_products_stats(self, user_id: str) -> List[Dict[str, Any]]:
        """Aggregates purchase stats for all products under the user's account."""
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$unwind": "$items"},
            {
                "$group": {
                    "_id": "$items.product",
                    "total_quantity_purchased": {"$sum": "$items.quantity"},
                    "total_amount_spent": {"$sum": "$items.amount"},
                    "average_price": {"$avg": "$items.price"},
                    "min_price": {"$min": "$items.price"},
                    "max_price": {"$max": "$items.price"},
                    "dealers": {"$addToSet": "$dealer_name"},
                    "last_purchase_date": {"$max": "$date"},
                    # Group dates to compute frequency later
                    "purchase_dates": {"$push": "$date"}
                }
            }
        ]
        cursor = self._get_bills_col().aggregate(pipeline)
        return await cursor.to_list(length=1000)

    async def get_product_stats(self, product_name: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Aggregates stats for a single product under the user's account."""
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$unwind": "$items"},
            {"$match": {"items.product": product_name}},
            {
                "$group": {
                    "_id": "$items.product",
                    "total_quantity_purchased": {"$sum": "$items.quantity"},
                    "total_amount_spent": {"$sum": "$items.amount"},
                    "average_price": {"$avg": "$items.price"},
                    "min_price": {"$min": "$items.price"},
                    "max_price": {"$max": "$items.price"},
                    "dealers": {"$addToSet": "$dealer_name"},
                    "last_purchase_date": {"$max": "$date"},
                    "purchase_dates": {"$push": "$date"}
                }
            }
        ]
        cursor = self._get_bills_col().aggregate(pipeline)
        res = await cursor.to_list(length=1)
        return res[0] if res else None

    async def get_product_dealer_prices(self, product_name: str, user_id: str) -> List[Dict[str, Any]]:
        """Finds pricing of a specific product across all dealers under the user's account."""
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$unwind": "$items"},
            {"$match": {"items.product": product_name}},
            {
                "$group": {
                    "_id": "$dealer_name",
                    "average_price": {"$avg": "$items.price"},
                    "min_price": {"$min": "$items.price"},
                    "max_price": {"$max": "$items.price"},
                    "last_purchase_date": {"$max": "$date"}
                }
            },
            {"$sort": {"average_price": 1}}
        ]
        cursor = self._get_bills_col().aggregate(pipeline)
        return await cursor.to_list(length=100)

    async def get_price_trend(self, product_name: str, user_id: str, dealer_name: str = None) -> List[Dict[str, Any]]:
        """Fetches monthly average price historical trend for a product under the user's account."""
        match_filter = {"items.product": product_name, "user_id": user_id}
        if dealer_name:
            match_filter["dealer_name"] = dealer_name
            
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$unwind": "$items"},
            {"$match": match_filter},
            {
                "$project": {
                    "price": "$items.price",
                    "date_obj": {"$dateFromString": {"dateString": "$date", "onError": None, "onNull": None}}
                }
            },
            {
                "$group": {
                    "_id": {
                        "year": {"$year": "$date_obj"},
                        "month": {"$month": "$date_obj"}
                     },
                    "average_price": {"$avg": "$price"},
                    "min_price": {"$min": "$price"},
                    "max_price": {"$max": "$price"}
                }
            },
            {"$sort": {"_id.year": 1, "_id.month": 1}}
        ]
        cursor = self._get_bills_col().aggregate(pipeline)
        return await cursor.to_list(length=100)

    async def get_all_dealers_price_trends(self, product_name: str, user_id: str) -> List[Dict[str, Any]]:
        """Fetches monthly price trends of a product grouped per dealer under the user's account."""
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$unwind": "$items"},
            {"$match": {"items.product": product_name}},
            {
                "$project": {
                    "dealer_name": "$dealer_name",
                    "price": "$items.price",
                    "date_obj": {"$dateFromString": {"dateString": "$date", "onError": None, "onNull": None}}
                }
            },
            {
                "$group": {
                    "_id": {
                        "dealer": "$dealer_name",
                        "year": {"$year": "$date_obj"},
                        "month": {"$month": "$date_obj"}
                    },
                    "average_price": {"$avg": "$price"},
                    "min_price": {"$min": "$price"},
                    "max_price": {"$max": "$price"}
                }
            },
            {
                "$group": {
                    "_id": "$_id.dealer",
                    "trend": {
                        "$push": {
                            "year": "$_id.year",
                            "month": "$_id.month",
                            "average_price": "$average_price",
                            "min_price": "$min_price",
                            "max_price": "$max_price"
                        }
                    }
                }
            }
        ]
        cursor = self._get_bills_col().aggregate(pipeline)
        return await cursor.to_list(length=100)

    async def get_purchase_trends(self, user_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """Calculates transaction summaries across Daily, Weekly, Monthly, Quarterly, and Yearly intervals under the user's account."""
        # Helper pipeline segment to convert string to date and group
        def make_trend_facet(group_by_expr):
            return [
                {
                    "$project": {
                        "total": "$total",
                        "date_obj": {"$dateFromString": {"dateString": "$date", "onError": None, "onNull": None}}
                    }
                },
                {
                    "$group": {
                        "_id": group_by_expr,
                        "total_amount": {"$sum": "$total"},
                        "bill_count": {"$sum": 1}
                    }
                },
                {"$sort": {"_id": 1}}
            ]

        pipeline = [
            {"$match": {"user_id": user_id}},
            {
                "$facet": {
                    "daily": make_trend_facet({"$dateToString": {"format": "%Y-%m-%d", "date": "$date_obj"}}),
                    "weekly": make_trend_facet({"$dateToString": {"format": "%Y-W%U", "date": "$date_obj"}}),
                    "monthly": make_trend_facet({"$dateToString": {"format": "%Y-%m", "date": "$date_obj"}}),
                    "quarterly": make_trend_facet({
                        "year": {"$year": "$date_obj"},
                        "quarter": {"$ceil": {"$divide": [{"$month": "$date_obj"}, 3]}}
                    }),
                    "yearly": make_trend_facet({"$dateToString": {"format": "%Y", "date": "$date_obj"}})
                }
            }
        ]
        
        cursor = self._get_bills_col().aggregate(pipeline)
        res_list = await cursor.to_list(length=1)
        res = res_list[0] if res_list else {}
        
        # Format quarterly response
        formatted_quarterly = []
        for item in res.get("quarterly", []):
            if isinstance(item["_id"], dict) and "year" in item["_id"] and "quarter" in item["_id"]:
                formatted_quarterly.append({
                    "label": f"{item['_id']['year']}-Q{item['_id']['quarter']}",
                    "total_amount": item["total_amount"],
                    "bill_count": item["bill_count"]
                })
        
        return {
            "daily_purchase": [{"label": item["_id"], "total_amount": item["total_amount"], "bill_count": item["bill_count"]} for item in res.get("daily", []) if item["_id"]],
            "weekly_purchase": [{"label": item["_id"], "total_amount": item["total_amount"], "bill_count": item["bill_count"]} for item in res.get("weekly", []) if item["_id"]],
            "monthly_purchase": [{"label": item["_id"], "total_amount": item["total_amount"], "bill_count": item["bill_count"]} for item in res.get("monthly", []) if item["_id"]],
            "quarterly_purchase": formatted_quarterly,
            "yearly_purchase": [{"label": item["_id"], "total_amount": item["total_amount"], "bill_count": item["bill_count"]} for item in res.get("yearly", []) if item["_id"]]
        }

    async def get_category_spending(self, user_id: str) -> List[Dict[str, Any]]:
        """Performs join aggregation to group purchases by user-specific product categories."""
        pipeline = [
            {"$match": {"user_id": user_id}},
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
                    "amount": "$items.amount",
                    "quantity": "$items.quantity",
                    "date_obj": {"$dateFromString": {"dateString": "$date", "onError": None, "onNull": None}}
                }
            },
            {
                "$group": {
                    "_id": {
                        "category": "$category",
                        "year": {"$year": "$date_obj"},
                        "month": {"$month": "$date_obj"}
                    },
                    "total_spending": {"$sum": "$amount"},
                    "total_quantity": {"$sum": "$quantity"}
                }
            },
            {
                "$group": {
                    "_id": "$_id.category",
                    "total_spending": {"$sum": "$total_spending"},
                    "total_quantity": {"$sum": "$total_quantity"},
                    "monthly_history": {
                        "$push": {
                            "year": "$_id.year",
                            "month": "$_id.month",
                            "spending": "$total_spending"
                        }
                     }
                }
            }
        ]
        cursor = self._get_bills_col().aggregate(pipeline)
        return await cursor.to_list(length=100)

    async def get_all_bill_items(self, user_id: str) -> List[Dict[str, Any]]:
        """Returns lists of products per bill to support Market Basket Analysis for a specific user."""
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$unwind": "$items"},
            {
                "$group": {
                    "_id": "$_id",
                    "products": {"$addToSet": "$items.product"}
                }
            }
        ]
        cursor = self._get_bills_col().aggregate(pipeline)
        return await cursor.to_list(length=1000)

    async def get_recent_prices_history(self, user_id: str) -> List[Dict[str, Any]]:
        """Returns raw historical item transactions for price change alerts under the user's account."""
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$unwind": "$items"},
            {
                "$project": {
                    "product": "$items.product",
                    "price": "$items.price",
                    "quantity": "$items.quantity",
                    "dealer": "$dealer_name",
                    "date": "$date"
                }
            },
            {"$sort": {"date": 1}}
        ]
        cursor = self._get_bills_col().aggregate(pipeline)
        return await cursor.to_list(length=5000)

# Singleton analytics repository
analytics_repository = AnalyticsRepository()

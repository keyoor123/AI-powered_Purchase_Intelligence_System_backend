import logging
from app.analytics.repositories.analytics_repository import analytics_repository
from app.analytics.schemas.responses import DashboardResponse

logger = logging.getLogger(__name__)

class DashboardService:
    async def get_dashboard_data(self, user_id: str) -> DashboardResponse:
        """Retrieves and formats dashboard analytical summaries for the given user."""
        logger.info(f"Fetching overall dashboard analytics for user: {user_id}")
        raw_data = await analytics_repository.get_overall_stats(user_id)
        return DashboardResponse(**raw_data)

dashboard_service = DashboardService()

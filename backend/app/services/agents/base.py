from abc import ABC, abstractmethod

class BaseAgent(ABC):
    @property
    @abstractmethod
    def agent_type(self) -> str:
        """Unique identifier of this agent, e.g. 'monthly_report'."""
        pass

    @abstractmethod
    async def run(self, user_id: str, context: dict = None) -> bool:
        """
        Executes the agent core logic.
        
        Args:
            user_id: The ID of the user the agent is running for.
            context: Optional dict containing context configurations.
            
        Returns:
            True if execution was successful, False otherwise.
        """
        pass

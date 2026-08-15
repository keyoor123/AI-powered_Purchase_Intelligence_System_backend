import time
import logging
from threading import Lock
from fastapi import Request, HTTPException, status

logger = logging.getLogger(__name__)

class IPRateLimiter:
    def __init__(self, limit: int = 5, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self.requests = {}
        self.lock = Lock()

    def is_rate_limited(self, ip: str, path: str) -> bool:
        current_time = time.time()
        key = f"{ip}:{path}"
        
        with self.lock:
            if key not in self.requests:
                self.requests[key] = []
            
            # Filter out timestamps older than the window
            self.requests[key] = [
                t for t in self.requests[key] 
                if current_time - t < self.window_seconds
            ]
            
            if len(self.requests[key]) >= self.limit:
                return True
            
            # Record current request timestamp
            self.requests[key].append(current_time)
            return False

# Create a singleton rate limiter instance with 5 requests per 60 seconds
auth_limiter = IPRateLimiter(limit=5, window_seconds=60)

async def verify_ip_rate_limit(request: Request):
    """FastAPI dependency to verify IP request limits."""
    # Retrieve client IP, checking for proxy headers first, falling back to client.host
    client_ip = request.headers.get("x-forwarded-for")
    if client_ip:
        client_ip = client_ip.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "127.0.0.1"
        
    path = request.url.path
    
    if auth_limiter.is_rate_limited(client_ip, path):
        logger.warning(f"Rate limit exceeded: IP {client_ip} on path {path}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again after some time."
        )

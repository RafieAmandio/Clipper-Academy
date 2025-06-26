"""Base classes for social media integration"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel


class SocialMediaPost(BaseModel):
    """Model for social media post data"""
    platform: str
    video_path: str
    caption: str
    hashtags: list[str]
    scheduled_time: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


class SocialMediaPlatform(ABC):
    """Base class for social media platform integration"""
    
    @abstractmethod
    async def validate_credentials(self) -> bool:
        """Validate platform credentials"""
        pass
    
    @abstractmethod
    async def upload_video(self, post: SocialMediaPost) -> Dict[str, Any]:
        """Upload video to platform"""
        pass
    
    @abstractmethod
    async def schedule_post(self, post: SocialMediaPost) -> Dict[str, Any]:
        """Schedule post for later publication"""
        pass
    
    @abstractmethod
    async def get_post_status(self, post_id: str) -> Dict[str, Any]:
        """Get status of a post"""
        pass 
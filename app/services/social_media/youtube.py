"""YouTube platform integration"""

import logging
from typing import Dict, Any
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from app.services.social_media.base import SocialMediaPlatform, SocialMediaPost
from app.core.exceptions import SocialMediaError

logger = logging.getLogger(__name__)

class YouTubePlatform(SocialMediaPlatform):
    """YouTube platform integration"""
    
    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self._service = None
    
    async def validate_credentials(self) -> bool:
        """Validate YouTube credentials"""
        try:
            service = await self._get_service()
            # Test API access
            service.channels().list(part="snippet", mine=True).execute()
            return True
        except Exception as e:
            logger.error(f"YouTube credentials validation failed: {e}")
            return False
    
    async def _get_service(self):
        """Get or create YouTube API service"""
        if self._service is None:
            credentials = Credentials(
                None,
                refresh_token=self.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.client_id,
                client_secret=self.client_secret
            )
            
            self._service = build("youtube", "v3", credentials=credentials)
        
        return self._service
    
    async def upload_video(self, post: SocialMediaPost) -> Dict[str, Any]:
        """Upload video to YouTube"""
        try:
            youtube = await self._get_service()
            
            # Prepare video metadata
            body = {
                "snippet": {
                    "title": post.caption.split("\n")[0],  # Use first line as title
                    "description": post.caption,
                    "tags": post.metadata.get("tags", []) if post.metadata else [],
                    "categoryId": "22"  # People & Blogs category
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False
                }
            }
            
            # Create media file upload
            media = MediaFileUpload(
                post.video_path,
                mimetype="video/mp4",
                resumable=True
            )
            
            # Upload video
            request = youtube.videos().insert(
                part=",".join(body.keys()),
                body=body,
                media_body=media
            )
            
            response = request.execute()
            
            return {
                "post_id": response["id"],
                "url": f"https://youtube.com/shorts/{response['id']}"
            }
            
        except Exception as e:
            logger.error(f"YouTube upload failed: {e}")
            raise SocialMediaError(f"Failed to upload to YouTube: {str(e)}")
    
    async def schedule_post(self, post: SocialMediaPost) -> Dict[str, Any]:
        """Schedule post for later publication"""
        # YouTube doesn't support direct scheduling through the API
        # We'll need to implement our own scheduling system
        raise SocialMediaError("YouTube scheduling not implemented yet")
    
    async def get_post_status(self, post_id: str) -> Dict[str, Any]:
        """Get status of a YouTube post"""
        try:
            youtube = await self._get_service()
            
            # Get video details
            response = youtube.videos().list(
                part="status,snippet",
                id=post_id
            ).execute()
            
            if not response["items"]:
                raise SocialMediaError(f"Video not found: {post_id}")
            
            video = response["items"][0]
            
            return {
                "post_id": post_id,
                "status": video["status"]["uploadStatus"],
                "privacy": video["status"]["privacyStatus"],
                "title": video["snippet"]["title"],
                "url": f"https://youtube.com/watch?v={post_id}"
            }
            
        except Exception as e:
            logger.error(f"Failed to get YouTube post status: {e}")
            raise SocialMediaError(f"Failed to get post status: {str(e)}") 
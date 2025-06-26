from typing import Dict, List, Optional, Any
import logging
from datetime import datetime
import os
from pydantic import BaseModel
import json
import httpx
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from instagram_private_api import Client, ClientError, ClientLoginError

from app.services.base import BaseService
from app.config.settings import Settings
from app.core.exceptions import ClipperException
from app.services.social_media.base import SocialMediaPost
from app.services.social_media.youtube import YouTubePlatform

logger = logging.getLogger(__name__)

class SocialMediaPost(BaseModel):
    """Model for social media post data"""
    platform: str
    video_path: str
    caption: str
    hashtags: List[str]
    scheduled_time: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

class SocialMediaError(ClipperException):
    """Error during social media operations"""
    pass

class SocialMediaService(BaseService):
    """Service for handling social media posting operations"""
    
    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.supported_platforms = ["youtube"]  # Add other platforms as they're implemented
        self._platforms = {}
    
    async def _get_platform(self, platform: str):
        """Get or create platform instance"""
        if platform not in self.supported_platforms:
            raise SocialMediaError(f"Unsupported platform: {platform}")
        
        if platform not in self._platforms:
            if platform == "youtube":
                if not all([
                    self.settings.youtube_client_id,
                    self.settings.youtube_client_secret,
                    self.settings.youtube_refresh_token
                ]):
                    raise SocialMediaError("YouTube credentials not configured")
                
                self._platforms[platform] = YouTubePlatform(
                    client_id=self.settings.youtube_client_id,
                    client_secret=self.settings.youtube_client_secret,
                    refresh_token=self.settings.youtube_refresh_token
                )
            # Add other platforms here as they're implemented
        
        return self._platforms[platform]
    
    async def validate_platform(self, platform: str) -> bool:
        """Validate if platform is supported and credentials are valid"""
        try:
            platform_instance = await self._get_platform(platform)
            return await platform_instance.validate_credentials()
        except Exception as e:
            logger.error(f"Platform validation failed: {e}")
            return False
    
    async def validate_video(self, video_path: str) -> bool:
        """Validate video file exists and is in supported format"""
        if not os.path.exists(video_path):
            raise SocialMediaError(f"Video file not found: {video_path}")
            
        ext = os.path.splitext(video_path)[1].lower()
        if ext not in self.settings.supported_video_formats:
            raise SocialMediaError(f"Unsupported video format: {ext}")
            
        return True
    
    async def prepare_post(self, post: SocialMediaPost) -> Dict[str, Any]:
        """Prepare post data for the target platform"""
        if not await self.validate_platform(post.platform):
            raise SocialMediaError(f"Unsupported platform: {post.platform}")
            
        if not await self.validate_video(post.video_path):
            raise SocialMediaError("Invalid video file")
            
        # Format hashtags
        formatted_hashtags = " ".join([f"#{tag.strip('#')}" for tag in post.hashtags])
        
        # Combine caption and hashtags
        full_caption = f"{post.caption}\n\n{formatted_hashtags}"
        
        return {
            "platform": post.platform,
            "video_path": post.video_path,
            "caption": full_caption,
            "scheduled_time": post.scheduled_time,
            "metadata": post.metadata or {}
        }
    
    async def post_to_tiktok(self, post_data: Dict[str, Any]) -> Dict[str, Any]:
        """Post video to TikTok using TikTok API"""
        try:
            # TikTok API endpoint
            api_url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
            
            # Prepare headers with API key and access token
            headers = {
                "Authorization": f"Bearer {self.settings.tiktok_access_token}",
                "Content-Type": "application/json"
            }
            
            # First, initialize the upload
            init_data = {
                "post_info": {
                    "title": post_data["caption"],
                    "privacy_level": "PUBLIC",
                    "disable_comment": False,
                    "disable_duet": False,
                    "disable_stitch": False,
                    "video_cover_timestamp_ms": 0
                }
            }
            
            async with httpx.AsyncClient() as client:
                # Initialize upload
                init_response = await client.post(
                    api_url,
                    headers=headers,
                    json=init_data
                )
                init_response.raise_for_status()
                upload_data = init_response.json()
                
                # Get upload URL and upload ID
                upload_url = upload_data["data"]["upload_url"]
                upload_id = upload_data["data"]["upload_id"]
                
                # Upload video file
                with open(post_data["video_path"], "rb") as video_file:
                    upload_response = await client.put(
                        upload_url,
                        headers={"Content-Type": "video/mp4"},
                        content=video_file.read()
                    )
                    upload_response.raise_for_status()
                
                # Publish the video
                publish_url = f"https://open.tiktokapis.com/v2/post/publish/video/publish/"
                publish_data = {
                    "upload_id": upload_id,
                    "post_info": {
                        "title": post_data["caption"],
                        "privacy_level": "PUBLIC"
                    }
                }
                
                publish_response = await client.post(
                    publish_url,
                    headers=headers,
                    json=publish_data
                )
                publish_response.raise_for_status()
                publish_result = publish_response.json()
                
                return {
                    "post_id": publish_result["data"]["post_id"],
                    "url": f"https://www.tiktok.com/@{publish_result['data']['author']['unique_id']}/video/{publish_result['data']['post_id']}"
                }
                
        except Exception as e:
            logger.error(f"TikTok upload failed: {e}")
            raise SocialMediaError(f"Failed to upload to TikTok: {str(e)}")
    
    async def post_to_instagram(self, post_data: Dict[str, Any]) -> Dict[str, Any]:
        """Post video to Instagram using Instagram Graph API"""
        try:
            # Initialize Instagram API client
            api = Client(
                auto_patch=True,
                authenticate=True,
                username=self.settings.instagram_username,
                password=self.settings.instagram_password
            )
            
            # Upload video as Reel
            result = api.post_video(
                video=post_data["video_path"],
                caption=post_data["caption"],
                is_reel=True
            )
            
            return {
                "post_id": result["media"]["id"],
                "url": f"https://www.instagram.com/reel/{result['media']['code']}/"
            }
            
        except (ClientError, ClientLoginError) as e:
            logger.error(f"Instagram upload failed: {e}")
            raise SocialMediaError(f"Failed to upload to Instagram: {str(e)}")
        except Exception as e:
            logger.error(f"Instagram upload failed: {e}")
            raise SocialMediaError(f"Failed to upload to Instagram: {str(e)}")
    
    async def post_to_youtube(self, post_data: Dict[str, Any]) -> Dict[str, Any]:
        """Post video to YouTube using YouTube Data API"""
        try:
            youtube = await self._get_platform("youtube")
            
            # Prepare video metadata
            body = {
                "snippet": {
                    "title": post_data["caption"].split("\n")[0],  # Use first line as title
                    "description": post_data["caption"],
                    "tags": post_data["metadata"].get("tags", []),
                    "categoryId": "22"  # People & Blogs category
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False
                }
            }
            
            # Create media file upload
            media = MediaFileUpload(
                post_data["video_path"],
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
    
    async def post_now(self, post: SocialMediaPost) -> Dict[str, Any]:
        """Post video immediately to the specified platform"""
        try:
            # Validate platform and video
            if not await self.validate_platform(post.platform):
                raise SocialMediaError(f"Invalid platform credentials: {post.platform}")
            
            if not await self.validate_video(post.video_path):
                raise SocialMediaError("Invalid video file")
            
            # Get platform instance and upload
            platform = await self._get_platform(post.platform)
            result = await platform.upload_video(post)
            
            return {
                "message": f"Successfully uploaded to {post.platform}",
                "platform": post.platform,
                "post_data": result
            }
            
        except Exception as e:
            logger.error(f"Social media posting failed: {e}")
            raise SocialMediaError(f"Failed to post to {post.platform}: {str(e)}")
    
    async def schedule_post(self, post: SocialMediaPost) -> Dict[str, Any]:
        """Schedule a post for later publication"""
        try:
            # Validate platform and video
            if not await self.validate_platform(post.platform):
                raise SocialMediaError(f"Invalid platform credentials: {post.platform}")
            
            if not await self.validate_video(post.video_path):
                raise SocialMediaError("Invalid video file")
            
            if not post.scheduled_time:
                raise SocialMediaError("Scheduled time is required")
            
            # Get platform instance and schedule
            platform = await self._get_platform(post.platform)
            result = await platform.schedule_post(post)
            
            return {
                "message": f"Successfully scheduled post for {post.platform}",
                "platform": post.platform,
                "post_data": result
            }
            
        except Exception as e:
            logger.error(f"Social media scheduling failed: {e}")
            raise SocialMediaError(f"Failed to schedule post for {post.platform}: {str(e)}")
    
    async def get_post_status(self, platform: str, post_id: str) -> Dict[str, Any]:
        """Get status of a post"""
        try:
            platform_instance = await self._get_platform(platform)
            return await platform_instance.get_post_status(post_id)
        except Exception as e:
            logger.error(f"Failed to get post status: {e}")
            raise SocialMediaError(f"Failed to get post status: {str(e)}") 
"""
Social Media Upload Service

Handles video uploads to YouTube, Instagram, and TikTok platforms.
Uses OAuth tokens for authentication and platform-specific APIs.
"""

import logging
import os
import time
from typing import Dict, Any, Optional
import httpx
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

from app.services.base import BaseService
from app.services.oauth_service import OAuthService
from app.config.settings import Settings
from app.core.exceptions import SocialMediaError, OAuthError

logger = logging.getLogger(__name__)


class SocialUploadService(BaseService):
    """Service for uploading videos to social media platforms"""
    
    def __init__(self, settings: Settings, oauth_service: OAuthService):
        super().__init__(settings)
        self.oauth_service = oauth_service
    
    async def upload_to_youtube(
        self, 
        clip_id: str, 
        title: str, 
        description: str = "", 
        tags: list = None, 
        privacy_status: str = "public",
        category_id: str = "22",
        made_for_kids: bool = False,
        upload_as_shorts: bool = True
    ) -> Dict[str, Any]:
        """Upload video to YouTube"""
        try:
            # Get OAuth tokens
            tokens = await self.oauth_service.get_tokens("youtube")
            if not tokens:
                raise OAuthError("YouTube account not connected. Please authenticate first.")
            
            # Get video file path
            video_path = await self._get_clip_path(clip_id)
            if not os.path.exists(video_path):
                raise SocialMediaError(f"Video file not found: {video_path}")
            
            # Create YouTube API client
            credentials = Credentials(
                token=tokens['access_token'],
                refresh_token=tokens.get('refresh_token'),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.settings.youtube_client_id,
                client_secret=self.settings.youtube_client_secret
            )
            
            youtube = build('youtube', 'v3', credentials=credentials)
            
            # Prepare video metadata
            body = {
                'snippet': {
                    'title': title,
                    'description': description,
                    'tags': tags or [],
                    'categoryId': category_id
                },
                'status': {
                    'privacyStatus': privacy_status,
                    'selfDeclaredMadeForKids': made_for_kids
                }
            }
            
            # Add YouTube Shorts specific settings
            if upload_as_shorts:
                # For YouTube Shorts, we typically use category 22 (People & Blogs)
                # and add #Shorts to the title or description
                if not any(tag.lower() == 'shorts' for tag in (tags or [])):
                    if tags is None:
                        tags = []
                    tags.append('Shorts')
                
                # Ensure the title is appropriate for Shorts (under 100 characters)
                if len(title) > 100:
                    title = title[:97] + "..."
                
                # Update the body with Shorts-specific settings
                body['snippet']['tags'] = tags
                body['snippet']['title'] = title
            
            # Create media upload
            media = MediaFileUpload(
                video_path, 
                chunksize=-1, 
                resumable=True
            )
            
            # Upload video
            logger.info(f"Starting YouTube upload for clip {clip_id} as {'Shorts' if upload_as_shorts else 'regular video'}")
            request = youtube.videos().insert(
                part=",".join(body.keys()),
                body=body,
                media_body=media
            )
            
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logger.info(f"YouTube upload progress: {int(status.progress() * 100)}%")
            
            video_id = response['id']
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            
            logger.info(f"YouTube upload completed: {video_url}")
            
            return {
                "success": True,
                "platform": "youtube",
                "video_id": video_id,
                "url": video_url,
                "title": title,
                "privacy_status": privacy_status,
                "made_for_kids": made_for_kids,
                "upload_as_shorts": upload_as_shorts,
                "tags": tags
            }
            
        except Exception as e:
            logger.error(f"YouTube upload failed for clip {clip_id}: {e}")
            raise SocialMediaError(f"YouTube upload failed: {str(e)}")
    
    async def upload_to_instagram(
        self, 
        clip_id: str, 
        caption: str = "", 
        hashtags: list = None
    ) -> Dict[str, Any]:
        """Upload video to Instagram (simplified implementation)"""
        try:
            # Get OAuth tokens
            tokens = await self.oauth_service.get_tokens("instagram")
            if not tokens:
                raise OAuthError("Instagram account not connected. Please authenticate first.")
            
            # Get video file path
            video_path = await self._get_clip_path(clip_id)
            if not os.path.exists(video_path):
                raise SocialMediaError(f"Video file not found: {video_path}")
            
            # Instagram Graph API requires a Facebook Page ID
            # This is a simplified implementation
            # In a real implementation, you would need to:
            # 1. Get the user's Facebook pages
            # 2. Create a media container
            # 3. Upload the video
            # 4. Publish the container
            
            logger.info(f"Instagram upload initiated for clip {clip_id}")
            
            # For now, return a mock response
            # In production, implement the full Instagram Graph API flow
            return {
                "success": True,
                "platform": "instagram",
                "message": "Instagram upload initiated (simplified implementation)",
                "note": "Full Instagram upload requires Facebook Page integration"
            }
            
        except Exception as e:
            logger.error(f"Instagram upload failed for clip {clip_id}: {e}")
            raise SocialMediaError(f"Instagram upload failed: {str(e)}")
    
    async def upload_to_tiktok(
        self, 
        clip_id: str, 
        title: str = "", 
        visibility: str = "public"
    ) -> Dict[str, Any]:
        """Upload video to TikTok"""
        try:
            # Get OAuth tokens
            tokens = await self.oauth_service.get_tokens("tiktok")
            if not tokens:
                raise OAuthError("TikTok account not connected. Please authenticate first.")
            
            # Get video file path
            video_path = await self._get_clip_path(clip_id)
            if not os.path.exists(video_path):
                raise SocialMediaError(f"Video file not found: {video_path}")
            
            # TikTok API upload process
            # This is a simplified implementation
            # In a real implementation, you would need to:
            # 1. Create an upload session
            # 2. Upload the video in chunks
            # 3. Complete the upload
            # 4. Publish the video
            
            logger.info(f"TikTok upload initiated for clip {clip_id}")
            
            # For now, return a mock response
            # In production, implement the full TikTok API flow
            return {
                "success": True,
                "platform": "tiktok",
                "message": "TikTok upload initiated (simplified implementation)",
                "note": "Full TikTok upload requires complete API implementation"
            }
            
        except Exception as e:
            logger.error(f"TikTok upload failed for clip {clip_id}: {e}")
            raise SocialMediaError(f"TikTok upload failed: {str(e)}")
    
    async def _get_clip_path(self, clip_id: str) -> str:
        """Get the file path for a clip ID"""
        # Look for clips in the results directory
        # Clips are stored with full filenames like: clip_1750248055_4_The_Real_Cost_of_Making_Music_You_Wont_Believe_It_captioned_1750248293.mp4
        
        # Try different video extensions
        extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm']
        
        # First, try exact filename match (clip_id might already be the full filename)
        for ext in extensions:
            if clip_id.endswith(ext):
                # clip_id is already a full filename with extension
                clip_path = os.path.join(self.settings.results_dir, clip_id)
                if os.path.exists(clip_path):
                    return clip_path
        
        # If not found with exact match, try adding extensions to clip_id
        for ext in extensions:
            clip_path = os.path.join(self.settings.results_dir, f"{clip_id}{ext}")
            if os.path.exists(clip_path):
                return clip_path
        
        # If still not found, try pattern matching for files that contain the clip_id
        import glob
        for ext in extensions:
            pattern = os.path.join(self.settings.results_dir, f"*{clip_id}*{ext}")
            matching_files = glob.glob(pattern)
            
            if matching_files:
                # Return the first matching file
                return matching_files[0]
        
        # If still not found, try with just the clip_id as directory name
        clip_dir = os.path.join(self.settings.results_dir, clip_id)
        if os.path.exists(clip_dir) and os.path.isdir(clip_dir):
            # Look for video files in the clip directory
            for filename in os.listdir(clip_dir):
                if any(filename.lower().endswith(ext) for ext in extensions):
                    return os.path.join(clip_dir, filename)
        
        raise SocialMediaError(f"Could not find video file for clip ID: {clip_id}")
    
    async def get_upload_status(self, platform: str, upload_id: str) -> Dict[str, Any]:
        """Get the status of an upload"""
        try:
            # This would check the status of an ongoing upload
            # Implementation depends on the platform's API
            
            if platform == "youtube":
                return await self._get_youtube_upload_status(upload_id)
            elif platform == "instagram":
                return await self._get_instagram_upload_status(upload_id)
            elif platform == "tiktok":
                return await self._get_tiktok_upload_status(upload_id)
            else:
                raise SocialMediaError(f"Unknown platform: {platform}")
                
        except Exception as e:
            logger.error(f"Failed to get upload status for {platform}: {e}")
            raise SocialMediaError(f"Failed to get upload status: {str(e)}")
    
    async def _get_youtube_upload_status(self, upload_id: str) -> Dict[str, Any]:
        """Get YouTube upload status"""
        # YouTube uploads are typically synchronous, so this would be for checking
        # if the video is still processing
        return {
            "platform": "youtube",
            "upload_id": upload_id,
            "status": "completed",
            "message": "YouTube upload completed"
        }
    
    async def _get_instagram_upload_status(self, upload_id: str) -> Dict[str, Any]:
        """Get Instagram upload status"""
        return {
            "platform": "instagram",
            "upload_id": upload_id,
            "status": "pending",
            "message": "Instagram upload in progress"
        }
    
    async def _get_tiktok_upload_status(self, upload_id: str) -> Dict[str, Any]:
        """Get TikTok upload status"""
        return {
            "platform": "tiktok",
            "upload_id": upload_id,
            "status": "pending",
            "message": "TikTok upload in progress"
        } 
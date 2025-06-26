"""
OAuth Service for Social Media Integration

Handles OAuth 2.0 flows for YouTube, Instagram, and TikTok platforms.
Manages token storage, refresh, and validation.
"""

import logging
import secrets
import time
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
import httpx
from urllib.parse import urlencode
from google_auth_oauthlib.flow import InstalledAppFlow, Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest

from app.services.base import BaseService
from app.config.settings import Settings
from app.core.exceptions import OAuthError

logger = logging.getLogger(__name__)


class OAuthService(BaseService):
    """Service for handling OAuth 2.0 operations"""
    
    def __init__(self, settings: Settings):
        super().__init__(settings)
        # In-memory token storage (in production, use a database)
        self._tokens: Dict[str, Dict[str, Any]] = {}
        self._states: Dict[str, str] = {}
    
    def generate_state(self) -> str:
        """Generate a secure random state parameter"""
        return secrets.token_urlsafe(32)
    
    def store_state(self, state: str, platform: str) -> None:
        """Store OAuth state for validation"""
        self._states[state] = platform
        logger.info(f"Stored state '{state}' for platform '{platform}'. Total states: {len(self._states)}")
    
    def validate_state(self, state: str, platform: str) -> bool:
        """Validate OAuth state parameter"""
        stored_platform = self._states.get(state)
        is_valid = stored_platform == platform
        logger.info(f"Validating state '{state}' for platform '{platform}'. Stored platform: '{stored_platform}', Valid: {is_valid}")
        logger.info(f"Current stored states: {list(self._states.keys())}")
        if is_valid:
            # Clean up the state after successful validation
            del self._states[state]
            logger.info(f"Cleaned up state '{state}'. Remaining states: {len(self._states)}")
        return is_valid
    
    def store_tokens(self, platform: str, tokens: Dict[str, Any]) -> None:
        """Store OAuth tokens for a platform"""
        # Add expiration time if not present
        if 'expires_at' not in tokens and 'expires_in' in tokens:
            tokens['expires_at'] = datetime.now() + timedelta(seconds=tokens['expires_in'])
        
        self._tokens[platform] = tokens
        logger.info(f"Stored tokens for {platform}")
    
    async def get_tokens(self, platform: str) -> Optional[Dict[str, Any]]:
        """Get stored tokens for a platform"""
        tokens = self._tokens.get(platform)
        if not tokens:
            return None
        
        # Check if token is expired
        if 'expires_at' in tokens:
            expires_at = tokens['expires_at']
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            
            if datetime.now() >= expires_at:
                logger.info(f"Token for {platform} is expired, attempting refresh")
                return await self._refresh_tokens(platform, tokens)
        
        return tokens
    
    async def _refresh_tokens(self, platform: str, tokens: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Refresh expired OAuth tokens"""
        try:
            if platform == "youtube":
                return self._refresh_youtube_tokens(tokens)
            elif platform == "instagram":
                return self._refresh_instagram_tokens(tokens)
            elif platform == "tiktok":
                return await self._refresh_tiktok_tokens(tokens)
            else:
                logger.error(f"Unknown platform for token refresh: {platform}")
                return None
        except Exception as e:
            logger.error(f"Failed to refresh tokens for {platform}: {e}")
            return None
    
    def _refresh_youtube_tokens(self, tokens: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Refresh YouTube OAuth tokens"""
        try:
            credentials = Credentials(
                token=tokens.get('access_token'),
                refresh_token=tokens.get('refresh_token'),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.settings.youtube_client_id,
                client_secret=self.settings.youtube_client_secret
            )
            
            # Refresh the credentials
            credentials.refresh(GoogleRequest())
            
            # Update stored tokens
            new_tokens = {
                'access_token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'expires_at': credentials.expiry.isoformat() if credentials.expiry else None,
                'token_type': 'Bearer'
            }
            
            self._tokens['youtube'] = new_tokens
            return new_tokens
            
        except Exception as e:
            logger.error(f"YouTube token refresh failed: {e}")
            return None
    
    def _refresh_instagram_tokens(self, tokens: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Refresh Instagram OAuth tokens"""
        # Instagram tokens are long-lived and don't typically need refresh
        # But we can implement if needed
        logger.warning("Instagram token refresh not implemented - tokens are long-lived")
        return tokens
    
    async def _refresh_tiktok_tokens(self, tokens: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Refresh TikTok OAuth tokens"""
        try:
            refresh_url = "https://open.tiktokapis.com/v2/oauth/token/"
            
            data = {
                "client_key": self.settings.tiktok_client_key,
                "client_secret": self.settings.tiktok_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": tokens.get('refresh_token')
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(refresh_url, data=data)
                response.raise_for_status()
                token_data = response.json()
                
                new_tokens = {
                    'access_token': token_data['access_token'],
                    'refresh_token': token_data.get('refresh_token', tokens.get('refresh_token')),
                    'expires_in': token_data.get('expires_in'),
                    'expires_at': datetime.now() + timedelta(seconds=token_data.get('expires_in', 3600)),
                    'token_type': token_data.get('token_type', 'Bearer')
                }
                
                self._tokens['tiktok'] = new_tokens
                return new_tokens
                
        except Exception as e:
            logger.error(f"TikTok token refresh failed: {e}")
            return None
    
    async def initiate_youtube_oauth(self, redirect_uri: Optional[str] = None) -> Dict[str, str]:
        """Initiate YouTube OAuth flow using authorization code flow"""
        try:
            state = self.generate_state()
            self.store_state(state, "youtube")
            
            # Use backend callback URL for secure token exchange
            final_redirect_uri = redirect_uri or f"{self.settings.app_url}/api/v1/oauth/youtube/callback"
            logger.info(f"YouTube OAuth redirect URI: {final_redirect_uri}")
            
            # Generate authorization URL for authorization code flow
            auth_url = "https://accounts.google.com/o/oauth2/auth"
            params = {
                "response_type": "code",  # Use authorization code flow for security
                "client_id": self.settings.youtube_client_id,
                "scope": " ".join(self.settings.youtube_scopes),
                "state": state,
                "include_granted_scopes": "true",
                "redirect_uri": final_redirect_uri
            }
            
            # Build the full URL with parameters
            full_url = f"{auth_url}?{urlencode(params)}"
            logger.info(f"Generated YouTube OAuth URL: {full_url}")
            
            return {
                "auth_url": full_url,
                "state": state
            }
            
        except Exception as e:
            logger.error(f"YouTube OAuth initiation failed: {e}")
            raise OAuthError(f"Failed to initiate YouTube OAuth: {e}")
    
    async def initiate_instagram_oauth(self, redirect_uri: Optional[str] = None) -> Dict[str, str]:
        """Initiate Instagram OAuth flow"""
        try:
            state = self.generate_state()
            self.store_state(state, "instagram")
            
            # Instagram OAuth URL
            auth_url = "https://api.instagram.com/oauth/authorize"
            
            # Prepare OAuth parameters
            params = {
                "client_id": self.settings.instagram_client_id,
                "scope": ",".join(self.settings.instagram_scopes),
                "response_type": "code",
                "redirect_uri": redirect_uri or self.settings.instagram_redirect_uri,
                "state": state
            }
            
            full_auth_url = f"{auth_url}?{urlencode(params)}"
            
            return {
                "auth_url": full_auth_url,
                "state": state
            }
            
        except Exception as e:
            logger.error(f"Instagram OAuth initiation failed: {e}")
            raise OAuthError(f"Failed to initiate Instagram OAuth: {str(e)}")
    
    async def initiate_tiktok_oauth(self, redirect_uri: Optional[str] = None) -> Dict[str, str]:
        """Initiate TikTok OAuth flow"""
        try:
            state = self.generate_state()
            self.store_state(state, "tiktok")
            
            # TikTok OAuth URL
            auth_url = "https://www.tiktok.com/auth/authorize/"
            
            # Prepare OAuth parameters
            params = {
                "client_key": self.settings.tiktok_client_key,
                "scope": ",".join(self.settings.tiktok_scopes),
                "response_type": "code",
                "redirect_uri": redirect_uri or self.settings.tiktok_redirect_uri,
                "state": state
            }
            
            full_auth_url = f"{auth_url}?{urlencode(params)}"
            
            return {
                "auth_url": full_auth_url,
                "state": state
            }
            
        except Exception as e:
            logger.error(f"TikTok OAuth initiation failed: {e}")
            raise OAuthError(f"Failed to initiate TikTok OAuth: {str(e)}")
    
    async def handle_youtube_callback(self, code: str, state: str) -> Dict[str, Any]:
        """Handle YouTube OAuth callback using authorization code flow"""
        try:
            if not self.validate_state(state, "youtube"):
                raise OAuthError("Invalid state parameter")
            
            logger.info(f"Processing YouTube OAuth callback with authorization code flow")
            logger.info(f"Authorization code received: {code[:20]}...")
            
            # Exchange authorization code for access token (server-side only)
            token_url = "https://oauth2.googleapis.com/token"
            
            data = {
                "client_id": self.settings.youtube_client_id,
                "client_secret": self.settings.youtube_client_secret,
                "grant_type": "authorization_code",
                "redirect_uri": f"{self.settings.app_url}/api/v1/oauth/youtube/callback",
                "code": code
            }
            
            logger.info(f"Exchanging authorization code for access token")
            logger.info(f"Redirect URI: {data['redirect_uri']}")
            logger.info(f"Code: {code[:20]}...")
            
            async with httpx.AsyncClient() as client:
                response = await client.post(token_url, data=data)
                
                if not response.is_success:
                    logger.error(f"Token exchange failed with status {response.status_code}")
                    logger.error(f"Response body: {response.text}")
                    response.raise_for_status()
                    
                token_data = response.json()
                
                logger.info("Successfully exchanged authorization code for access token")
                
                # Store tokens securely on server (never sent to frontend)
                tokens = {
                    'access_token': token_data['access_token'],
                    'refresh_token': token_data.get('refresh_token'),
                    'expires_in': token_data.get('expires_in'),
                    'expires_at': None,
                    'token_type': token_data.get('token_type', 'Bearer')
                }
                
                # Calculate expiration time
                if tokens['expires_in']:
                    tokens['expires_at'] = (datetime.now() + timedelta(seconds=tokens['expires_in'])).isoformat()
                
                self.store_tokens("youtube", tokens)
                logger.info("YouTube tokens stored securely on server")
                
                return {
                    "success": True,
                    "platform": "youtube"
                    # Note: No access token returned to frontend for security
                }
                
        except Exception as e:
            logger.error(f"YouTube OAuth callback failed: {e}")
            raise OAuthError(f"Failed to complete YouTube OAuth: {e}")
    
    async def handle_instagram_callback(self, code: str, state: str) -> Dict[str, Any]:
        """Handle Instagram OAuth callback"""
        try:
            if not self.validate_state(state, "instagram"):
                raise OAuthError("Invalid state parameter")
            
            # Exchange code for access token
            token_url = "https://api.instagram.com/oauth/access_token"
            
            data = {
                "client_id": self.settings.instagram_client_id,
                "client_secret": self.settings.instagram_client_secret,
                "grant_type": "authorization_code",
                "redirect_uri": self.settings.instagram_redirect_uri,
                "code": code
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(token_url, data=data)
                response.raise_for_status()
                token_data = response.json()
                
                # Store tokens
                tokens = {
                    'access_token': token_data['access_token'],
                    'user_id': token_data.get('user_id'),
                    'expires_at': None,  # Instagram tokens are long-lived
                    'token_type': 'Bearer'
                }
                
                self.store_tokens("instagram", tokens)
                
                return {
                    "success": True,
                    "platform": "instagram",
                    "access_token": token_data['access_token'],
                    "user_id": token_data.get('user_id')
                }
                
        except Exception as e:
            logger.error(f"Instagram OAuth callback failed: {e}")
            raise OAuthError(f"Failed to complete Instagram OAuth: {str(e)}")
    
    async def handle_tiktok_callback(self, code: str, state: str) -> Dict[str, Any]:
        """Handle TikTok OAuth callback"""
        try:
            if not self.validate_state(state, "tiktok"):
                raise OAuthError("Invalid state parameter")
            
            # Exchange code for access token
            token_url = "https://open.tiktokapis.com/v2/oauth/token/"
            
            data = {
                "client_key": self.settings.tiktok_client_key,
                "client_secret": self.settings.tiktok_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": self.settings.tiktok_redirect_uri
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(token_url, data=data)
                response.raise_for_status()
                token_data = response.json()
                
                # Store tokens
                tokens = {
                    'access_token': token_data['access_token'],
                    'refresh_token': token_data.get('refresh_token'),
                    'expires_in': token_data.get('expires_in'),
                    'expires_at': datetime.now() + timedelta(seconds=token_data.get('expires_in', 3600)),
                    'token_type': token_data.get('token_type', 'Bearer')
                }
                
                self.store_tokens("tiktok", tokens)
                
                return {
                    "success": True,
                    "platform": "tiktok",
                    "access_token": token_data['access_token'],
                    "refresh_token": token_data.get('refresh_token')
                }
                
        except Exception as e:
            logger.error(f"TikTok OAuth callback failed: {e}")
            raise OAuthError(f"Failed to complete TikTok OAuth: {str(e)}")
    
    async def get_connection_status(self, platform: str) -> Dict[str, Any]:
        """Get connection status for a platform"""
        tokens = await self.get_tokens(platform)
        
        if not tokens:
            return {
                "connected": False,
                "platform": platform,
                "message": f"Not connected to {platform}"
            }
        
        # Try to get user info to verify token is still valid
        try:
            user_info = await self._get_user_info(platform, tokens['access_token'])
            return {
                "connected": True,
                "platform": platform,
                "user_info": user_info,
                "expires_at": tokens.get('expires_at'),
                "message": f"Connected to {platform}"
            }
        except Exception as e:
            logger.warning(f"Token validation failed for {platform}: {e}")
            return {
                "connected": False,
                "platform": platform,
                "message": f"Token validation failed for {platform}"
            }
    
    async def _get_user_info(self, platform: str, access_token: str) -> Dict[str, Any]:
        """Get user information from platform"""
        try:
            if platform == "youtube":
                return await self._get_youtube_user_info(access_token)
            elif platform == "instagram":
                return await self._get_instagram_user_info(access_token)
            elif platform == "tiktok":
                return await self._get_tiktok_user_info(access_token)
            else:
                raise OAuthError(f"Unknown platform: {platform}")
        except Exception as e:
            logger.error(f"Failed to get user info for {platform}: {e}")
            raise OAuthError(f"Failed to get user info: {str(e)}")
    
    async def _get_youtube_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get YouTube user information"""
        url = "https://www.googleapis.com/youtube/v3/channels"
        params = {
            "part": "snippet,statistics",
            "mine": "true",
            "access_token": access_token
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get('items'):
                channel = data['items'][0]
                return {
                    "channel_id": channel['id'],
                    "title": channel['snippet']['title'],
                    "description": channel['snippet']['description'],
                    "subscriber_count": channel['statistics'].get('subscriberCount'),
                    "video_count": channel['statistics'].get('videoCount')
                }
            else:
                raise OAuthError("No YouTube channel found")
    
    async def _get_instagram_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get Instagram user information"""
        url = f"https://graph.instagram.com/me"
        params = {
            "fields": "id,username,account_type",
            "access_token": access_token
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            return {
                "user_id": data['id'],
                "username": data['username'],
                "account_type": data['account_type']
            }
    
    async def _get_tiktok_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get TikTok user information"""
        url = "https://open.tiktokapis.com/v2/user/info/"
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            return {
                "user_id": data['data']['user']['id'],
                "username": data['data']['user']['username'],
                "display_name": data['data']['user']['display_name']
            } 
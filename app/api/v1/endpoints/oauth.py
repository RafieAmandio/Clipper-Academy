"""
OAuth endpoints for social media integration

Handles OAuth 2.0 flows for YouTube, Instagram, and TikTok platforms.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
import logging
import time
from urllib.parse import urlencode
from datetime import datetime, timedelta

from app.core.dependencies import get_oauth_service, get_social_upload_service
from app.services.oauth_service import OAuthService
from app.services.social_upload_service import SocialUploadService
from app.models.requests import OAuthInitiateRequest, SocialMediaUploadRequest, ConnectionStatusRequest, StoreTokenRequest
from app.models.responses import (
    OAuthInitiateResponse, 
    SocialMediaUploadResponse, 
    ConnectionStatusResponse,
    AuthResponse
)
from app.core.exceptions import OAuthError, SocialMediaError

router = APIRouter(tags=["oauth"])
logger = logging.getLogger(__name__)


@router.post("/initiate", response_model=OAuthInitiateResponse)
async def initiate_oauth(
    request: OAuthInitiateRequest,
    oauth_service: OAuthService = Depends(get_oauth_service)
) -> OAuthInitiateResponse:
    """
    Initiate OAuth flow for a social media platform
    
    Generates an authorization URL for the specified platform and returns it
    along with a state parameter for security validation.
    """
    start_time = time.time()
    
    try:
        logger.info(f"Starting OAuth flow for {request.platform}")
        logger.info(f"Received redirect_uri: {request.redirect_uri}")
        
        if request.platform == "youtube":
            result = await oauth_service.initiate_youtube_oauth(request.redirect_uri)
        elif request.platform == "instagram":
            result = await oauth_service.initiate_instagram_oauth(request.redirect_uri)
        elif request.platform == "tiktok":
            result = await oauth_service.initiate_tiktok_oauth(request.redirect_uri)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported platform: {request.platform}"
            )
        
        processing_time = time.time() - start_time
        
        return OAuthInitiateResponse(
            success=True,
            message=f"OAuth URL generated successfully for {request.platform}",
            platform=request.platform,
            auth_url=result["auth_url"],
            state=result["state"]
        )
        
    except OAuthError as e:
        logger.error(f"OAuth initiation failed for {request.platform}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OAuth initiation failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error during OAuth initiation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )


@router.get("/instagram/callback")
async def instagram_callback(
    code: str,
    state: str,
    oauth_service: OAuthService = Depends(get_oauth_service)
):
    """
    Handle Instagram OAuth callback
    
    Processes the OAuth callback from Instagram and stores the access token.
    Redirects to the frontend with success/error status.
    """
    try:
        logger.info("Processing Instagram OAuth callback")
        
        result = await oauth_service.handle_instagram_callback(code, state)
        
        # Redirect to frontend with success status
        redirect_url = f"{oauth_service.settings.frontend_url}/oauth/callback/instagram?success=true&platform=instagram"
        return RedirectResponse(url=redirect_url)
        
    except OAuthError as e:
        logger.error(f"Instagram OAuth callback failed: {e}")
        redirect_url = f"{oauth_service.settings.frontend_url}/oauth/callback/instagram?success=false&error={str(e)}"
        return RedirectResponse(url=redirect_url)
    except Exception as e:
        logger.error(f"Unexpected error in Instagram callback: {e}")
        redirect_url = f"{oauth_service.settings.frontend_url}/oauth/callback/instagram?success=false&error=Unexpected error"
        return RedirectResponse(url=redirect_url)


@router.get("/tiktok/callback")
async def tiktok_callback(
    code: str,
    state: str,
    oauth_service: OAuthService = Depends(get_oauth_service)
):
    """
    Handle TikTok OAuth callback
    
    Processes the OAuth callback from TikTok and stores the access token.
    Redirects to the frontend with success/error status.
    """
    try:
        logger.info("Processing TikTok OAuth callback")
        
        result = await oauth_service.handle_tiktok_callback(code, state)
        
        # Redirect to frontend with success status
        redirect_url = f"{oauth_service.settings.frontend_url}/oauth/callback/tiktok?success=true&platform=tiktok"
        return RedirectResponse(url=redirect_url)
        
    except OAuthError as e:
        logger.error(f"TikTok OAuth callback failed: {e}")
        redirect_url = f"{oauth_service.settings.frontend_url}/oauth/callback/tiktok?success=false&error={str(e)}"
        return RedirectResponse(url=redirect_url)
    except Exception as e:
        logger.error(f"Unexpected error in TikTok callback: {e}")
        redirect_url = f"{oauth_service.settings.frontend_url}/oauth/callback/tiktok?success=false&error=Unexpected error"
        return RedirectResponse(url=redirect_url)


@router.get("/status/{platform}", response_model=ConnectionStatusResponse)
async def get_connection_status(
    platform: str,
    oauth_service: OAuthService = Depends(get_oauth_service)
) -> ConnectionStatusResponse:
    """
    Get connection status for a social media platform
    
    Returns whether the user is connected to the specified platform
    and includes user information if connected.
    """
    start_time = time.time()
    
    try:
        logger.info(f"Checking connection status for {platform}")
        
        status_info = await oauth_service.get_connection_status(platform)
        
        processing_time = time.time() - start_time
        
        return ConnectionStatusResponse(
            success=True,
            message=status_info["message"],
            platform=platform,
            connected=status_info["connected"],
            user_info=status_info.get("user_info"),
            expires_at=status_info.get("expires_at")
        )
        
    except OAuthError as e:
        logger.error(f"Failed to get connection status for {platform}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get connection status: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error getting connection status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )


@router.post("/upload", response_model=SocialMediaUploadResponse)
async def upload_to_social_media(
    request: SocialMediaUploadRequest,
    upload_service: SocialUploadService = Depends(get_social_upload_service)
) -> SocialMediaUploadResponse:
    """
    Upload a clip to social media
    
    Uploads the specified clip to the target social media platform
    using the stored OAuth tokens for authentication.
    """
    start_time = time.time()
    
    try:
        logger.info(f"Starting upload to {request.platform} for clip {request.clip_id}")
        
        if request.platform == "youtube":
            result = await upload_service.upload_to_youtube(
                clip_id=request.clip_id,
                title=request.title or f"Clip {request.clip_id}",
                description=request.description or "",
                tags=request.tags,
                privacy_status=request.privacy_status,
                category_id=request.category_id,
                made_for_kids=request.made_for_kids,
                upload_as_shorts=request.upload_as_shorts
            )
        elif request.platform == "instagram":
            result = await upload_service.upload_to_instagram(
                clip_id=request.clip_id,
                caption=request.caption or f"Check out this clip!",
                hashtags=request.hashtags
            )
        elif request.platform == "tiktok":
            result = await upload_service.upload_to_tiktok(
                clip_id=request.clip_id,
                title=request.title or f"Clip {request.clip_id}",
                visibility=request.visibility
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported platform: {request.platform}"
            )
        
        processing_time = time.time() - start_time
        
        return SocialMediaUploadResponse(
            success=True,
            message=f"Successfully uploaded to {request.platform}",
            platform=request.platform,
            clip_id=request.clip_id,
            upload_result=result,
            processing_time=processing_time
        )
        
    except (OAuthError, SocialMediaError) as e:
        logger.error(f"Upload failed for {request.platform}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error during upload: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )


@router.get("/upload/status/{platform}/{upload_id}")
async def get_upload_status(
    platform: str,
    upload_id: str,
    upload_service: SocialUploadService = Depends(get_social_upload_service)
):
    """
    Get the status of an upload
    
    Returns the current status of an ongoing upload to a social media platform.
    """
    try:
        logger.info(f"Checking upload status for {platform} upload {upload_id}")
        
        status_info = await upload_service.get_upload_status(platform, upload_id)
        
        return {
            "success": True,
            "platform": platform,
            "upload_id": upload_id,
            "status": status_info["status"],
            "message": status_info["message"]
        }
        
    except SocialMediaError as e:
        logger.error(f"Failed to get upload status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get upload status: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error getting upload status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )


@router.get("/youtube/callback")
async def youtube_callback(
    code: str,
    state: str,
    oauth_service: OAuthService = Depends(get_oauth_service)
):
    """
    Handle YouTube OAuth callback using authorization code flow
    
    Receives the authorization code from Google, exchanges it for access token
    server-side, and redirects to frontend with success/error status.
    """
    try:
        logger.info("Processing YouTube OAuth callback")
        logger.info(f"Received code: {code}")
        logger.info(f"Received state: {state}")
        
        # Exchange authorization code for access token (server-side only)
        result = await oauth_service.handle_youtube_callback(code, state)
        
        # Redirect to frontend with success status
        redirect_url = f"{oauth_service.settings.frontend_url}/oauth/callback/youtube?success=true&platform=youtube"
        return RedirectResponse(url=redirect_url)
        
    except OAuthError as e:
        logger.error(f"YouTube OAuth callback failed: {e}")
        redirect_url = f"{oauth_service.settings.frontend_url}/oauth/callback/youtube?success=false&error={str(e)}"
        return RedirectResponse(url=redirect_url)
    except Exception as e:
        logger.error(f"Unexpected error in YouTube callback: {e}")
        redirect_url = f"{oauth_service.settings.frontend_url}/oauth/callback/youtube?success=false&error=Unexpected error"
        return RedirectResponse(url=redirect_url) 
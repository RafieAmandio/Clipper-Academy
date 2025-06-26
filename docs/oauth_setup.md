# OAuth Setup Guide

## Environment Variables Required

Create a `.env` file in the backend directory with the following variables:

```bash
# OAuth Configuration
# YouTube OAuth
YOUTUBE_CLIENT_ID=your_youtube_client_id_here
YOUTUBE_CLIENT_SECRET=your_youtube_client_secret_here
YOUTUBE_REDIRECT_URI=http://localhost:8000/api/v1/oauth/youtube/callback

# Instagram OAuth
INSTAGRAM_CLIENT_ID=your_instagram_client_id_here
INSTAGRAM_CLIENT_SECRET=your_instagram_client_secret_here
INSTAGRAM_REDIRECT_URI=http://localhost:8000/api/v1/oauth/instagram/callback

# TikTok OAuth
TIKTOK_CLIENT_KEY=your_tiktok_client_key_here
TIKTOK_CLIENT_SECRET=your_tiktok_client_secret_here
TIKTOK_REDIRECT_URI=http://localhost:8000/api/v1/oauth/tiktok/callback

# Frontend URL
FRONTEND_URL=http://localhost:3000

# Other required settings
OPENAI_API_KEY=your_openai_api_key_here
```

## Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the YouTube Data API v3
4. Go to "Credentials" → "Create Credentials" → "OAuth 2.0 Client IDs"
5. Choose "Web application"
6. Add authorized redirect URIs:
   - `http://localhost:8000/api/v1/oauth/youtube/callback`
   - `http://localhost:3000/oauth/callback/youtube` (for frontend)
7. Copy the Client ID and Client Secret to your `.env` file

## Testing OAuth Configuration

Run the test script to verify your configuration:

```bash
cd backend
python test_oauth.py
```

## Common Issues

### "Missing required parameter: redirect_uri"

This error occurs when:

1. The redirect URI is not properly configured in Google Cloud Console
2. The redirect URI in your `.env` file doesn't match what's configured in Google Cloud Console
3. The frontend is not providing the correct redirect URI

### Solution Steps:

1. **Verify Google Cloud Console Configuration:**

   - Make sure `http://localhost:8000/api/v1/oauth/youtube/callback` is added to authorized redirect URIs
   - Make sure `http://localhost:3000/oauth/callback/youtube` is also added for frontend redirects

2. **Check Environment Variables:**

   - Ensure `YOUTUBE_CLIENT_ID` and `YOUTUBE_CLIENT_SECRET` are set
   - Ensure `YOUTUBE_REDIRECT_URI` is set to `http://localhost:8000/api/v1/oauth/youtube/callback`

3. **Verify Frontend Configuration:**

   - The frontend should call the backend with the correct redirect URI
   - The backend will use this redirect URI for the OAuth flow

4. **Test the Configuration:**
   - Run `python test_oauth.py` to verify settings
   - Check backend logs for OAuth URL generation

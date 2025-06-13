from fastapi import Request
import os

def file_path_to_url(file_path: str, request: Request, mount_path: str = "/data") -> str:
    """
    Convert a local file path (e.g., data/results/video.mp4) to a full URL using the request's base URL.
    Assumes files are served from a static mount (e.g., /data).
    """
    # Remove leading 'data/' if present
    rel_path = file_path
    if rel_path.startswith("data/"):
        rel_path = rel_path[4:]
    # Ensure leading slash
    if not rel_path.startswith("/"):
        rel_path = "/" + rel_path
    url_path = f"{mount_path}{rel_path}"
    # Remove trailing slash from base_url if present
    base_url = str(request.base_url).rstrip("/")
    return base_url + url_path 
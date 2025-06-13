import os
import time
import mimetypes
from typing import Optional, Dict
from io import BytesIO
import httpx
import aiofiles
import asyncio
from fastapi import UploadFile

from app.services.base import BaseService
from app.config.settings import Settings
from app.core.exceptions import ZapCapError, StorageError


class ZapCapService(BaseService):
    """Service for handling ZapCap video captioning operations"""
    
    def __init__(self, settings: Settings):
        """Initialize ZapCap service
        
        Args:
            settings: Application settings
        """
        super().__init__(settings)
        self.api_base = settings.zapcap_api_base
        self.api_key = settings.zapcap_api_key
        self.default_template_id = settings.zapcap_template_id
        
        if not self.api_key:
            self.logger.warning("ZapCap API key not provided. ZapCap features will not work.")
    
    def _ensure_api_key(self) -> None:
        """Ensure ZapCap API key is available"""
        if not self.api_key:
            raise ZapCapError("ZapCap API key not configured")
    
    async def save_upload_file(self, upload_file: UploadFile) -> str:
        """Save uploaded file to uploads directory
        
        Args:
            upload_file: FastAPI UploadFile object
            
        Returns:
            Path to saved file
            
        Raises:
            StorageError: If file save fails
        """
        try:
            file_extension = os.path.splitext(upload_file.filename or "video.mp4")[1]
            temp_file_path = os.path.join(self.settings.upload_dir, f"upload_{int(time.time())}{file_extension}")
            
            async with aiofiles.open(temp_file_path, 'wb') as temp_file:
                content = await upload_file.read()
                await temp_file.write(content)
            
            self.logger.info(f"File saved to: {temp_file_path}, size: {self.format_file_size(len(content))}")
            return temp_file_path
            
        except Exception as e:
            self.logger.error(f"Error saving upload file: {e}")
            raise StorageError(f"Failed to save uploaded file: {e}")
    
    async def upload_video(self, video_path: str) -> str:
        """Upload video to ZapCap with smart size detection (async)"""
        self._ensure_api_key()
        
        if not os.path.exists(video_path):
            raise ZapCapError(f"Video file not found: {video_path}")
        
        file_size = os.path.getsize(video_path)
        filename = os.path.basename(video_path)
        ten_mb = 10 * 1024 * 1024
        
        self.logger.info(f"Uploading video: {filename}, size: {self.format_file_size(file_size)}")
        
        if file_size <= ten_mb:
            self.logger.info("Using standard upload (file <= 10MB)")
            return await self._simple_upload(video_path)
        else:
            self.logger.info("Using multipart upload (file > 10MB)")
            return await self._multipart_upload(video_path)
    
    async def _simple_upload(self, video_path: str) -> str:
        """Handle simple upload for files <= 10MB (async)"""
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                with open(video_path, 'rb') as video_file:
                    upload_url = f"{self.api_base}/videos"
                    headers = {"x-api-key": self.api_key}
                    files = {'file': (os.path.basename(video_path), video_file, 'video/mp4')}
                    self.logger.info("Uploading video using simple upload...")
                    response = await client.post(upload_url, headers=headers, files=files)
                    response.raise_for_status()
                    upload_data = response.json()
                    if "id" in upload_data:
                        video_id = upload_data["id"]
                        self.logger.info(f"Upload completed! Video ID: {video_id}")
                        return video_id
                    else:
                        raise ZapCapError(f"Invalid upload response: {upload_data}")
        except httpx.RequestError as e:
            self.logger.error(f"Upload failed: {e}")
            raise ZapCapError(f"Upload failed: {e}")
        except Exception as e:
            self.logger.error(f"Upload error: {e}")
            raise ZapCapError(f"Upload error: {e}")
    
    async def _multipart_upload(self, video_path: str) -> str:
        """Handle multipart upload for files > 10MB (async)"""
        try:
            file_size = os.path.getsize(video_path)
            filename = os.path.basename(video_path)
            chunk_size = 10 * 1024 * 1024  # 10MB chunks
            num_parts = (file_size + chunk_size - 1) // chunk_size
            self.logger.info(f"Preparing {num_parts} parts for upload...")
            create_upload_url = f"{self.api_base}/videos/upload"
            headers = {"x-api-key": self.api_key, "Content-Type": "application/json"}
            upload_parts = []
            for i in range(num_parts):
                part_size = min(chunk_size, file_size - (i * chunk_size))
                upload_parts.append({"contentLength": part_size})
            create_payload = {
                "uploadParts": upload_parts,
                "filename": filename,
                "contentType": mimetypes.guess_type(filename)[0] or 'application/octet-stream'
            }
            async with httpx.AsyncClient(timeout=60) as client:
                self.logger.info("Creating upload session...")
                create_resp = await client.post(create_upload_url, headers=headers, json=create_payload)
                create_resp.raise_for_status()
                create_data = create_resp.json()
            upload_id = create_data["uploadId"]
            video_id = create_data["videoId"]
            presigned_urls = None
            for possible_key in ["presignedUrls", "presigned_urls", "urls", "uploadUrls", "upload_urls", "parts"]:
                if possible_key in create_data:
                    presigned_urls = create_data[possible_key]
                    break
            if not presigned_urls:
                raise ZapCapError(f"No presigned URLs found. Available keys: {list(create_data.keys())}")
            self.logger.info(f"Upload session created (ID: {upload_id}, Video ID: {video_id})")
            uploaded_parts = []
            async with httpx.AsyncClient(timeout=300) as client:
                with open(video_path, 'rb') as video_file:
                    for part_number, presigned_url_data in enumerate(presigned_urls, 1):
                        chunk_data = video_file.read(chunk_size)
                        if not chunk_data:
                            break
                        self.logger.info(f"Uploading part [{part_number}/{num_parts}] ({self.format_file_size(len(chunk_data))})")
                        if isinstance(presigned_url_data, str):
                            presigned_url = presigned_url_data
                        elif isinstance(presigned_url_data, dict):
                            presigned_url = (presigned_url_data.get("url") or 
                                           presigned_url_data.get("uploadUrl") or 
                                           presigned_url_data.get("presignedUrl"))
                            if not presigned_url:
                                raise ZapCapError(f"No URL found in: {presigned_url_data}")
                        else:
                            raise ZapCapError(f"Unexpected URL format: {type(presigned_url_data)}")
                        upload_resp = await client.put(
                            presigned_url, 
                            content=chunk_data, 
                            headers={'Content-Type': create_payload['contentType']}
                        )
                        upload_resp.raise_for_status()
                        etag = upload_resp.headers.get('ETag', '').strip('"')
                        uploaded_parts.append({
                            "partNumber": part_number,
                            "etag": etag or ""
                        })
            self.logger.info("All parts uploaded successfully!")
            complete_url = f"{self.api_base}/videos/upload/complete"
            file_extension = os.path.splitext(filename)[1]
            base_name = os.path.splitext(filename)[0]
            complete_payload = {
                "uploadId": upload_id,
                "videoId": video_id,
                "filename": filename,
                "originalFilename": filename,
                "fileExtension": file_extension,
                "baseName": base_name,
                "contentType": create_payload['contentType'],
                "parts": uploaded_parts,
                "metadata": {
                    "originalSize": file_size,
                    "uploadMethod": "multipart"
                }
            }
            async with httpx.AsyncClient(timeout=60) as client:
                self.logger.info("Finalizing upload...")
                complete_resp = await client.post(complete_url, headers=headers, json=complete_payload)
                if complete_resp.status_code in [200, 201]:
                    self.logger.info("Upload completed successfully!")
                    return video_id
                else:
                    self.logger.warning(f"Completion returned status {complete_resp.status_code}")
                    check_url = f"{self.api_base}/videos/{video_id}"
                    check_resp = await client.get(check_url, headers={"x-api-key": self.api_key})
                    if check_resp.status_code == 200:
                        self.logger.info("Video is available despite completion warning")
                        return video_id
                    else:
                        complete_resp.raise_for_status()
        except httpx.RequestError as e:
            self.logger.error(f"Multipart upload failed: {e}")
            raise ZapCapError(f"Multipart upload failed: {e}")
        except Exception as e:
            self.logger.error(f"Multipart upload error: {e}")
            raise ZapCapError(f"Multipart upload error: {e}")
    
    async def create_caption_task(self, video_id: str, template_id: Optional[str] = None, 
                          language: str = "en", auto_approve: bool = True) -> str:
        """Create a captioning task for the uploaded video (async)"""
        self._ensure_api_key()
        self.logger.info(f"Creating captioning task for video ID: {video_id}")
        task_url = f"{self.api_base}/videos/{video_id}/task"
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "autoApprove": auto_approve,
            "language": language,
            "templateId": template_id or self.default_template_id
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(task_url, headers=headers, json=payload)
                response.raise_for_status()
                task_data = response.json()
                if "taskId" in task_data:
                    task_id = task_data["taskId"]
                    self.logger.info(f"Captioning task created! Task ID: {task_id}")
                    return task_id
                else:
                    raise ZapCapError(f"Invalid task creation response: {task_data}")
        except httpx.RequestError as e:
            self.logger.error(f"Failed to create captioning task: {e}")
            raise ZapCapError(f"Failed to create captioning task: {e}")
        except Exception as e:
            self.logger.error(f"Task creation error: {e}")
            raise ZapCapError(f"Task creation error: {e}")
    
    async def check_caption_status(self, video_id: str, task_id: str) -> Dict:
        """Check the status of the captioning task (async)"""
        self._ensure_api_key()
        status_url = f"{self.api_base}/videos/{video_id}/task/{task_id}"
        headers = {"x-api-key": self.api_key}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(status_url, headers=headers)
                response.raise_for_status()
                status_data = response.json()
                status = status_data.get('status', 'unknown')
                self.logger.debug(f"Task {task_id} status: {status}")
                return status_data
        except httpx.RequestError as e:
            self.logger.error(f"Failed to check caption status: {e}")
            raise ZapCapError(f"Failed to check caption status: {e}")
        except Exception as e:
            self.logger.error(f"Status check error: {e}")
            raise ZapCapError(f"Status check error: {e}")
    
    async def wait_for_completion(self, video_id: str, task_id: str, 
                          max_wait_time: int = 600, check_interval: int = 5) -> Dict:
        """Wait for captioning task to complete (async)"""
        start_time = time.time()
        self.logger.info(f"Waiting for captioning completion (max {max_wait_time}s)...")
        while True:
            status_data = await self.check_caption_status(video_id, task_id)
            status = status_data.get("status", "unknown")
            if status == "completed":
                elapsed = int(time.time() - start_time)
                self.logger.info(f"Captioning completed in {elapsed} seconds!")
                return status_data
            elif status == "failed":
                error_message = status_data.get("error", "Unknown error")
                self.logger.error(f"Captioning failed: {error_message}")
                raise ZapCapError(f"Captioning failed: {error_message}")
            elif status in ["processing", "pending", "transcribing"]:
                elapsed = time.time() - start_time
                if elapsed > max_wait_time:
                    self.logger.error(f"Captioning timed out after {max_wait_time} seconds")
                    raise ZapCapError("Captioning process timed out")
                self.logger.info(f"Status: {status}, elapsed: {int(elapsed)}s")
                await asyncio.sleep(check_interval)
            else:
                self.logger.warning(f"Unknown status: {status}")
                await asyncio.sleep(check_interval)
    
    async def download_result_video(self, download_url: str, video_id: str, original_filename: str = None) -> str:
        """Download the processed video and save it to results directory (async)"""
        try:
            timestamp = int(time.time())
            if original_filename:
                name, ext = os.path.splitext(original_filename)
                result_filename = f"{name}_captioned_{timestamp}{ext}"
            else:
                result_filename = f"result_{video_id}_{timestamp}.mp4"
            result_path = os.path.join(self.settings.results_dir, result_filename)
            self.logger.info(f"Downloading result video from: {download_url}")
            headers = {"x-api-key": self.api_key}
            async with httpx.AsyncClient(timeout=300) as client:
                async with client.stream("GET", download_url, headers=headers) as response:
                    response.raise_for_status()
                    async with aiofiles.open(result_path, 'wb') as result_file:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            await result_file.write(chunk)
            self.logger.info(f"Result video saved to: {result_path}, size: {os.path.getsize(result_path)} bytes")
            return result_path
        except Exception as e:
            self.logger.error(f"Error downloading result video: {e}")
            raise ZapCapError(f"Failed to download result video: {e}")
    
    async def process_video(self, upload_file: UploadFile, template_id: Optional[str] = None,
                          language: str = "en", auto_approve: bool = True) -> Dict:
        """Complete video processing pipeline (async)"""
        start_time = time.time()
        temp_file_path = None
        try:
            # Step 1: Save uploaded file
            temp_file_path = await self.save_upload_file(upload_file)
            # Step 2: Upload to ZapCap
            video_id = await self.upload_video(temp_file_path)
            # Step 3: Create captioning task
            task_id = await self.create_caption_task(
                video_id, 
                template_id=template_id, 
                language=language, 
                auto_approve=auto_approve
            )
            # Step 4: Wait for completion
            status_data = await self.wait_for_completion(video_id, task_id)
            # Step 5: Extract download URL
            download_url = status_data.get("downloadUrl")
            if not download_url:
                raise ZapCapError("Download URL not found in response")
            # Step 6: Download result
            result_path = await self.download_result_video(download_url, video_id, upload_file.filename)
            processing_time = time.time() - start_time
            video_name = os.path.basename(result_path)
            return {
                "success": True,
                "message": "Video captioning completed successfully",
                "video_id": video_id,
                "task_id": task_id,
                "video_name": video_name,
                "result_file_path": result_path,
                "processing_time": processing_time
            }
        except Exception as e:
            self.logger.error(f"Error processing video: {e}")
            raise
        finally:
            # Clean up uploaded file
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                    self.logger.info("Upload file cleaned up")
                except OSError as e:
                    self.logger.warning(f"Could not clean up upload file: {e}") 
import os
import time
import tempfile
import mimetypes
from typing import Optional, Tuple
import requests
import aiofiles
from fastapi import HTTPException, UploadFile
import logging

logger = logging.getLogger(__name__)

class ZapCapService:
    """Service for handling ZapCap video captioning operations"""
    
    def __init__(self):
        # ZapCap API configuration
        self.api_base = "https://api.zapcap.ai"
        self.api_key = os.getenv("ZAPCAP_API_KEY", "f6f749fed7f75634510ab78da636519846c80b82bcc68837839c0c853a550472")
        self.default_template_id = os.getenv("ZAPCAP_TEMPLATE_ID", "d2018215-2125-41c1-940e-f13b411fff5c")
        
        if not self.api_key:
            logger.warning("ZAPCAP_API_KEY not found in environment variables")
    
    def format_file_size(self, size_bytes: int) -> str:
        """Convert bytes to human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    async def save_upload_file(self, upload_file: UploadFile) -> str:
        """Save uploaded file to uploads directory"""
        try:
            # Create uploads directory if it doesn't exist
            uploads_dir = "uploads"
            os.makedirs(uploads_dir, exist_ok=True)
            
            # Create temporary file with original extension
            file_extension = os.path.splitext(upload_file.filename or "video.mp4")[1]
            temp_file_path = os.path.join(uploads_dir, f"upload_{int(time.time())}{file_extension}")
            
            # Save file asynchronously
            async with aiofiles.open(temp_file_path, 'wb') as temp_file:
                content = await upload_file.read()
                await temp_file.write(content)
            
            logger.info(f"File saved to: {temp_file_path}, size: {self.format_file_size(len(content))}")
            return temp_file_path
            
        except Exception as e:
            logger.error(f"Error saving upload file: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {e}")
    
    def upload_video(self, video_path: str) -> str:
        """Upload video to ZapCap with smart size detection"""
        if not os.path.exists(video_path):
            raise HTTPException(status_code=404, detail=f"Video file not found: {video_path}")
        
        file_size = os.path.getsize(video_path)
        filename = os.path.basename(video_path)
        ten_mb = 10 * 1024 * 1024
        
        logger.info(f"Uploading video: {filename}, size: {self.format_file_size(file_size)}")
        if file_size <= ten_mb:
            # Simple upload for smaller files
            logger.info("Using standard upload (file <= 10MB)")
            return self._simple_upload(video_path)
        else:
            # Multipart upload for larger files
            logger.info("Using multipart upload (file > 10MB)")
            return self._multipart_upload(video_path)
    
    def _simple_upload(self, video_path: str) -> str:
        """Handle simple upload for files <= 10MB"""
        try:
            with open(video_path, 'rb') as video_file:
                upload_url = f"{self.api_base}/videos"
                headers = {"x-api-key": self.api_key}
                files = {'file': video_file}
                
                logger.info("Uploading video using simple upload...")
                response = requests.post(upload_url, headers=headers, files=files, timeout=300)
                response.raise_for_status()
                
                upload_data = response.json()
                if "id" in upload_data:
                    video_id = upload_data["id"]
                    logger.info(f"Upload completed! Video ID: {video_id}")
                    return video_id
                else:
                    raise ValueError(f"Invalid upload response: {upload_data}")
                    
        except requests.exceptions.RequestException as e:
            logger.error(f"Upload failed: {e}")
            raise HTTPException(status_code=500, detail=f"Upload failed: {e}")
        except Exception as e:
            logger.error(f"Upload error: {e}")
            raise HTTPException(status_code=500, detail=f"Upload error: {e}")
    
    def _multipart_upload(self, video_path: str) -> str:
        """Handle multipart upload for files > 10MB"""
        try:
            file_size = os.path.getsize(video_path)
            filename = os.path.basename(video_path)
            chunk_size = 10 * 1024 * 1024  # 10MB chunks
            num_parts = (file_size + chunk_size - 1) // chunk_size
            
            logger.info(f"Preparing {num_parts} parts for upload...")
            
            # 1. Create upload session
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
            
            logger.info("Creating upload session...")
            create_resp = requests.post(create_upload_url, headers=headers, json=create_payload, timeout=60)
            create_resp.raise_for_status()
            create_data = create_resp.json()
            
            upload_id = create_data["uploadId"]
            video_id = create_data["videoId"]
            
            # Find presigned URLs in response
            presigned_urls = None
            for possible_key in ["presignedUrls", "presigned_urls", "urls", "uploadUrls", "upload_urls", "parts"]:
                if possible_key in create_data:
                    presigned_urls = create_data[possible_key]
                    break
            
            if not presigned_urls:
                raise ValueError(f"No presigned URLs found. Available keys: {list(create_data.keys())}")
            
            logger.info(f"Upload session created (ID: {upload_id}, Video ID: {video_id})")
            
            # 2. Upload each part
            uploaded_parts = []
            with open(video_path, 'rb') as video_file:
                for part_number, presigned_url_data in enumerate(presigned_urls, 1):
                    chunk_data = video_file.read(chunk_size)
                    if not chunk_data:
                        break
                    
                    logger.info(f"Uploading part [{part_number}/{num_parts}] ({self.format_file_size(len(chunk_data))})")
                    
                    # Extract presigned URL
                    if isinstance(presigned_url_data, str):
                        presigned_url = presigned_url_data
                    elif isinstance(presigned_url_data, dict):
                        presigned_url = (presigned_url_data.get("url") or 
                                       presigned_url_data.get("uploadUrl") or 
                                       presigned_url_data.get("presignedUrl"))
                        if not presigned_url:
                            raise ValueError(f"No URL found in: {presigned_url_data}")
                    else:
                        raise ValueError(f"Unexpected URL format: {type(presigned_url_data)}")
                    
                    # Upload part
                    upload_resp = requests.put(
                        presigned_url, 
                        data=chunk_data, 
                        headers={'Content-Type': create_payload['contentType']},
                        timeout=300
                    )
                    upload_resp.raise_for_status()
                    
                    # Collect ETag for completion
                    etag = upload_resp.headers.get('ETag', '').strip('"')
                    uploaded_parts.append({
                        "partNumber": part_number,
                        "etag": etag or ""
                    })
            
            logger.info("All parts uploaded successfully!")
            
            # 3. Complete multipart upload
            logger.info("Finalizing upload...")
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
            
            complete_resp = requests.post(complete_url, headers=headers, json=complete_payload, timeout=60)
            
            if complete_resp.status_code in [200, 201]:
                logger.info("Upload completed successfully!")
                return video_id
            else:
                logger.warning(f"Completion returned status {complete_resp.status_code}")
                logger.info("Checking if video is still available...")
                
                # Check if video exists despite completion issues
                check_url = f"{self.api_base}/videos/{video_id}"
                check_resp = requests.get(check_url, headers={"x-api-key": self.api_key}, timeout=30)
                if check_resp.status_code == 200:
                    check_data = check_resp.json()
                    status = check_data.get('status', 'unknown')
                    logger.info(f"Video is available (status: {status})")
                    return video_id
                else:
                    complete_resp.raise_for_status()
                    
        except requests.exceptions.RequestException as e:
            logger.error(f"Multipart upload failed: {e}")
            raise HTTPException(status_code=500, detail=f"Multipart upload failed: {e}")
        except Exception as e:
            logger.error(f"Multipart upload error: {e}")
            raise HTTPException(status_code=500, detail=f"Multipart upload error: {e}")
    
    def create_caption_task(self, video_id: str, template_id: Optional[str] = None, 
                          language: str = "en", auto_approve: bool = True) -> str:
        """Create a captioning task for the uploaded video"""
        logger.info(f"Creating captioning task for video ID: {video_id}")
        
        task_url = f"{self.api_base}/videos/{video_id}/task"
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        
        payload = {
            "autoApprove": auto_approve,
            "language": language
        }
        
        if template_id:
            payload["templateId"] = template_id
        else:
            payload["templateId"] = self.default_template_id
        
        try:
            response = requests.post(task_url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            
            task_data = response.json()
            if "taskId" in task_data:
                task_id = task_data["taskId"]
                logger.info(f"Captioning task created! Task ID: {task_id}")
                return task_id
            else:
                raise ValueError(f"Invalid task creation response: {task_data}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create captioning task: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create captioning task: {e}")
        except Exception as e:
            logger.error(f"Task creation error: {e}")
            raise HTTPException(status_code=500, detail=f"Task creation error: {e}")
    
    def check_caption_status(self, video_id: str, task_id: str) -> dict:
        """Check the status of the captioning task"""
        status_url = f"{self.api_base}/videos/{video_id}/task/{task_id}"
        headers = {"x-api-key": self.api_key}
        
        try:
            response = requests.get(status_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            status_data = response.json()
            status = status_data.get('status', 'unknown')
            
            logger.info(f"Task {task_id} status: {status}")
            return status_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to check caption status: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to check caption status: {e}")
        except Exception as e:
            logger.error(f"Status check error: {e}")
            raise HTTPException(status_code=500, detail=f"Status check error: {e}")
    
    def wait_for_completion(self, video_id: str, task_id: str, 
                          max_wait_time: int = 600, check_interval: int = 5) -> dict:
        """Wait for captioning task to complete"""
        start_time = time.time()
        
        logger.info(f"Waiting for captioning completion (max {max_wait_time}s)...")
        
        while True:
            status_data = self.check_caption_status(video_id, task_id)
            status = status_data.get("status", "unknown")
            
            if status == "completed":
                elapsed = int(time.time() - start_time)
                logger.info(f"Captioning completed in {elapsed} seconds!")
                return status_data
                
            elif status == "failed":
                error_message = status_data.get("error", "Unknown error")
                logger.error(f"Captioning failed: {error_message}")
                raise HTTPException(status_code=500, detail=f"Captioning failed: {error_message}")
                
            elif status in ["processing", "pending", "transcribing"]:
                elapsed = time.time() - start_time
                if elapsed > max_wait_time:
                    logger.error(f"Captioning timed out after {max_wait_time} seconds")
                    raise HTTPException(status_code=408, detail="Captioning process timed out")
                
                logger.info(f"Status: {status}, elapsed: {int(elapsed)}s")
                time.sleep(check_interval)
                
            else:
                logger.warning(f"Unknown status: {status}")
                time.sleep(check_interval)
    
    async def process_video(self, upload_file: UploadFile, template_id: Optional[str] = None,
                          language: str = "en", auto_approve: bool = True) -> dict:
        """Complete video processing pipeline"""
        start_time = time.time()
        temp_file_path = None
        
        try:
            # Step 1: Save uploaded file to uploads directory
            temp_file_path = await self.save_upload_file(upload_file)
            
            # Step 2: Upload to ZapCap
            video_id = self.upload_video(temp_file_path)
            
            # Step 3: Create captioning task
            task_id = self.create_caption_task(
                video_id, 
                template_id=template_id, 
                language=language, 
                auto_approve=auto_approve
            )
            
            # Step 4: Wait for completion
            status_data = self.wait_for_completion(video_id, task_id)
            
            # Step 5: Extract download URL
            download_url = status_data.get("downloadUrl")
            if not download_url:
                raise HTTPException(status_code=500, detail="Download URL not found in response")
            
            # Step 6: Download and save result video to results directory
            original_filename = upload_file.filename
            result_path = await self.download_result_video(download_url, video_id, original_filename)
            
            # Extract just the filename from the result path
            video_name = os.path.basename(result_path)
            
            processing_time = time.time() - start_time
            
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
            logger.error(f"Error processing video: {e}")
            raise
        finally:
            # Clean up uploaded file from uploads directory
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                    logger.info("Upload file cleaned up from uploads directory")
                except OSError as e:
                    logger.warning(f"Could not clean up upload file: {e}")
    
    async def download_result_video(self, download_url: str, video_id: str, original_filename: str = None) -> str:
        """Download the processed video and save it to results directory"""
        try:
            # Create results directory if it doesn't exist
            results_dir = "results"
            os.makedirs(results_dir, exist_ok=True)
            
            # Generate filename for result
            timestamp = int(time.time())
            if original_filename:
                name, ext = os.path.splitext(original_filename)
                result_filename = f"{name}_captioned_{timestamp}{ext}"
            else:
                result_filename = f"result_{video_id}_{timestamp}.mp4"
            
            result_path = os.path.join(results_dir, result_filename)
            
            # Download the video
            logger.info(f"Downloading result video from: {download_url}")
            headers = {"x-api-key": self.api_key}
            
            response = requests.get(download_url, headers=headers, stream=True, timeout=300)
            response.raise_for_status()
            
            # Save the downloaded video
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0
            
            async with aiofiles.open(result_path, 'wb') as result_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        await result_file.write(chunk)
                        downloaded_size += len(chunk)
                        
                        # Log progress for large files
                        if total_size > 0 and downloaded_size % (1024 * 1024 * 10) == 0:  # Every 10MB
                            progress = (downloaded_size / total_size) * 100
                            logger.info(f"Download progress: {progress:.1f}% ({self.format_file_size(downloaded_size)}/{self.format_file_size(total_size)})")
            
            logger.info(f"Result video saved to: {result_path}, size: {self.format_file_size(downloaded_size)}")
            return result_path
            
        except Exception as e:
            logger.error(f"Error downloading result video: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to download result video: {e}")


# Create service instance
zapcap_service = ZapCapService()

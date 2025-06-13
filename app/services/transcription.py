import os
import subprocess
import json
import asyncio
import concurrent.futures
from datetime import datetime
from typing import Dict, List, Optional
from io import BytesIO

from openai import OpenAI

from app.services.base import BaseService
from app.config.settings import Settings
from app.core.exceptions import TranscriptionError, ConfigurationError


class TranscriptionService(BaseService):
    """Service for handling audio transcription with OpenAI Whisper"""
    
    def __init__(self, settings: Settings, openai_client: OpenAI):
        """Initialize transcription service
        
        Args:
            settings: Application settings
            openai_client: OpenAI client
        """
        super().__init__(settings)
        self.client = openai_client
    
    def _ensure_client(self) -> None:
        """Ensure OpenAI client is available"""
        if self.client is None:
            raise TranscriptionError("OpenAI client not initialized. Check API key configuration.")
    
    def extract_audio_from_video(self, video_path: str) -> str:
        """Extract audio from video for transcription
        
        Args:
            video_path: Path to video file
            
        Returns:
            Path to extracted audio file
            
        Raises:
            TranscriptionError: If audio extraction fails
        """
        try:
            audio_filename = f"audio_{int(datetime.now().timestamp())}.wav"
            audio_path = os.path.join(self.settings.temp_dir, audio_filename)
            
            # Extract audio with ffmpeg
            cmd = [
                'ffmpeg', '-y', '-i', video_path, '-vn',
                '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
                audio_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.logger.info(f"Audio extracted to: {audio_path}")
            return audio_path
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"FFmpeg error: {e.stderr}")
            raise TranscriptionError(f"Failed to extract audio: {e.stderr}")
        except Exception as e:
            self.logger.error(f"Error extracting audio: {e}")
            raise TranscriptionError(f"Failed to extract audio: {e}")
    
    def get_audio_duration(self, audio_path: str) -> float:
        """Get duration of audio file
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Duration in seconds
        """
        try:
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', audio_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            info = json.loads(result.stdout)
            
            duration = float(info['format']['duration'])
            return duration
            
        except Exception as e:
            self.logger.error(f"Error getting audio duration: {e}")
            return 0.0
    
    def split_audio_for_transcription(self, audio_path: str) -> List[Dict[str, float]]:
        """Split large audio files into smaller chunks for transcription
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            List of chunk information with paths and offsets
        """
        try:
            file_size = os.path.getsize(audio_path)
            max_size_bytes = self.settings.max_transcription_chunk_size
            
            if file_size <= max_size_bytes:
                return [{
                    'path': audio_path,
                    'start_offset': 0.0,
                    'duration': self.get_audio_duration(audio_path)
                }]
            
            # Calculate number of chunks needed
            import math
            num_chunks = math.ceil(file_size / max_size_bytes)
            self.logger.info(f"Audio file ({self.format_file_size(file_size)}) exceeds limit, splitting into {num_chunks} chunks")
            
            # Get total duration to calculate chunk duration
            total_duration = self.get_audio_duration(audio_path)
            chunk_duration = total_duration / num_chunks
            
            chunk_info = []
            for i in range(num_chunks):
                start_time = i * chunk_duration
                end_time = min((i + 1) * chunk_duration, total_duration)
                
                chunk_filename = f"audio_chunk_{i}_{int(datetime.now().timestamp())}.wav"
                chunk_path = os.path.join(self.settings.temp_dir, chunk_filename)
                
                # Extract audio chunk
                cmd = [
                    'ffmpeg', '-y', '-i', audio_path,
                    '-ss', str(start_time), '-to', str(end_time),
                    '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
                    chunk_path
                ]
                
                subprocess.run(cmd, capture_output=True, text=True, check=True)
                
                chunk_size = os.path.getsize(chunk_path)
                self.logger.info(f"Created chunk {i+1}/{num_chunks}: {self.format_file_size(chunk_size)} ({self.format_timestamp(start_time)} - {self.format_timestamp(end_time)})")
                
                chunk_info.append({
                    'path': chunk_path,
                    'start_offset': start_time,
                    'duration': end_time - start_time
                })
            
            return chunk_info
            
        except Exception as e:
            self.logger.error(f"Error splitting audio: {e}")
            raise TranscriptionError(f"Failed to split audio: {e}")
    
    def transcribe_chunk_sync(self, chunk_path: str, chunk_index: int, start_offset: float) -> Dict:
        """Synchronous transcription of a single chunk for parallel processing
        
        Args:
            chunk_path: Path to audio chunk
            chunk_index: Index of the chunk
            start_offset: Time offset for timestamps
            
        Returns:
            Transcription result with adjusted timestamps
        """
        try:
            self.logger.info(f"Transcribing chunk {chunk_index + 1}...")
            
            with open(chunk_path, "rb") as audio_file:
                chunk_transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["word"]
                )
            
            chunk_data_dict = chunk_transcript.model_dump()
            
            if not chunk_data_dict:
                self.logger.warning(f"Empty transcript for chunk {chunk_index + 1}, skipping...")
                return {
                    'chunk_index': chunk_index,
                    'segments': [],
                    'words': [],
                    'text': '',
                    'success': False
                }
            
            # Adjust timestamps by adding chunk start offset
            segments = chunk_data_dict.get('segments', [])
            if segments:
                for segment in segments:
                    if segment:
                        segment['start'] += start_offset
                        segment['end'] += start_offset
            
            words = chunk_data_dict.get('words', [])
            if words:
                for word in words:
                    if word:
                        word['start'] += start_offset
                        word['end'] += start_offset
            
            result = {
                'chunk_index': chunk_index,
                'segments': segments or [],
                'words': words or [],
                'text': chunk_data_dict.get('text', ''),
                'success': True
            }
            
            self.logger.info(f"Chunk {chunk_index + 1} processed: {len(segments or [])} segments, {len(words or [])} words")
            return result
            
        except Exception as chunk_error:
            self.logger.error(f"Error transcribing chunk {chunk_index + 1}: {chunk_error}")
            return {
                'chunk_index': chunk_index,
                'segments': [],
                'words': [],
                'text': '',
                'success': False,
                'error': str(chunk_error)
            }
    
    async def transcribe_chunks_parallel(self, chunk_info: List[Dict]) -> List[Dict]:
        """Transcribe multiple audio chunks in parallel
        
        Args:
            chunk_info: List of chunk information
            
        Returns:
            List of successful transcription results
        """
        self.logger.info(f"Starting parallel transcription of {len(chunk_info)} chunks...")
        
        loop = asyncio.get_event_loop()
        max_workers = min(self.settings.max_concurrent_chunks, len(chunk_info))
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for i, chunk_data in enumerate(chunk_info):
                future = loop.run_in_executor(
                    executor,
                    self.transcribe_chunk_sync,
                    chunk_data['path'],
                    i,
                    chunk_data['start_offset']
                )
                futures.append(future)
            
            results = await asyncio.gather(*futures, return_exceptions=True)
            
            successful_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self.logger.error(f"Chunk {i + 1} failed with exception: {result}")
                elif result and result.get('success', False):
                    successful_results.append(result)
                else:
                    self.logger.warning(f"Chunk {i + 1} returned empty or failed result")
            
            self.logger.info(f"Parallel transcription completed: {len(successful_results)}/{len(chunk_info)} chunks successful")
            return successful_results
    
    async def transcribe_audio_with_timestamps(self, audio_path: str) -> Dict:
        """Transcribe audio with word-level timestamps, handling large files by chunking
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Complete transcription with timestamps
            
        Raises:
            TranscriptionError: If transcription fails
        """
        try:
            self._ensure_client()
            
            # Split audio if necessary
            chunk_info = self.split_audio_for_transcription(audio_path)
            
            if len(chunk_info) == 1:
                # Single file transcription
                with open(chunk_info[0]['path'], "rb") as audio_file:
                    transcript = self.client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        response_format="verbose_json",
                        timestamp_granularities=["word"]
                    )
                
                result = transcript.model_dump()
                self.logger.info("Single-file transcription completed")
                return result
            
            else:
                # Multi-chunk transcription
                chunk_results = await self.transcribe_chunks_parallel(chunk_info)
                
                if not chunk_results:
                    raise TranscriptionError("All audio chunks failed to transcribe")
                
                # Merge results
                all_segments = []
                all_words = []
                full_text = ""
                
                chunk_results.sort(key=lambda x: x.get('chunk_index', 0))
                
                for result in chunk_results:
                    all_segments.extend(result.get('segments', []))
                    all_words.extend(result.get('words', []))
                    
                    chunk_text = result.get('text', '')
                    if chunk_text:
                        if full_text:
                            full_text += " " + chunk_text
                        else:
                            full_text = chunk_text
                
                # Clean up chunk files
                for chunk_data in chunk_info:
                    chunk_path = chunk_data['path']
                    if chunk_path != audio_path and os.path.exists(chunk_path):
                        try:
                            os.remove(chunk_path)
                            self.logger.debug(f"Cleaned up audio chunk: {chunk_path}")
                        except OSError:
                            pass
                
                merged_transcript = {
                    'text': full_text,
                    'segments': all_segments,
                    'words': all_words,
                    'language': 'en'
                }
                
                self.logger.info(f"Multi-chunk transcription completed: {len(all_segments)} segments, {len(all_words)} words")
                return merged_transcript
                
        except Exception as e:
            self.logger.error(f"Error transcribing audio: {e}")
            raise TranscriptionError(f"Failed to transcribe audio: {e}")
    
    async def transcribe_video(self, video_path: str) -> Dict:
        """Complete video transcription workflow
        
        Args:
            video_path: Path to video file
            
        Returns:
            Transcription result with timestamps
        """
        temp_files = []
        
        try:
            # Extract audio
            audio_path = self.extract_audio_from_video(video_path)
            temp_files.append(audio_path)
            
            # Transcribe
            result = await self.transcribe_audio_with_timestamps(audio_path)
            
            return result
            
        finally:
            # Clean up temporary files
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                        self.logger.debug(f"Cleaned up temp file: {temp_file}")
                    except OSError as e:
                        self.logger.warning(f"Could not clean up temp file {temp_file}: {e}") 
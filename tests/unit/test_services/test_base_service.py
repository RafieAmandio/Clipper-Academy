import pytest
import os
from unittest.mock import patch, Mock

from app.services.base import BaseService
from app.config.settings import Settings


class TestBaseService:
    """Test the BaseService class"""
    
    def test_initialization(self, test_settings):
        """Test that BaseService initializes correctly"""
        service = BaseService(test_settings)
        
        assert service.settings == test_settings
        assert service.logger is not None
        # Logger name includes the app prefix
        assert "services.base" in service.logger.name
    
    def test_directory_creation(self, test_settings, temp_dir):
        """Test that required directories are created"""
        # Update settings to use temp directory
        test_settings.upload_dir = os.path.join(temp_dir, "uploads")
        test_settings.clips_dir = os.path.join(temp_dir, "clips")
        test_settings.temp_dir = os.path.join(temp_dir, "temp")
        test_settings.results_dir = os.path.join(temp_dir, "results")
        
        service = BaseService(test_settings)
        
        # Check that directories were created
        assert os.path.exists(test_settings.upload_dir)
        assert os.path.exists(test_settings.clips_dir)
        assert os.path.exists(test_settings.temp_dir)
        assert os.path.exists(test_settings.results_dir)
    
    def test_format_timestamp(self, base_service):
        """Test timestamp formatting"""
        assert base_service.format_timestamp(0) == "00:00"
        assert base_service.format_timestamp(65) == "01:05"
        assert base_service.format_timestamp(3661) == "61:01"
        assert base_service.format_timestamp(120.5) == "02:00"
    
    def test_format_file_size(self, base_service):
        """Test file size formatting"""
        assert base_service.format_file_size(0) == "0.0 B"
        assert base_service.format_file_size(1024) == "1.0 KB"
        assert base_service.format_file_size(1024 * 1024) == "1.0 MB"
        assert base_service.format_file_size(1024 * 1024 * 1024) == "1.0 GB"
        assert base_service.format_file_size(1536) == "1.5 KB"
    
    def test_cleanup_temp_files(self, base_service, temp_dir):
        """Test cleanup of temporary files"""
        # Create some test files
        temp_files = []
        for i in range(3):
            temp_file = os.path.join(temp_dir, f"temp_file_{i}.txt")
            with open(temp_file, 'w') as f:
                f.write(f"test content {i}")
            temp_files.append(temp_file)
        
        # Verify files exist
        for temp_file in temp_files:
            assert os.path.exists(temp_file)
        
        # Cleanup
        base_service.cleanup_temp_files(temp_files)
        
        # Verify files are removed
        for temp_file in temp_files:
            assert not os.path.exists(temp_file)
    
    def test_cleanup_temp_files_handles_missing_files(self, base_service):
        """Test that cleanup handles missing files gracefully"""
        non_existent_files = ["/path/that/does/not/exist.txt"]
        
        # Should not raise an exception
        base_service.cleanup_temp_files(non_existent_files)
    
    @patch('os.makedirs')
    def test_directory_creation_error_handling(self, mock_makedirs, test_settings):
        """Test that directory creation errors are handled gracefully"""
        mock_makedirs.side_effect = OSError("Permission denied")
        
        # Should not raise an exception due to error handling
        service = BaseService(test_settings)
        assert service.settings == test_settings 
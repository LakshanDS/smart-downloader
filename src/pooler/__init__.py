"""
Pooler Package - Process Runners

Contains process runners for download and upload modules.
These run as separate processes for isolation and reliability.
"""

from .download_runner import (
    start_download_process,
    stop_download_process,
    get_download_status,
    restart_download_process
)

__all__ = [
    'start_download_process',
    'stop_download_process',
    'get_download_status',
    'restart_download_process',
    'start_upload_process',
    'stop_upload_process'
]


def start_upload_process():
    """Placeholder for upload process starter."""
    pass


def stop_upload_process():
    """Placeholder for upload process stopper."""
    pass

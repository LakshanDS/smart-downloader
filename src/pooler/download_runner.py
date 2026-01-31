"""
Download Runner - Process Lifecycle Manager

This module manages the download process lifecycle:
- Spawns download process
- Tracks process ID
- Handles graceful shutdown
- Provides status monitoring
"""

import os
import sys
import signal
import time
import subprocess
from pathlib import Path
from typing import Optional

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from database.manager import DatabaseManager
import src.config


class DownloadRunner:
    """Manages the download process lifecycle."""

    def __init__(self, db_path: str = None):
        """Initialize download runner.

        Args:
            db_path: Path to database file (uses config if not provided)
        """
        self.db_path = db_path or src.config.DATABASE_PATH
        self.process: Optional[subprocess.Popen] = None
        self.pid_file = project_root / "sessions" / "download.pid"

    def start(self) -> bool:
        """Start the download process.

        Returns:
            True if process started successfully, False otherwise
        """
        # Check if already running
        if self.is_running():
            print("Download process already running")
            return False

        # Create sessions directory if needed
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)

        # Start download pooler as subprocess
        try:
            # Use python executable from current environment
            python_exe = sys.executable
            pooler_script = project_root / "src" / "download_module" / "download_pooler.py"

            # Start process with no output (it logs to database)
            self.process = subprocess.Popen(
                [python_exe, str(pooler_script)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True  # Detach from parent process
            )

            # Save PID
            with open(self.pid_file, 'w') as f:
                f.write(str(self.process.pid))

            print(f"Download process started (PID: {self.process.pid})")
            return True

        except Exception as e:
            print(f"Failed to start download process: {e}")
            return False

    def stop(self, timeout: int = 30) -> bool:
        """Stop the download process gracefully.

        Args:
            timeout: Maximum time to wait for graceful shutdown (seconds)

        Returns:
            True if process stopped successfully, False otherwise
        """
        # Check if running
        if not self.is_running():
            print("Download process not running")
            return True

        try:
            # Try graceful shutdown first
            pid = self._get_pid()
            if pid:
                # Send SIGTERM
                os.kill(pid, signal.SIGTERM)

                # Wait for process to exit
                start_time = time.time()
                while time.time() - start_time < timeout:
                    if not self._is_process_alive(pid):
                        break
                    time.sleep(1)

                # Force kill if still running
                if self._is_process_alive(pid):
                    print("Process did not stop gracefully, forcing...")
                    os.kill(pid, signal.SIGKILL)
                    time.sleep(1)

            # Clean up PID file
            if self.pid_file.exists():
                self.pid_file.unlink()

            print("Download process stopped")
            return True

        except Exception as e:
            print(f"Failed to stop download process: {e}")
            return False

    def is_running(self) -> bool:
        """Check if download process is running.

        Returns:
            True if process is running, False otherwise
        """
        pid = self._get_pid()
        if pid is None:
            return False
        return self._is_process_alive(pid)

    def get_status(self) -> dict:
        """Get download process status.

        Returns:
            Dictionary with status information
        """
        is_running = self.is_running()
        pid = self._get_pid()

        status = {
            'running': is_running,
            'pid': pid,
            'pid_file': str(self.pid_file) if self.pid_file.exists() else None
        }

        # Add database info if running
        if is_running and self.db_path:
            try:
                db = DatabaseManager(self.db_path)
                summary = db.get_queue_summary()
                status['queue'] = summary
            except Exception as e:
                status['queue_error'] = str(e)

        return status

    def restart(self, timeout: int = 30) -> bool:
        """Restart the download process.

        Args:
            timeout: Maximum time to wait for graceful shutdown (seconds)

        Returns:
            True if restart successful, False otherwise
        """
        print("Restarting download process...")
        self.stop(timeout)
        time.sleep(2)  # Brief pause
        return self.start()

    # === Private Methods ===

    def _get_pid(self) -> Optional[int]:
        """Get PID from PID file.

        Returns:
            PID if file exists and contains valid PID, None otherwise
        """
        if not self.pid_file.exists():
            return None

        try:
            with open(self.pid_file, 'r') as f:
                pid = int(f.read().strip())
            return pid
        except (ValueError, IOError):
            return None

    def _is_process_alive(self, pid: int) -> bool:
        """Check if process with given PID is alive.

        Args:
            pid: Process ID to check

        Returns:
            True if process is alive, False otherwise
        """
        try:
            # Send signal 0 to check if process exists
            os.kill(pid, 0)
            return True
        except OSError:
            return False


# === Module-level Functions ===

_runner: Optional[DownloadRunner] = None


def start_download_process(db_path: str = None) -> bool:
    """Start the download process (module-level function).

    Args:
        db_path: Path to database file (uses config if not provided)

    Returns:
        True if process started successfully, False otherwise
    """
    global _runner
    if _runner is None:
        _runner = DownloadRunner(db_path)
    return _runner.start()


def stop_download_process(timeout: int = 30) -> bool:
    """Stop the download process (module-level function).

    Args:
        timeout: Maximum time to wait for graceful shutdown (seconds)

    Returns:
        True if process stopped successfully, False otherwise
    """
    global _runner
    if _runner is None:
        return True  # Not running, so success
    return _runner.stop(timeout)


def get_download_status() -> dict:
    """Get download process status (module-level function).

    Returns:
        Dictionary with status information
    """
    global _runner
    if _runner is None:
        return {'running': False, 'pid': None}
    return _runner.get_status()


def restart_download_process(timeout: int = 30) -> bool:
    """Restart the download process (module-level function).

    Args:
        timeout: Maximum time to wait for graceful shutdown (seconds)

    Returns:
        True if restart successful, False otherwise
    """
    global _runner
    if _runner is None:
        _runner = DownloadRunner()
    return _runner.restart(timeout)


# === CLI Entry Point ===

if __name__ == "__main__":
    """CLI for manual control of download process."""
    import argparse

    parser = argparse.ArgumentParser(description="Download Process Manager")
    parser.add_argument('command', choices=['start', 'stop', 'restart', 'status'],
                       help='Command to execute')

    args = parser.parse_args()

    runner = DownloadRunner()

    if args.command == 'start':
        success = runner.start()
        sys.exit(0 if success else 1)
    elif args.command == 'stop':
        success = runner.stop()
        sys.exit(0 if success else 1)
    elif args.command == 'restart':
        success = runner.restart()
        sys.exit(0 if success else 1)
    elif args.command == 'status':
        status = runner.get_status()
        print(f"Download Process Status:")
        print(f"  Running: {status['running']}")
        print(f"  PID: {status['pid']}")
        if 'queue' in status:
            print(f"  Queue: {status['queue']}")
        sys.exit(0)

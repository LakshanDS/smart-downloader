"""
Pytest configuration for Smart Downloader tests.
"""

import os
import sys

# Set test environment variables BEFORE any imports
os.environ['TELEGRAM_BOT_TOKEN'] = 'test_token_12345'
os.environ['DATABASE_PATH'] = ':memory:'

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )


@pytest.fixture
def mock_env():
    """Set up mock environment variables."""
    original_env = os.environ.copy()

    os.environ['TELEGRAM_BOT_TOKEN'] = 'test_token_12345'
    os.environ['DATABASE_PATH'] = ':memory:'
    os.environ['LOG_LEVEL'] = 'DEBUG'

    yield

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)

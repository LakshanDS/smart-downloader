#!/usr/bin/env python3
"""
Run Smart Downloader Bot

Usage:
    python run.py
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from bot import main

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Main entry point for lightrag-mcp-connect package.
"""

import asyncio
from .cli import main

if __name__ == "__main__":
    asyncio.run(main())

"""
CLI entry point for the Daniel LightRAG MCP server.
"""

import asyncio
import sys
from .server import main


def cli():
    """CLI entry point."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down server...")
        sys.exit(0)
    except Exception as e:
        print(f"Error starting server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()

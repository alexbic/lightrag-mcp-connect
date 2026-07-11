#!/usr/bin/env python3
"""
Test runner script for lightrag-mcp-connect test suite.
"""

import sys
import os
import subprocess
import argparse
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def run_tests(test_type: str = "all", verbose: bool = False, coverage: bool = False):
    """Run the test suite."""
    
    # Base pytest command
    cmd = ["python3", "-m", "pytest"]
    
    # Add verbosity
    if verbose:
        cmd.append("-v")
    else:
        cmd.append("-q")
    
    # Add coverage if requested
    if coverage:
        cmd.extend(["--cov=lightrag_mcp_connect", "--cov-report=term-missing", "--cov-report=html"])
    
    # Add specific test selection
    if test_type == "unit":
        cmd.extend(["tests/test_server.py", "tests/test_client.py", "tests/test_models.py"])
    elif test_type == "integration":
        cmd.append("tests/test_integration.py")
    elif test_type == "models":
        cmd.append("tests/test_models.py")
    elif test_type == "server":
        cmd.append("tests/test_server.py")
    elif test_type == "client":
        cmd.append("tests/test_client.py")
    elif test_type == "all":
        cmd.append("tests/")
    else:
        print(f"Unknown test type: {test_type}")
        return 1
    
    # Add asyncio mode
    cmd.append("--asyncio-mode=auto")
    
    print(f"Running command: {' '.join(cmd)}")
    print("-" * 50)
    
    # Run the tests
    try:
        result = subprocess.run(cmd, cwd=Path(__file__).parent.parent)
        return result.returncode
    except KeyboardInterrupt:
        print("\nTests interrupted by user")
        return 1
    except Exception as e:
        print(f"Error running tests: {e}")
        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run lightrag-mcp-connect tests")
    parser.add_argument(
        "test_type",
        nargs="?",
        default="all",
        choices=["all", "unit", "integration", "models", "server", "client"],
        help="Type of tests to run (default: all)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Run tests in verbose mode"
    )
    parser.add_argument(
        "-c", "--coverage",
        action="store_true",
        help="Run tests with coverage reporting"
    )
    parser.add_argument(
        "--install-deps",
        action="store_true",
        help="Install test dependencies before running tests"
    )
    
    args = parser.parse_args()
    
    # Install dependencies if requested
    if args.install_deps:
        print("Installing test dependencies...")
        try:
            subprocess.run([
                sys.executable, "-m", "pip", "install", "-e", ".[dev]"
            ], check=True, cwd=Path(__file__).parent.parent)
            print("Dependencies installed successfully")
        except subprocess.CalledProcessError as e:
            print(f"Failed to install dependencies: {e}")
            return 1
    
    # Run the tests
    return run_tests(args.test_type, args.verbose, args.coverage)


if __name__ == "__main__":
    sys.exit(main())
"""
Test runner script for Ark Relay Gateway
"""

import os
import sys
import subprocess
import argparse


def run_unit_tests():
    """Run unit tests using unittest"""
    print("Running unit tests...")
    result = subprocess.run([
        sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"
    ], cwd=os.path.dirname(os.path.abspath(__file__)))
    return result.returncode == 0


def run_pytest():
    """Run tests using pytest"""
    print("Running tests with pytest...")
    result = subprocess.run([
        sys.executable, "-m", "pytest", "tests/", "-v"
    ], cwd=os.path.dirname(os.path.abspath(__file__)))
    return result.returncode == 0


def run_specific_test(test_name):
    """Run a specific test"""
    print(f"Running specific test: {test_name}")
    result = subprocess.run([
        sys.executable, "tests/test_grpc_clients.py", test_name, "-v"
    ], cwd=os.path.dirname(os.path.abspath(__file__)))
    return result.returncode == 0


def run_coverage():
    """Run tests with coverage report"""
    print("Running tests with coverage...")
    result = subprocess.run([
        sys.executable, "-m", "pytest", "tests/", "--cov=grpc_clients", "--cov-report=html", "--cov-report=term"
    ], cwd=os.path.dirname(os.path.abspath(__file__)))
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Run tests for Ark Relay Gateway")
    parser.add_argument("--test", type=str, help="Run specific test (e.g., TestCircuitBreaker.test_successful_call_remains_closed)")
    parser.add_argument("--pytest", action="store_true", help="Use pytest instead of unittest")
    parser.add_argument("--coverage", action="store_true", help="Run with coverage report")

    args = parser.parse_args()

    if args.coverage:
        success = run_coverage()
    elif args.test:
        success = run_specific_test(args.test)
    elif args.pytest:
        success = run_pytest()
    else:
        success = run_unit_tests()

    if success:
        print("\n✅ All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
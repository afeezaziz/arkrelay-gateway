#!/usr/bin/env python3
"""
Comprehensive test runner for Ark Relay Gateway Phase 5
"""

import sys
import subprocess
import os
from datetime import datetime

def run_test_file(test_file):
    """Run a specific test file"""
    print(f"\n🧪 Running {test_file}...")
    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest",
            test_file,
            "-v",
            "--tb=short",
            "--color=yes"
        ], capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__)))

        if result.returncode == 0:
            print(f"✅ {test_file} - PASSED")
            return True
        else:
            print(f"❌ {test_file} - FAILED")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            return False
    except Exception as e:
        print(f"❌ Error running {test_file}: {e}")
        return False

def main():
    """Run all Phase 5 tests"""
    print("🚀 Starting Ark Relay Gateway Phase 5 Test Suite")
    print("=" * 60)

    test_files = [
        "test_transaction_processor.py",
        "test_signing_orchestrator.py",
        "test_asset_manager.py",
        "test_phase5_integration.py",
        "test_config.py",
        "test_grpc_clients.py",
        "test_nostr_encryption.py"
    ]

    passed = 0
    failed = 0

    start_time = datetime.now()

    for test_file in test_files:
        if run_test_file(test_file):
            passed += 1
        else:
            failed += 1

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print("\n" + "=" * 60)
    print(f"📊 Test Results Summary:")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📈 Total: {passed + failed}")
    print(f"⏱️  Duration: {duration:.2f} seconds")

    if failed == 0:
        print("\n🎉 All tests passed! Phase 5 implementation is working correctly.")
        return 0
    else:
        print(f"\n💥 {failed} test(s) failed. Please review the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
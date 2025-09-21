#!/usr/bin/env python3
"""
Simple test script for session management functionality
"""
import sys
import os
import json
from datetime import datetime, timedelta

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from session_manager import get_session_manager, SessionState
from challenge_manager import get_challenge_manager

def test_session_creation():
    """Test creating a session"""
    print("Testing session creation...")

    session_manager = get_session_manager()

    user_pubkey = "test_user_pubkey_12345"
    session_type = "p2p_transfer"
    intent_data = {
        "amount": 1000,
        "recipient_pubkey": "recipient_pubkey_67890",
        "asset_id": "BTC"
    }

    try:
        session = session_manager.create_session(user_pubkey, session_type, intent_data)
        print(f"✅ Session created: {session.session_id[:16]}...")
        print(f"   Status: {session.status}")
        print(f"   Type: {session.session_type}")
        print(f"   Expires: {session.expires_at}")
        return session.session_id
    except Exception as e:
        print(f"❌ Failed to create session: {e}")
        return None

def test_challenge_creation(session_id):
    """Test creating a challenge for a session"""
    print(f"\nTesting challenge creation for session {session_id[:16]}...")

    session_manager = get_session_manager()
    challenge_manager = get_challenge_manager()

    try:
        context_data = {"test": "data"}
        challenge = challenge_manager.create_and_store_challenge(session_id, context_data)

        if challenge:
            print(f"✅ Challenge created: {challenge.challenge_id[:16]}...")
            print(f"   Context: {challenge.context[:50]}...")
            print(f"   Expires: {challenge.expires_at}")
            return challenge.challenge_id
        else:
            print("❌ Failed to create challenge")
            return None
    except Exception as e:
        print(f"❌ Failed to create challenge: {e}")
        return None

def test_session_status_transitions(session_id):
    """Test session status transitions"""
    print(f"\nTesting session status transitions for {session_id[:16]}...")

    session_manager = get_session_manager()

    try:
        # Test transitioning to challenge_sent
        success = session_manager.update_session_status(session_id, 'challenge_sent', 'Challenge sent')
        if success:
            print("✅ Transition to challenge_sent successful")
        else:
            print("❌ Failed to transition to challenge_sent")
            return False

        # Test transitioning to awaiting_signature
        success = session_manager.update_session_status(session_id, 'awaiting_signature', 'Awaiting signature')
        if success:
            print("✅ Transition to awaiting_signature successful")
        else:
            print("❌ Failed to transition to awaiting_signature")
            return False

        # Test completing session
        result_data = {"txid": "test_txid", "status": "completed"}
        success = session_manager.complete_session(session_id, result_data)
        if success:
            print("✅ Session completed successfully")
        else:
            print("❌ Failed to complete session")
            return False

        return True
    except Exception as e:
        print(f"❌ Error during status transitions: {e}")
        return False

def test_get_session_info(session_id):
    """Test getting session information"""
    print(f"\nTesting session info retrieval for {session_id[:16]}...")

    session_manager = get_session_manager()

    try:
        session = session_manager.get_session(session_id)
        if session:
            print(f"✅ Session retrieved:")
            print(f"   ID: {session.session_id}")
            print(f"   Status: {session.status}")
            print(f"   Type: {session.session_type}")
            print(f"   Created: {session.created_at}")
            if session.result_data:
                print(f"   Result: {session.result_data}")
            return True
        else:
            print("❌ Session not found")
            return False
    except Exception as e:
        print(f"❌ Error getting session info: {e}")
        return False

def test_session_cleanup():
    """Test session cleanup functionality"""
    print("\nTesting session cleanup...")

    session_manager = get_session_manager()
    challenge_manager = get_challenge_manager()

    try:
        # Clean up expired sessions
        expired_sessions = session_manager.cleanup_expired_sessions()
        print(f"✅ Cleaned up {expired_sessions} expired sessions")

        # Clean up expired challenges
        expired_challenges = challenge_manager.cleanup_expired_challenges()
        print(f"✅ Cleaned up {expired_challenges} expired challenges")

        return True
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")
        return False

def main():
    """Run all tests"""
    print("🚀 Starting Session Management Tests")
    print("=" * 50)

    session_id = None

    try:
        # Test session creation
        session_id = test_session_creation()
        if not session_id:
            print("❌ Session creation failed, stopping tests")
            return

        # Test challenge creation
        challenge_id = test_challenge_creation(session_id)

        # Test status transitions
        transitions_ok = test_session_status_transitions(session_id)

        # Test session info retrieval
        info_ok = test_get_session_info(session_id)

        # Test cleanup
        cleanup_ok = test_session_cleanup()

        print("\n" + "=" * 50)
        print("🏁 Test Summary:")
        print(f"   Session Creation: ✅" if session_id else "   Session Creation: ❌")
        print(f"   Challenge Creation: ✅" if challenge_id else "   Challenge Creation: ❌")
        print(f"   Status Transitions: ✅" if transitions_ok else "   Status Transitions: ❌")
        print(f"   Info Retrieval: ✅" if info_ok else "   Info Retrieval: ❌")
        print(f"   Cleanup: ✅" if cleanup_ok else "   Cleanup: ❌")

        if all([session_id, challenge_id, transitions_ok, info_ok, cleanup_ok]):
            print("\n🎉 All tests passed!")
        else:
            print("\n⚠️  Some tests failed")

    except Exception as e:
        print(f"\n❌ Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
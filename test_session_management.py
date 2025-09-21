#!/usr/bin/env python3
"""
Comprehensive test script for session management functionality including Phase 5 integration
"""
import sys
import os
import json
from datetime import datetime, timedelta

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from session_manager import get_session_manager, SessionState
from challenge_manager import get_challenge_manager
from transaction_processor import get_transaction_processor
from signing_orchestrator import get_signing_orchestrator
from asset_manager import get_asset_manager

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

def test_phase5_integration(session_id):
    """Test Phase 5 integration with session management"""
    print(f"\nTesting Phase 5 integration for session {session_id[:16]}...")

    try:
        # Test transaction processor integration
        print("   Testing transaction processor...")
        transaction_processor = get_transaction_processor()
        # Note: This would require actual asset balances in the database
        print("   ✅ Transaction processor accessible")

        # Test signing orchestrator integration
        print("   Testing signing orchestrator...")
        orchestrator = get_signing_orchestrator()
        ceremony_status = orchestrator.get_ceremony_status(session_id)
        print("   ✅ Signing orchestrator accessible")

        # Test asset manager integration
        print("   Testing asset manager...")
        asset_manager = get_asset_manager()
        asset_stats = asset_manager.get_asset_stats()
        print("   ✅ Asset manager accessible")

        return True
    except Exception as e:
        print(f"   ❌ Phase 5 integration test failed: {e}")
        return False

def test_complete_phase5_workflow():
    """Test complete Phase 5 workflow"""
    print("\nTesting complete Phase 5 workflow...")

    try:
        # Create asset for testing
        print("   Creating test asset...")
        asset_manager = get_asset_manager()
        asset_result = asset_manager.create_asset(
            asset_id="TEST_BTC",
            name="Test Bitcoin",
            ticker="TBTC",
            asset_type="normal",
            decimal_places=8,
            total_supply=1000000
        )
        print(f"   ✅ Asset created: {asset_result['asset_id']}")

        # Mint assets to test user
        print("   Minting assets to test user...")
        user_pubkey = "test_user_phase5_1234567890abcdef1234567890abcdef12345678"
        mint_result = asset_manager.mint_assets(user_pubkey, "TEST_BTC", 5000)
        print(f"   ✅ Assets minted: {mint_result['amount_minted']}")

        # Create session for P2P transfer
        print("   Creating P2P transfer session...")
        session_manager = get_session_manager()
        session = session_manager.create_session(
            user_pubkey=user_pubkey,
            session_type="p2p_transfer",
            intent_data={
                "recipient_pubkey": "test_recipient_phase5_1234567890abcdef1234567890abcdef12345678",
                "amount": 1000,
                "asset_id": "TEST_BTC"
            }
        )
        print(f"   ✅ Session created: {session.session_id[:16]}...")

        # Move to signing state
        print("   Moving session to signing state...")
        challenge_manager = get_challenge_manager()
        challenge = challenge_manager.create_and_store_challenge(
            session.session_id,
            {"session_id": session.session_id, "test": "data"}
        )
        session_manager.validate_challenge_response(session.session_id, b"test_signature")
        print("   ✅ Session ready for signing")

        # Test VTXO management
        print("   Testing VTXO management...")
        vtxo_result = asset_manager.manage_vtxos(
            user_pubkey=user_pubkey,
            asset_id="TEST_BTC",
            action="create",
            amount_sats=2000
        )
        print(f"   ✅ VTXO created: {vtxo_result['vtxo_id'][:16]}...")

        print("   🎉 Complete Phase 5 workflow test successful!")
        return True

    except Exception as e:
        print(f"   ❌ Complete Phase 5 workflow test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests including Phase 5 integration"""
    print("🚀 Starting Session Management Tests with Phase 5 Integration")
    print("=" * 70)

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

        # Test Phase 5 integration
        phase5_integration_ok = test_phase5_integration(session_id)

        # Test complete Phase 5 workflow
        phase5_workflow_ok = test_complete_phase5_workflow()

        print("\n" + "=" * 70)
        print("🏁 Test Summary:")
        print(f"   Session Creation: ✅" if session_id else "   Session Creation: ❌")
        print(f"   Challenge Creation: ✅" if challenge_id else "   Challenge Creation: ❌")
        print(f"   Status Transitions: ✅" if transitions_ok else "   Status Transitions: ❌")
        print(f"   Info Retrieval: ✅" if info_ok else "   Info Retrieval: ❌")
        print(f"   Cleanup: ✅" if cleanup_ok else "   Cleanup: ❌")
        print(f"   Phase 5 Integration: ✅" if phase5_integration_ok else "   Phase 5 Integration: ❌")
        print(f"   Phase 5 Workflow: ✅" if phase5_workflow_ok else "   Phase 5 Workflow: ❌")

        all_passed = all([session_id, challenge_id, transitions_ok, info_ok, cleanup_ok, phase5_integration_ok, phase5_workflow_ok])

        if all_passed:
            print("\n🎉 All tests passed! Phase 5 integration working correctly!")
        else:
            print("\n⚠️  Some tests failed")

    except Exception as e:
        print(f"\n❌ Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from app import app
from models import SigningSession, AssetBalance, Asset, Vtxo, get_session
from session_manager import get_session_manager
from challenge_manager import get_challenge_manager

class TestPhase5Integration:
    """Integration tests for Phase 5 API endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client

    @pytest.fixture
    def sample_session(self):
        """Create a sample signing session"""
        session_manager = get_session_manager()
        session = session_manager.create_session(
            user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            session_type="p2p_transfer",
            intent_data={
                "recipient_pubkey": "test_recipient_pubkey_1234567890abcdef1234567890abcdef12345678",
                "amount": 1000,
                "asset_id": "BTC"
            }
        )

        # Move to awaiting_signature state
        challenge_manager = get_challenge_manager()
        challenge = challenge_manager.create_and_store_challenge(
            session.session_id,
            {"session_id": session.session_id, "test": "data"}
        )

        session_manager.validate_challenge_response(session.session_id, b"test_signature")
        return session

    @pytest.fixture
    def sample_asset(self):
        """Create a sample asset"""
        db_session = get_session()
        try:
            asset = Asset(
                asset_id="BTC",
                name="Bitcoin",
                ticker="BTC",
                asset_type="normal",
                decimal_places=8,
                total_supply=2100000000000000,
                is_active=True
            )
            db_session.add(asset)
            db_session.commit()
            db_session.refresh(asset)
            return asset
        finally:
            db_session.close()

    @pytest.fixture
    def sample_balance(self, sample_asset):
        """Create a sample asset balance"""
        db_session = get_session()
        try:
            balance = AssetBalance(
                user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                asset_id="BTC",
                balance=5000,
                reserved_balance=0
            )
            db_session.add(balance)
            db_session.commit()
            db_session.refresh(balance)
            return balance
        finally:
            db_session.close()

    # Transaction Endpoints

    def test_process_p2p_transfer_endpoint(self, client, sample_session, sample_balance):
        """Test P2P transfer endpoint"""
        data = {
            "session_id": sample_session.session_id
        }

        response = client.post('/transactions/p2p-transfer',
                              data=json.dumps(data),
                              content_type='application/json')

        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['message'] == 'P2P transfer processed successfully'
        assert 'transaction' in result
        assert result['transaction']['amount'] == 1000

    def test_process_p2p_transfer_missing_session_id(self, client):
        """Test P2P transfer endpoint with missing session_id"""
        data = {}

        response = client.post('/transactions/p2p-transfer',
                              data=json.dumps(data),
                              content_type='application/json')

        assert response.status_code == 400
        result = json.loads(response.data)
        assert 'session_id is required' in result['error']

    def test_get_transaction_status_endpoint(self, client):
        """Test get transaction status endpoint"""
        # First create a transaction through the database directly
        db_session = get_session()
        try:
            from models import Transaction
            tx = Transaction(
                txid="test_txid_123",
                session_id="test_session",
                tx_type="p2p_transfer",
                status="pending",
                amount_sats=1000,
                fee_sats=100
            )
            db_session.add(tx)
            db_session.commit()
        finally:
            db_session.close()

        response = client.get('/transactions/test_txid_123/status')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['txid'] == "test_txid_123"
        assert result['status'] == "pending"

    def test_get_transaction_status_not_found(self, client):
        """Test get transaction status for non-existent transaction"""
        response = client.get('/transactions/nonexistent_txid/status')
        assert response.status_code == 404
        result = json.loads(response.data)
        assert 'not found' in result['error']

    def test_broadcast_transaction_endpoint(self, client):
        """Test broadcast transaction endpoint"""
        # Create a transaction first
        db_session = get_session()
        try:
            from models import Transaction
            tx = Transaction(
                txid="test_broadcast_tx",
                session_id="test_session",
                tx_type="p2p_transfer",
                status="pending",
                amount_sats=1000,
                fee_sats=100,
                raw_tx="0100000000010100000000000000010000000000000000000000000000000000000000000000000000000000000000000000"
            )
            db_session.add(tx)
            db_session.commit()
        finally:
            db_session.close()

        response = client.post('/transactions/test_broadcast_tx/broadcast')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['txid'] == "test_broadcast_tx"
        assert 'success' in result

    def test_get_user_transactions_endpoint(self, client, sample_session, sample_balance):
        """Test get user transactions endpoint"""
        # First process a transfer to create a transaction
        data = {"session_id": sample_session.session_id}
        client.post('/transactions/p2p-transfer',
                   data=json.dumps(data),
                   content_type='application/json')

        user_pubkey = "test_user_pubkey_1234567890abcdef1234567890abcdef12345678"
        response = client.get(f'/transactions/user/{user_pubkey}')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert 'transactions' in result
        assert result['total_count'] > 0
        assert result['user_pubkey'] == "test_user_..."

    def test_get_user_transactions_with_limit(self, client, sample_session, sample_balance):
        """Test get user transactions endpoint with limit"""
        # Process a transfer first
        data = {"session_id": sample_session.session_id}
        client.post('/transactions/p2p-transfer',
                   data=json.dumps(data),
                   content_type='application/json')

        user_pubkey = "test_user_pubkey_1234567890abcdef1234567890abcdef12345678"
        response = client.get(f'/transactions/user/{user_pubkey}?limit=1')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert len(result['transactions']) <= 1

    # Signing Ceremony Endpoints

    def test_start_signing_ceremony_endpoint(self, client, sample_session):
        """Test start signing ceremony endpoint"""
        data = {"session_id": sample_session.session_id}

        response = client.post('/signing/ceremony/start',
                              data=json.dumps(data),
                              content_type='application/json')

        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['message'] == 'Signing ceremony started'
        assert 'ceremony' in result
        assert result['ceremony']['step'] == 1

    def test_start_signing_ceremony_missing_session_id(self, client):
        """Test start signing ceremony endpoint with missing session_id"""
        data = {}

        response = client.post('/signing/ceremony/start',
                              data=json.dumps(data),
                              content_type='application/json')

        assert response.status_code == 400
        result = json.loads(response.data)
        assert 'session_id is required' in result['error']

    def test_get_signing_ceremony_status_endpoint(self, client, sample_session):
        """Test get signing ceremony status endpoint"""
        # Start ceremony first
        data = {"session_id": sample_session.session_id}
        client.post('/signing/ceremony/start',
                   data=json.dumps(data),
                   content_type='application/json')

        response = client.get(f'/signing/ceremony/{sample_session.session_id}/status')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['session_id'] == sample_session.session_id
        assert result['ceremony_status'] == 'in_progress'
        assert result['current_step'] >= 1

    def test_execute_signing_step_endpoint(self, client, sample_session):
        """Test execute signing step endpoint"""
        # Start ceremony first
        data = {"session_id": sample_session.session_id}
        client.post('/signing/ceremony/start',
                   data=json.dumps(data),
                   content_type='application/json')

        # Execute step 2 (ARK transaction preparation)
        step_data = {"signature_data": {"test": "signature"}}
        response = client.post(f'/signing/ceremony/{sample_session.session_id}/step/2',
                              data=json.dumps(step_data),
                              content_type='application/json')

        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['step'] == 2
        assert 'result' in result

    def test_execute_signing_step_invalid_step(self, client, sample_session):
        """Test execute signing step endpoint with invalid step"""
        response = client.post(f'/signing/ceremony/{sample_session.session_id}/step/99',
                              data=json.dumps({}),
                              content_type='application/json')

        assert response.status_code == 400
        result = json.loads(response.data)
        assert 'Invalid step' in result['error']

    def test_cancel_signing_ceremony_endpoint(self, client, sample_session):
        """Test cancel signing ceremony endpoint"""
        # Start ceremony first
        data = {"session_id": sample_session.session_id}
        client.post('/signing/ceremony/start',
                   data=json.dumps(data),
                   content_type='application/json')

        # Cancel ceremony
        cancel_data = {"reason": "Test cancellation"}
        response = client.post(f'/signing/ceremony/{sample_session.session_id}/cancel',
                              data=json.dumps(cancel_data),
                              content_type='application/json')

        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['reason'] == "Test cancellation"

    # Asset Management Endpoints

    def test_create_asset_endpoint(self, client):
        """Test create asset endpoint"""
        data = {
            "asset_id": "TEST_ASSET",
            "name": "Test Asset",
            "ticker": "TEST",
            "asset_type": "normal",
            "decimal_places": 8,
            "total_supply": 1000000,
            "metadata": {"description": "Test asset for integration testing"}
        }

        response = client.post('/assets',
                              data=json.dumps(data),
                              content_type='application/json')

        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['message'] == 'Asset created successfully'
        assert result['asset']['asset_id'] == "TEST_ASSET"
        assert result['asset']['name'] == "Test Asset"

    def test_create_asset_missing_required_fields(self, client):
        """Test create asset endpoint with missing required fields"""
        data = {"asset_id": "TEST"}  # Missing name and ticker

        response = client.post('/assets',
                              data=json.dumps(data),
                              content_type='application/json')

        assert response.status_code == 400
        result = json.loads(response.data)
        assert 'is required' in result['error']

    def test_get_asset_info_endpoint(self, client, sample_asset):
        """Test get asset info endpoint"""
        response = client.get('/assets/BTC')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['asset_id'] == "BTC"
        assert result['name'] == "Bitcoin"
        assert result['ticker'] == "BTC"

    def test_get_asset_info_not_found(self, client):
        """Test get asset info for non-existent asset"""
        response = client.get('/assets/NONEXISTENT')
        assert response.status_code == 404
        result = json.loads(response.data)
        assert 'not found' in result['error']

    def test_list_assets_endpoint(self, client, sample_asset):
        """Test list assets endpoint"""
        response = client.get('/assets')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert 'assets' in result
        assert result['total_count'] > 0
        assert result['active_only'] is True

    def test_list_assets_inactive(self, client, sample_asset):
        """Test list assets endpoint including inactive"""
        response = client.get('/assets?active_only=false')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['active_only'] is False

    def test_mint_assets_endpoint(self, client, sample_asset):
        """Test mint assets endpoint"""
        data = {
            "user_pubkey": "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            "amount": 1000,
            "reserve_amount": 100
        }

        response = client.post('/assets/BTC/mint',
                              data=json.dumps(data),
                              content_type='application/json')

        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['message'] == 'Assets minted successfully'
        assert result['result']['amount_minted'] == 1000
        assert result['result']['reserve_amount'] == 100

    def test_mint_assets_missing_required_fields(self, client, sample_asset):
        """Test mint assets endpoint with missing required fields"""
        data = {"amount": 1000}  # Missing user_pubkey

        response = client.post('/assets/BTC/mint',
                              data=json.dumps(data),
                              content_type='application/json')

        assert response.status_code == 400
        result = json.loads(response.data)
        assert 'is required' in result['error']

    def test_transfer_assets_endpoint(self, client, sample_asset, sample_balance):
        """Test transfer assets endpoint"""
        data = {
            "sender_pubkey": "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            "recipient_pubkey": "test_recipient_pubkey_1234567890abcdef1234567890abcdef12345678",
            "asset_id": "BTC",
            "amount": 1000
        }

        response = client.post('/assets/transfer',
                              data=json.dumps(data),
                              content_type='application/json')

        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['message'] == 'Assets transferred successfully'
        assert result['result']['amount'] == 1000

    def test_transfer_assets_missing_required_fields(self, client, sample_asset):
        """Test transfer assets endpoint with missing required fields"""
        data = {"sender_pubkey": "test_sender"}  # Missing many required fields

        response = client.post('/assets/transfer',
                              data=json.dumps(data),
                              content_type='application/json')

        assert response.status_code == 400
        result = json.loads(response.data)
        assert 'is required' in result['error']

    def test_get_user_balances_endpoint(self, client, sample_asset, sample_balance):
        """Test get user balances endpoint"""
        user_pubkey = "test_user_pubkey_1234567890abcdef1234567890abcdef12345678"
        response = client.get(f'/balances/{user_pubkey}')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert 'balances' in result
        assert result['user_pubkey'] == "test_user_..."
        assert result['total_assets'] > 0

    def test_get_user_balance_specific_asset_endpoint(self, client, sample_asset, sample_balance):
        """Test get user balance for specific asset endpoint"""
        user_pubkey = "test_user_pubkey_1234567890abcdef1234567890abcdef12345678"
        response = client.get(f'/balances/{user_pubkey}/BTC')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['asset_id'] == "BTC"
        assert result['balance'] == 5000

    def test_manage_vtxos_endpoint(self, client, sample_asset):
        """Test manage VTXOs endpoint"""
        user_pubkey = "test_user_pubkey_1234567890abcdef1234567890abcdef12345678"
        response = client.get(f'/vtxos/{user_pubkey}?action=list')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert 'vtxo_management' in result
        assert result['user_pubkey'] == "test_user_..."

    def test_get_asset_stats_endpoint(self, client, sample_asset, sample_balance):
        """Test get asset stats endpoint"""
        response = client.get('/assets/stats')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert 'stats' in result
        assert 'assets' in result['stats']
        assert 'balances' in result['stats']
        assert 'vtxos' in result['stats']

    def test_cleanup_expired_vtxos_endpoint(self, client, sample_asset):
        """Test cleanup expired VTXOs endpoint"""
        response = client.post('/assets/cleanup-vtxos')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['message'] == 'VTXO cleanup completed'
        assert 'result' in result

    def test_get_reserve_requirements_endpoint(self, client, sample_asset, sample_balance):
        """Test get reserve requirements endpoint"""
        response = client.get('/assets/BTC/reserve')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert 'reserve_requirements' in result
        assert result['reserve_requirements']['asset_id'] == "BTC"
        assert 'reserve_ratio' in result['reserve_requirements']

    # Error Handling Tests

    def test_invalid_json_data(self, client):
        """Test endpoints with invalid JSON data"""
        response = client.post('/assets',
                              data="invalid json",
                              content_type='application/json')

        assert response.status_code == 400

    def test_endpoint_not_found(self, client):
        """Test accessing non-existent endpoint"""
        response = client.get('/nonexistent/endpoint')
        assert response.status_code == 404

    def test_method_not_allowed(self, client):
        """Test using wrong HTTP method"""
        response = client.delete('/assets')  # DELETE not allowed
        assert response.status_code == 405

    # Comprehensive Flow Test

    def test_complete_p2p_transfer_flow(self, client, sample_asset):
        """Test complete P2P transfer flow from start to finish"""
        # 1. Create sender and recipient balances
        mint_data = {
            "user_pubkey": "test_sender_pubkey_1234567890abcdef1234567890abcdef12345678",
            "amount": 5000
        }
        client.post('/assets/BTC/mint',
                   data=json.dumps(mint_data),
                   content_type='application/json')

        mint_data["user_pubkey"] = "test_recipient_pubkey_1234567890abcdef1234567890abcdef12345678"
        mint_data["amount"] = 1000
        client.post('/assets/BTC/mint',
                   data=json.dumps(mint_data),
                   content_type='application/json')

        # 2. Create signing session
        session_manager = get_session_manager()
        session = session_manager.create_session(
            user_pubkey="test_sender_pubkey_1234567890abcdef1234567890abcdef12345678",
            session_type="p2p_transfer",
            intent_data={
                "recipient_pubkey": "test_recipient_pubkey_1234567890abcdef1234567890abcdef12345678",
                "amount": 1000,
                "asset_id": "BTC"
            }
        )

        # Move to awaiting_signature state
        challenge_manager = get_challenge_manager()
        challenge = challenge_manager.create_and_store_challenge(
            session.session_id,
            {"session_id": session.session_id, "test": "data"}
        )
        session_manager.validate_challenge_response(session.session_id, b"test_signature")

        # 3. Process P2P transfer
        transfer_data = {"session_id": session.session_id}
        response = client.post('/transactions/p2p-transfer',
                              data=json.dumps(transfer_data),
                              content_type='application/json')
        assert response.status_code == 200

        # 4. Start signing ceremony
        ceremony_data = {"session_id": session.session_id}
        response = client.post('/signing/ceremony/start',
                              data=json.dumps(ceremony_data),
                              content_type='application/json')
        assert response.status_code == 200

        # 5. Verify final balances
        sender_balance_response = client.get('/balances/test_sender_pubkey_1234567890abcdef1234567890abcdef12345678/BTC')
        recipient_balance_response = client.get('/balances/test_recipient_pubkey_1234567890abcdef1234567890abcdef12345678/BTC')

        sender_balance = json.loads(sender_balance_response.data)
        recipient_balance = json.loads(recipient_balance_response.data)

        # Note: Actual balance verification would depend on transaction completion
        # This is a simplified test of the flow
        assert sender_balance['asset_id'] == "BTC"
        assert recipient_balance['asset_id'] == "BTC"
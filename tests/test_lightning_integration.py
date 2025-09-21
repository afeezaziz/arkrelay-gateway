"""
Lightning Integration Tests for Phase 6

Comprehensive test suite for Lightning Network integration including:
- LND gRPC client functionality
- Lightning manager operations
- Lightning monitoring and error handling
- API endpoint testing
- Integration with existing systems
"""

import pytest
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import json
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lightning_manager import LightningManager, LightningLiftRequest, LightningLandRequest, LightningOperationResult
from lightning_monitor import LightningMonitor, LightningEvent
from lightning_errors import LightningErrorHandler, LightningError, LightningErrorType, lightning_error_handler
from grpc_clients.lnd_client import LndClient, LightningBalance, OnchainBalance, ChannelInfo, LightningInvoice as LndLightningInvoice, Payment
from models import LightningInvoice, AssetBalance, SigningSession, get_session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class TestLndClient(unittest.TestCase):
    """Test LND gRPC client functionality"""

    def setUp(self):
        """Set up test fixtures"""
        from grpc_clients.grpc_client import ConnectionConfig, ServiceType

        self.config = ConnectionConfig(
            host="localhost",
            port=10009,
            tls_cert="/tmp/tls.cert",
            macaroon="/tmp/admin.macaroon"
        )
        self.client = LndClient(self.config)

    def test_client_initialization(self):
        """Test LND client initialization"""
        self.assertIsNotNone(self.client)
        self.assertEqual(self.client.config.service_type, ServiceType.LND)
        self.assertEqual(len(self.client._invoices_db), 0)
        self.assertEqual(len(self.client._payments_db), 0)
        self.assertEqual(self.client._invoice_counter, 0)

    def test_health_check(self):
        """Test LND health check"""
        result = self.client._health_check_impl()
        self.assertTrue(result)

    def test_get_lightning_balance(self):
        """Test getting Lightning balance"""
        balance = self.client.get_lightning_balance()

        self.assertIsInstance(balance, LightningBalance)
        self.assertGreaterEqual(balance.local_balance, 0)
        self.assertGreaterEqual(balance.remote_balance, 0)

    def test_get_onchain_balance(self):
        """Test getting on-chain balance"""
        balance = self.client.get_onchain_balance()

        self.assertIsInstance(balance, OnchainBalance)
        self.assertGreater(balance.total_balance, 0)
        self.assertGreater(balance.confirmed_balance, 0)

    def test_get_total_balance(self):
        """Test getting total balance information"""
        balances = self.client.get_total_balance()

        self.assertIn('lightning_local_balance', balances)
        self.assertIn('onchain_total', balances)
        self.assertIn('total_wallet_balance', balances)
        self.assertIsInstance(balances['lightning_local_balance'], int)

    def test_add_invoice(self):
        """Test creating a Lightning invoice"""
        amount = 1000
        memo = "Test invoice"

        invoice = self.client.add_invoice(amount, memo)

        self.assertIsInstance(invoice, LndLightningInvoice)
        self.assertEqual(invoice.value, amount)
        self.assertEqual(invoice.memo, memo)
        self.assertFalse(invoice.settled)
        self.assertIsNotNone(invoice.payment_request)
        self.assertIsNotNone(invoice.payment_hash)

    def test_list_invoices(self):
        """Test listing invoices"""
        # Add some invoices
        self.client.add_invoice(1000, "Test 1")
        self.client.add_invoice(2000, "Test 2")

        # List all invoices
        invoices = self.client.list_invoices()
        self.assertGreaterEqual(len(invoices), 2)

        # List pending only
        pending_invoices = self.client.list_invoices(pending_only=True)
        self.assertGreaterEqual(len(pending_invoices), 2)

    def test_lookup_invoice(self):
        """Test looking up invoice by payment hash"""
        # Create invoice
        invoice = self.client.add_invoice(1000, "Test lookup")

        # Lookup invoice
        found_invoice = self.client.lookup_invoice(invoice.payment_hash)

        self.assertIsNotNone(found_invoice)
        self.assertEqual(found_invoice.payment_hash, invoice.payment_hash)
        self.assertEqual(found_invoice.value, invoice.value)

    def test_send_payment(self):
        """Test sending a Lightning payment"""
        # Create invoice first
        invoice = self.client.add_invoice(1000, "Test payment")

        # Send payment
        payment = self.client.send_payment(invoice.payment_request)

        self.assertIsInstance(payment, Payment)
        self.assertEqual(payment.value, 1000)
        self.assertEqual(payment.status, "complete")
        self.assertIsNotNone(payment.payment_preimage)

    def test_list_payments(self):
        """Test listing payments"""
        # Create and pay invoice
        invoice = self.client.add_invoice(1000, "Test payment list")
        self.client.send_payment(invoice.payment_request)

        # List payments
        payments = self.client.list_payments()
        self.assertGreaterEqual(len(payments), 1)

    def test_settle_invoice(self):
        """Test settling an invoice"""
        # Create invoice
        invoice = self.client.add_invoice(1000, "Test settle")
        payment_hash = invoice.payment_hash

        # Get preimage
        invoice_data = self.client._invoices_db[payment_hash]
        preimage = invoice_data['preimage']

        # Settle invoice
        result = self.client.settle_invoice(payment_hash, preimage)

        self.assertTrue(result)
        self.assertTrue(self.client._invoices_db[payment_hash]['settled'])

    def test_list_channels(self):
        """Test listing Lightning channels"""
        channels = self.client.list_channels()

        self.assertIsInstance(channels, list)
        # Should be empty in mock implementation

    def test_get_info(self):
        """Test getting LND node info"""
        info = self.client.get_info()

        self.assertIsInstance(info, dict)
        self.assertIn('version', info)
        self.assertIn('identity_pubkey', info)
        self.assertIn('alias', info)
        self.assertTrue(info['synced_to_chain'])


class TestLightningManager(unittest.TestCase):
    """Test Lightning manager functionality"""

    def setUp(self):
        """Set up test fixtures"""
        from grpc_clients.grpc_client import ConnectionConfig, ServiceType

        # Create mock LND client
        self.config = ConnectionConfig(ServiceType.LND, "localhost", 10009)
        self.lnd_client = LndClient(self.config)
        self.manager = LightningManager(self.lnd_client)

        # Setup test database
        self.engine = create_engine('sqlite:///:memory:')
        from models import Base
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        """Clean up test fixtures"""
        self.engine.dispose()

    def test_manager_initialization(self):
        """Test Lightning manager initialization"""
        self.assertIsNotNone(self.manager)
        self.assertEqual(self.manager.lnd_client, self.lnd_client)

    def test_create_lightning_lift_success(self):
        """Test successful Lightning lift creation"""
        session = self.Session()

        # Create asset balance for user
        asset_balance = AssetBalance(
            user_pubkey="test_user_pubkey",
            asset_id="gbtc",
            balance=50000
        )
        session.add(asset_balance)
        session.commit()

        request = LightningLiftRequest(
            user_pubkey="test_user_pubkey",
            asset_id="gbtc",
            amount_sats=10000,
            memo="Test lift"
        )

        result = self.manager.create_lightning_lift(request)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.operation_id)
        self.assertIsNotNone(result.payment_hash)
        self.assertIsNotNone(result.bolt11_invoice)

        # Verify invoice was created in database
        db_invoice = session.query(LightningInvoice).filter(
            LightningInvoice.payment_hash == result.payment_hash
        ).first()
        self.assertIsNotNone(db_invoice)
        self.assertEqual(db_invoice.amount_sats, 10000)
        self.assertEqual(db_invoice.invoice_type, "lift")

        session.close()

    def test_create_lightning_lift_insufficient_balance(self):
        """Test Lightning lift with insufficient balance"""
        session = self.Session()

        # Create asset balance with insufficient funds
        asset_balance = AssetBalance(
            user_pubkey="test_user_pubkey",
            asset_id="gbtc",
            balance=5000  # Less than requested amount
        )
        session.add(asset_balance)
        session.commit()

        request = LightningLiftRequest(
            user_pubkey="test_user_pubkey",
            asset_id="gbtc",
            amount_sats=10000,  # More than available
            memo="Test lift"
        )

        result = self.manager.create_lightning_lift(request)

        self.assertFalse(result.success)
        self.assertIn("Insufficient asset balance", result.error)

        session.close()

    def test_process_lightning_land_success(self):
        """Test successful Lightning land processing"""
        session = self.Session()

        # Create asset balance for user
        asset_balance = AssetBalance(
            user_pubkey="test_user_pubkey",
            asset_id="gbtc",
            balance=50000
        )
        session.add(asset_balance)
        session.commit()

        # Create invoice for land
        invoice = self.lnd_client.add_invoice(10000, "Test land")

        request = LightningLandRequest(
            user_pubkey="test_user_pubkey",
            asset_id="gbtc",
            amount_sats=10000,
            lightning_invoice=invoice.payment_request
        )

        result = self.manager.process_lightning_land(request)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.operation_id)
        self.assertEqual(result.payment_hash, invoice.payment_hash)

        # Verify invoice was created in database
        db_invoice = session.query(LightningInvoice).filter(
            LightningInvoice.payment_hash == result.payment_hash
        ).first()
        self.assertIsNotNone(db_invoice)
        self.assertEqual(db_invoice.amount_sats, 10000)
        self.assertEqual(db_invoice.invoice_type, "land")

        session.close()

    def test_pay_lightning_invoice_success(self):
        """Test successful Lightning invoice payment"""
        session = self.Session()

        # Create invoice in database
        lnd_invoice = self.lnd_client.add_invoice(10000, "Test payment")

        db_invoice = LightningInvoice(
            payment_hash=lnd_invoice.payment_hash,
            bolt11_invoice=lnd_invoice.payment_request,
            session_id=None,
            amount_sats=10000,
            asset_id="gbtc",
            status="pending_payment",
            invoice_type="land",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1)
        )
        session.add(db_invoice)
        session.commit()

        result = self.manager.pay_lightning_invoice(lnd_invoice.payment_hash)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.operation_id)
        self.assertEqual(result.payment_hash, lnd_invoice.payment_hash)

        # Verify invoice status was updated
        session.refresh(db_invoice)
        self.assertEqual(db_invoice.status, "paid")
        self.assertIsNotNone(db_invoice.paid_at)

        session.close()

    def test_check_invoice_status(self):
        """Test checking invoice status"""
        session = self.Session()

        # Create invoice in database
        lnd_invoice = self.lnd_client.add_invoice(10000, "Test status")

        db_invoice = LightningInvoice(
            payment_hash=lnd_invoice.payment_hash,
            bolt11_invoice=lnd_invoice.payment_request,
            session_id=None,
            amount_sats=10000,
            asset_id="gbtc",
            status="pending",
            invoice_type="lift",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1)
        )
        session.add(db_invoice)
        session.commit()

        status = self.manager.check_invoice_status(lnd_invoice.payment_hash)

        self.assertNotIn('error', status)
        self.assertEqual(status['payment_hash'], lnd_invoice.payment_hash)
        self.assertEqual(status['status'], 'pending')

        session.close()

    def test_get_lightning_balances(self):
        """Test getting Lightning balances"""
        balances = self.manager.get_lightning_balances()

        self.assertNotIn('error', balances)
        self.assertIn('lightning', balances)
        self.assertIn('onchain', balances)
        self.assertIn('total_wallet_balance', balances)

    def test_estimate_lightning_fees(self):
        """Test Lightning fee estimation"""
        amount_sats = 10000
        fees = self.manager.estimate_lightning_fees(amount_sats)

        self.assertNotIn('error', fees)
        self.assertEqual(fees['amount_sats'], amount_sats)
        self.assertGreater(fees['total_fee'], 0)
        self.assertGreater(fees['total_amount'], amount_sats)

    def test_expire_pending_invoices(self):
        """Test expiring pending invoices"""
        session = self.Session()

        # Create expired invoice
        lnd_invoice = self.lnd_client.add_invoice(10000, "Test expired")

        db_invoice = LightningInvoice(
            payment_hash=lnd_invoice.payment_hash,
            bolt11_invoice=lnd_invoice.payment_request,
            session_id=None,
            amount_sats=10000,
            asset_id="gbtc",
            status="pending",
            invoice_type="lift",
            created_at=datetime.now() - timedelta(hours=2),
            expires_at=datetime.now() - timedelta(hours=1)  # Already expired
        )
        session.add(db_invoice)
        session.commit()

        expired_count = self.manager.expire_pending_invoices()

        self.assertGreater(expired_count, 0)

        # Verify invoice was marked as expired
        session.refresh(db_invoice)
        self.assertEqual(db_invoice.status, "expired")

        session.close()


class TestLightningMonitor(unittest.TestCase):
    """Test Lightning monitor functionality"""

    def setUp(self):
        """Set up test fixtures"""
        from grpc_clients.grpc_client import ConnectionConfig, ServiceType

        self.config = ConnectionConfig(ServiceType.LND, "localhost", 10009)
        self.lnd_client = LndClient(self.config)
        self.manager = LightningManager(self.lnd_client)
        self.monitor = LightningMonitor(self.manager)

    def test_monitor_initialization(self):
        """Test Lightning monitor initialization"""
        self.assertIsNotNone(self.monitor)
        self.assertEqual(self.monitor.lightning_manager, self.manager)
        self.assertFalse(self.monitor.is_running)
        self.assertEqual(self.monitor.check_interval, 5)

    def test_health_check(self):
        """Test monitor health check"""
        health = self.monitor.health_check()

        self.assertIn('is_running', health)
        self.assertIn('check_interval', health)
        self.assertIn('event_handlers_count', health)
        self.assertFalse(health['is_running'])

    def test_get_lightning_statistics(self):
        """Test getting Lightning statistics"""
        stats = self.monitor.get_lightning_statistics()

        self.assertIn('time_range_hours', stats)
        self.assertIn('total_invoices', stats)
        self.assertIn('paid_invoices', stats)
        self.assertIn('payment_rate', stats)
        self.assertIsInstance(stats['total_invoices'], int)

    def test_event_handlers(self):
        """Test event handler management"""
        def test_handler(event):
            pass

        # Add handler
        self.monitor.add_event_handler('test_event', test_handler)
        self.assertIn('test_event', self.monitor.event_handlers)
        self.assertIn(test_handler, self.monitor.event_handlers['test_event'])

        # Remove handler
        self.monitor.remove_event_handler('test_event', test_handler)
        self.assertNotIn(test_handler, self.monitor.event_handlers.get('test_event', []))


class TestLightningErrorHandling(unittest.TestCase):
    """Test Lightning error handling and recovery"""

    def setUp(self):
        """Set up test fixtures"""
        self.error_handler = LightningErrorHandler()

    def test_error_classification_network(self):
        """Test network error classification"""
        error = Exception("Network connection failed")
        lightning_error = self.error_handler._classify_error(error)

        self.assertEqual(lightning_error.error_type, LightningErrorType.NETWORK_ERROR)
        self.assertTrue(lightning_error.recoverable)

    def test_error_classification_insufficient_balance(self):
        """Test insufficient balance error classification"""
        error = Exception("Insufficient balance")
        lightning_error = self.error_handler._classify_error(error)

        self.assertEqual(lightning_error.error_type, LightningErrorType.INSUFFICIENT_BALANCE)
        self.assertFalse(lightning_error.recoverable)

    def test_error_classification_timeout(self):
        """Test timeout error classification"""
        error = Exception("Operation timeout")
        lightning_error = self.error_handler._classify_error(error)

        self.assertEqual(lightning_error.error_type, LightningErrorType.TIMEOUT_ERROR)
        self.assertTrue(lightning_error.recoverable)

    def test_should_retry_logic(self):
        """Test retry logic"""
        # Test recoverable error with low retry count
        error = LightningError(
            error_type=LightningErrorType.NETWORK_ERROR,
            message="Test error",
            recoverable=True,
            retry_count=1,
            max_retries=3
        )
        self.assertTrue(self.error_handler.should_retry(error))

        # Test non-recoverable error
        error.recoverable = False
        self.assertFalse(self.error_handler.should_retry(error))

        # Test max retries reached
        error.recoverable = True
        error.retry_count = 3
        error.max_retries = 3
        self.assertFalse(self.error_handler.should_retry(error))

    def test_retry_delay_calculation(self):
        """Test retry delay with exponential backoff"""
        error = LightningError(
            error_type=LightningErrorType.NETWORK_ERROR,
            message="Test error",
            retry_count=2
        )

        delay = self.error_handler.get_retry_delay(error)
        self.assertGreaterEqual(delay, 0.1)  # Should be at least minimum delay with jitter
        self.assertLess(delay, 60.0)  # Should be less than max delay

    def test_circuit_breaker_activation(self):
        """Test circuit breaker activation"""
        # Create multiple errors of same type
        for i in range(6):  # More than threshold
            error = LightningError(
                error_type=LightningErrorType.NETWORK_ERROR,
                message=f"Test error {i}"
            )
            self.error_handler._record_error(error)
            self.error_handler._check_circuit_breaker(error)

        self.assertTrue(self.error_handler.circuit_breaker_active)
        self.assertIsNotNone(self.error_handler.circuit_breaker_until)

    def test_error_statistics(self):
        """Test error statistics"""
        # Add some errors
        error1 = LightningError(
            error_type=LightningErrorType.NETWORK_ERROR,
            message="Network error"
        )
        error2 = LightningError(
            error_type=LightningErrorType.PAYMENT_FAILED,
            message="Payment failed"
        )

        self.error_handler._record_error(error1)
        self.error_handler._record_error(error2)

        stats = self.error_handler.get_error_statistics()

        self.assertIn('total_errors_last_hour', stats)
        self.assertIn('error_counts_by_type', stats)
        self.assertGreaterEqual(stats['total_errors_last_hour'], 2)


class TestLightningAPI(unittest.TestCase):
    """Test Lightning API endpoints"""

    def setUp(self):
        """Set up test fixtures"""
        from app import app
        app.config['TESTING'] = True
        self.client = app.test_client()

        # Mock Lightning services
        from grpc_clients.grpc_client import ConnectionConfig, ServiceType
        config = ConnectionConfig(ServiceType.LND, "localhost", 10009)
        lnd_client = LndClient(config)

        from lightning_manager import LightningManager
        self.manager = LightningManager(lnd_client)

        # Set up global variables
        import app as app_module
        app_module.lightning_manager = self.manager

    def test_lightning_lift_endpoint(self):
        """Test Lightning lift API endpoint"""
        data = {
            'user_pubkey': 'test_user_pubkey',
            'asset_id': 'gbtc',
            'amount_sats': 10000,
            'memo': 'Test lift'
        }

        response = self.client.post('/lightning/lift',
                                   json=data,
                                   content_type='application/json')

        self.assertEqual(response.status_code, 200)
        result = json.loads(response.data)

        self.assertIn('success', result)
        self.assertIn('payment_hash', result)
        self.assertIn('bolt11_invoice', result)

    def test_lightning_land_endpoint(self):
        """Test Lightning land API endpoint"""
        # Create invoice first
        invoice = self.manager.lnd_client.add_invoice(10000, "Test land")

        data = {
            'user_pubkey': 'test_user_pubkey',
            'asset_id': 'gbtc',
            'amount_sats': 10000,
            'lightning_invoice': invoice.payment_request
        }

        response = self.client.post('/lightning/land',
                                   json=data,
                                   content_type='application/json')

        self.assertEqual(response.status_code, 200)
        result = json.loads(response.data)

        self.assertIn('success', result)
        self.assertIn('payment_hash', result)

    def test_invoice_status_endpoint(self):
        """Test invoice status API endpoint"""
        # Create invoice
        invoice = self.manager.lnd_client.add_invoice(10000, "Test status")

        response = self.client.get(f'/lightning/invoices/{invoice.payment_hash}')

        self.assertEqual(response.status_code, 200)
        result = json.loads(response.data)

        self.assertIn('invoice_status', result)
        self.assertEqual(result['invoice_status']['payment_hash'], invoice.payment_hash)

    def test_lightning_balances_endpoint(self):
        """Test Lightning balances API endpoint"""
        response = self.client.get('/lightning/balances')

        self.assertEqual(response.status_code, 200)
        result = json.loads(response.data)

        self.assertIn('lightning_balances', result)
        self.assertIn('lightning', result['lightning_balances'])
        self.assertIn('onchain', result['lightning_balances'])

    def test_fee_estimate_endpoint(self):
        """Test fee estimation API endpoint"""
        amount_sats = 10000
        response = self.client.get(f'/lightning/fees/estimate/{amount_sats}')

        self.assertEqual(response.status_code, 200)
        result = json.loads(response.data)

        self.assertIn('fee_estimate', result)
        self.assertEqual(result['fee_estimate']['amount_sats'], amount_sats)

    def test_lightning_channels_endpoint(self):
        """Test Lightning channels API endpoint"""
        response = self.client.get('/lightning/channels')

        self.assertEqual(response.status_code, 200)
        result = json.loads(response.data)

        self.assertIn('channels', result)
        self.assertIn('count', result)
        self.assertIsInstance(result['channels'], list)

    def test_lightning_statistics_endpoint(self):
        """Test Lightning statistics API endpoint"""
        response = self.client.get('/lightning/statistics')

        self.assertEqual(response.status_code, 200)
        result = json.loads(response.data)

        self.assertIn('lightning_statistics', result)
        self.assertIn('total_invoices', result['lightning_statistics'])

    def test_lightning_monitor_health_endpoint(self):
        """Test Lightning monitor health API endpoint"""
        response = self.client.get('/lightning/monitor/health')

        self.assertEqual(response.status_code, 200)
        result = json.loads(response.data)

        self.assertIn('monitor_health', result)
        self.assertIn('is_running', result['monitor_health'])

    def test_invalid_lightning_lift_request(self):
        """Test invalid Lightning lift request"""
        data = {
            'user_pubkey': 'test_user_pubkey',
            # Missing required fields
        }

        response = self.client.post('/lightning/lift',
                                   json=data,
                                   content_type='application/json')

        self.assertEqual(response.status_code, 400)
        result = json.loads(response.data)
        self.assertIn('error', result)

    def test_nonexistent_invoice_status(self):
        """Test getting status of nonexistent invoice"""
        response = self.client.get('/lightning/invoices/nonexistent_hash')

        self.assertEqual(response.status_code, 404)
        result = json.loads(response.data)
        self.assertIn('error', result)


@pytest.mark.unit
class TestLightningIntegrationUnit:
    """Unit tests for Lightning integration using pytest"""

    def test_lightning_operation_result_creation(self):
        """Test LightningOperationResult dataclass"""
        from lightning_manager import LightningOperationResult

        result = LightningOperationResult(
            success=True,
            operation_id="test_op",
            payment_hash="test_hash",
            details={"test": "data"}
        )

        assert result.success is True
        assert result.operation_id == "test_op"
        assert result.payment_hash == "test_hash"
        assert result.details == {"test": "data"}

    def test_lightning_lift_request_creation(self):
        """Test LightningLiftRequest dataclass"""
        request = LightningLiftRequest(
            user_pubkey="test_user",
            asset_id="gbtc",
            amount_sats=10000,
            memo="Test memo"
        )

        assert request.user_pubkey == "test_user"
        assert request.asset_id == "gbtc"
        assert request.amount_sats == 10000
        assert request.memo == "Test memo"

    def test_lightning_land_request_creation(self):
        """Test LightningLandRequest dataclass"""
        request = LightningLandRequest(
            user_pubkey="test_user",
            asset_id="gbtc",
            amount_sats=10000,
            lightning_invoice="lnbc1000n1p3k3m2pp5"
        )

        assert request.user_pubkey == "test_user"
        assert request.asset_id == "gbtc"
        assert request.amount_sats == 10000
        assert request.lightning_invoice == "lnbc1000n1p3k3m2pp5"

    @pytest.fixture
    def mock_lightning_manager(self):
        """Mock Lightning manager fixture"""
        from unittest.mock import Mock
        manager = Mock()
        manager.create_lightning_lift.return_value = Mock(success=True)
        manager.process_lightning_land.return_value = Mock(success=True)
        return manager

    def test_manager_fixture_usage(self, mock_lightning_manager):
        """Test using mock Lightning manager fixture"""
        result = mock_lightning_manager.create_lightning_lift(Mock())
        assert result.success is True


if __name__ == '__main__':
    unittest.main()
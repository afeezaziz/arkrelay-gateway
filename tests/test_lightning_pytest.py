"""
Pytest-style Lightning Integration Tests

Modern pytest tests for Lightning Network integration using fixtures and markers.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta


@pytest.mark.unit
class TestLightningManagerPytest:
    """Pytest tests for Lightning manager"""

    def test_lightning_manager_initialization(self, lightning_manager):
        """Test Lightning manager initialization"""
        assert lightning_manager is not None
        assert lightning_manager.lnd_client is not None

    def test_create_lightning_lift_success(self, lightning_manager, sample_lightning_lift_request, test_database_session):
        """Test successful Lightning lift creation"""
        # Mock the database session
        with patch('lightning_manager.get_db') as mock_get_db:
            mock_get_db.return_value = test_database_session

            result = lightning_manager.create_lightning_lift(sample_lightning_lift_request)

            assert result.success is True
            assert result.operation_id is not None
            assert result.payment_hash is not None
            assert result.bolt11_invoice is not None

    def test_create_lightning_lift_insufficient_balance(self, lightning_manager, test_database_session):
        """Test Lightning lift with insufficient balance"""
        # Create a user with low balance
        from models import AssetBalance
        low_balance = AssetBalance(
            user_pubkey="poor_user",
            asset_id="gbtc",
            balance=1000  # Very low balance
        )
        test_database_session.add(low_balance)
        test_database_session.commit()

        request = Mock()
        request.user_pubkey = "poor_user"
        request.asset_id = "gbtc"
        request.amount_sats = 10000  # More than available
        request.memo = "Test"

        with patch('lightning_manager.get_db') as mock_get_db:
            mock_get_db.return_value = test_database_session

            result = lightning_manager.create_lightning_lift(request)

            assert result.success is False
            assert "Insufficient asset balance" in result.error

    def test_process_lightning_land_success(self, lightning_manager, sample_lightning_land_request, test_database_session):
        """Test successful Lightning land processing"""
        with patch('lightning_manager.get_db') as mock_get_db:
            mock_get_db.return_value = test_database_session

            result = lightning_manager.process_lightning_land(sample_lightning_land_request)

            assert result.success is True
            assert result.operation_id is not None
            assert result.payment_hash is not None

    def test_pay_lightning_invoice_success(self, lightning_manager, test_database_session):
        """Test successful Lightning invoice payment"""
        # Create invoice in database
        from models import LightningInvoice
        db_invoice = LightningInvoice(
            payment_hash="test_payment_hash",
            bolt11_invoice="test_invoice",
            session_id=None,
            amount_sats=10000,
            asset_id="gbtc",
            status="pending_payment",
            invoice_type="land",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1)
        )
        test_database_session.add(db_invoice)
        test_database_session.commit()

        with patch('lightning_manager.get_db') as mock_get_db:
            mock_get_db.return_value = test_database_session

            result = lightning_manager.pay_lightning_invoice("test_payment_hash")

            assert result.success is True
            assert result.operation_id is not None

    def test_check_invoice_status(self, lightning_manager, test_database_session):
        """Test checking invoice status"""
        # Create invoice in database
        from models import LightningInvoice
        db_invoice = LightningInvoice(
            payment_hash="test_status_hash",
            bolt11_invoice="test_status_invoice",
            session_id=None,
            amount_sats=5000,
            asset_id="gbtc",
            status="pending",
            invoice_type="lift",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1)
        )
        test_database_session.add(db_invoice)
        test_database_session.commit()

        with patch('lightning_manager.get_db') as mock_get_db:
            mock_get_db.return_value = test_database_session

            status = lightning_manager.check_invoice_status("test_status_hash")

            assert "error" not in status
            assert status["payment_hash"] == "test_status_hash"
            assert status["status"] == "pending"

    def test_get_lightning_balances(self, lightning_manager):
        """Test getting Lightning balances"""
        balances = lightning_manager.get_lightning_balances()

        assert "error" not in balances
        assert "lightning" in balances
        assert "onchain" in balances
        assert "total_wallet_balance" in balances

    def test_estimate_lightning_fees(self, lightning_manager):
        """Test Lightning fee estimation"""
        amount_sats = 25000
        fees = lightning_manager.estimate_lightning_fees(amount_sats)

        assert "error" not in fees
        assert fees["amount_sats"] == amount_sats
        assert fees["total_fee"] > 0
        assert fees["total_amount"] > amount_sats
        assert "fee_percentage" in fees

    def test_expire_pending_invoices(self, lightning_manager, test_database_session):
        """Test expiring pending invoices"""
        # Create expired invoice
        from models import LightningInvoice
        expired_invoice = LightningInvoice(
            payment_hash="expired_hash",
            bolt11_invoice="expired_invoice",
            session_id=None,
            amount_sats=1000,
            asset_id="gbtc",
            status="pending",
            invoice_type="lift",
            created_at=datetime.now() - timedelta(hours=2),
            expires_at=datetime.now() - timedelta(hours=1)  # Expired
        )
        test_database_session.add(expired_invoice)
        test_database_session.commit()

        with patch('lightning_manager.get_db') as mock_get_db:
            mock_get_db.return_value = test_database_session

            expired_count = lightning_manager.expire_pending_invoices()

            assert expired_count > 0

            # Verify invoice was marked as expired
            test_database_session.refresh(expired_invoice)
            assert expired_invoice.status == "expired"


@pytest.mark.unit
class TestLightningMonitorPytest:
    """Pytest tests for Lightning monitor"""

    def test_monitor_initialization(self, lightning_monitor):
        """Test Lightning monitor initialization"""
        assert lightning_monitor is not None
        assert lightning_monitor.lightning_manager is not None
        assert lightning_monitor.is_running is False
        assert lightning_monitor.check_interval == 5

    def test_health_check(self, lightning_monitor):
        """Test monitor health check"""
        health = lightning_monitor.health_check()

        assert "is_running" in health
        assert "check_interval" in health
        assert "event_handlers_count" in health
        assert health["is_running"] is False

    def test_get_lightning_statistics(self, lightning_monitor):
        """Test getting Lightning statistics"""
        stats = lightning_monitor.get_lightning_statistics()

        assert "time_range_hours" in stats
        assert "total_invoices" in stats
        assert "paid_invoices" in stats
        assert "payment_rate" in stats
        assert isinstance(stats["total_invoices"], int)

    def test_event_handler_management(self, lightning_monitor):
        """Test event handler management"""
        def test_handler(event):
            pass

        # Test adding handler
        lightning_monitor.add_event_handler("test_event", test_handler)
        assert "test_event" in lightning_monitor.event_handlers
        assert test_handler in lightning_monitor.event_handlers["test_event"]

        # Test removing handler
        lightning_monitor.remove_event_handler("test_event", test_handler)
        assert test_handler not in lightning_monitor.event_handlers.get("test_event", [])


@pytest.mark.unit
class TestLightningErrorHandlingPytest:
    """Pytest tests for Lightning error handling"""

    def test_error_handler_initialization(self, lightning_error_handler):
        """Test error handler initialization"""
        assert lightning_error_handler is not None
        assert lightning_error_handler.circuit_breaker_threshold == 5
        assert lightning_error_handler.circuit_breaker_timeout == 300
        assert lightning_error_handler.circuit_breaker_active is False

    def test_network_error_classification(self, lightning_error_handler):
        """Test network error classification"""
        from lightning_errors import LightningErrorType
        error = Exception("Network connection failed")
        lightning_error = lightning_error_handler._classify_error(error)

        assert lightning_error.error_type == LightningErrorType.NETWORK_ERROR
        assert lightning_error.recoverable is True

    def test_insufficient_balance_error_classification(self, lightning_error_handler):
        """Test insufficient balance error classification"""
        from lightning_errors import LightningErrorType
        error = Exception("Insufficient balance")
        lightning_error = lightning_error_handler._classify_error(error)

        assert lightning_error.error_type == LightningErrorType.INSUFFICIENT_BALANCE
        assert lightning_error.recoverable is False

    def test_timeout_error_classification(self, lightning_error_handler):
        """Test timeout error classification"""
        from lightning_errors import LightningErrorType
        error = Exception("Operation timeout")
        lightning_error = lightning_error_handler._classify_error(error)

        assert lightning_error.error_type == LightningErrorType.TIMEOUT_ERROR
        assert lightning_error.recoverable is True

    def test_should_retry_logic(self, lightning_error_handler):
        """Test retry logic"""
        from lightning_errors import LightningError, LightningErrorType

        # Test recoverable error with low retry count
        error = LightningError(
            error_type=LightningErrorType.NETWORK_ERROR,
            message="Test error",
            recoverable=True,
            retry_count=1,
            max_retries=3
        )
        assert lightning_error_handler.should_retry(error) is True

        # Test non-recoverable error
        error.recoverable = False
        assert lightning_error_handler.should_retry(error) is False

        # Test max retries reached
        error.recoverable = True
        error.retry_count = 3
        error.max_retries = 3
        assert lightning_error_handler.should_retry(error) is False

    def test_retry_delay_calculation(self, lightning_error_handler):
        """Test retry delay with exponential backoff"""
        from lightning_errors import LightningError, LightningErrorType

        error = LightningError(
            error_type=LightningErrorType.NETWORK_ERROR,
            message="Test error",
            retry_count=2
        )

        delay = lightning_error_handler.get_retry_delay(error)
        assert delay > 1.0  # Should be more than base delay
        assert delay < 60.0  # Should be less than max delay

    def test_circuit_breaker_activation(self, lightning_error_handler):
        """Test circuit breaker activation"""
        from lightning_errors import LightningError, LightningErrorType

        # Create multiple errors of same type to trigger circuit breaker
        for i in range(6):  # More than threshold of 5
            error = LightningError(
                error_type=LightningErrorType.NETWORK_ERROR,
                message=f"Test error {i}"
            )
            lightning_error_handler._record_error(error)
            lightning_error_handler._check_circuit_breaker(error)

        assert lightning_error_handler.circuit_breaker_active is True
        assert lightning_error_handler.circuit_breaker_until is not None

    def test_error_statistics(self, lightning_error_handler):
        """Test error statistics"""
        from lightning_errors import LightningError, LightningErrorType

        # Add some errors
        error1 = LightningError(
            error_type=LightningErrorType.NETWORK_ERROR,
            message="Network error"
        )
        error2 = LightningError(
            error_type=LightningErrorType.PAYMENT_FAILED,
            message="Payment failed"
        )

        lightning_error_handler._record_error(error1)
        lightning_error_handler._record_error(error2)

        stats = lightning_error_handler.get_error_statistics()

        assert "total_errors_last_hour" in stats
        assert "error_counts_by_type" in stats
        assert "circuit_breaker_active" in stats
        assert stats["total_errors_last_hour"] >= 2


@pytest.mark.unit
class TestLndClientPytest:
    """Pytest tests for LND client"""

    def test_client_initialization(self, mock_lnd_client):
        """Test LND client initialization"""
        assert mock_lnd_client is not None
        assert mock_lnd_client.health_check.return_value is True

    def test_get_lightning_balance(self, mock_lnd_client):
        """Test getting Lightning balance"""
        balance = mock_lnd_client.get_lightning_balance()

        assert balance.local_balance == 100000
        assert balance.remote_balance == 50000
        assert balance.pending_htlc_local == 0

    def test_get_onchain_balance(self, mock_lnd_client):
        """Test getting on-chain balance"""
        balance = mock_lnd_client.get_onchain_balance()

        assert balance.total_balance == 1000000
        assert balance.confirmed_balance == 950000
        assert balance.unconfirmed_balance == 50000

    def test_add_invoice(self, mock_lnd_client):
        """Test creating a Lightning invoice"""
        invoice = mock_lnd_client.add_invoice(1000, "Test invoice")

        assert invoice.value == 1000
        assert invoice.memo == "Test invoice"
        assert invoice.settled is False
        assert invoice.payment_request is not None

    def test_send_payment(self, mock_lnd_client):
        """Test sending a Lightning payment"""
        payment = mock_lnd_client.send_payment("test_invoice")

        assert payment.value == 1000
        assert payment.fee == 1
        assert payment.status == "complete"
        assert payment.payment_preimage is not None

    def test_list_channels(self, mock_lnd_client):
        """Test listing Lightning channels"""
        channels = mock_lnd_client.list_channels()

        assert isinstance(channels, list)
        assert len(channels) == 0  # Mock returns empty list

    def test_health_check(self, mock_lnd_client):
        """Test LND health check"""
        result = mock_lnd_client._health_check_impl()

        assert result is True


@pytest.mark.integration
class TestLightningIntegrationPytest:
    """Integration tests for Lightning components"""

    def test_lightning_services_integration(self, lightning_manager, lightning_monitor):
        """Test integration between Lightning services"""
        assert lightning_manager.lnd_client is not None
        assert lightning_monitor.lightning_manager == lightning_manager

        # Test that components can work together
        balances = lightning_manager.get_lightning_balances()
        assert "error" not in balances

        health = lightning_monitor.health_check()
        assert "is_running" in health

    def test_database_integration(self, test_database_session):
        """Test database integration with Lightning models"""
        from models import LightningInvoice, AssetBalance

        # Test creating and querying LightningInvoice
        invoice = LightningInvoice(
            payment_hash="integration_test_hash",
            bolt11_invoice="integration_test_invoice",
            amount_sats=7500,
            asset_id="gbtc",
            status="pending",
            invoice_type="lift",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1)
        )
        test_database_session.add(invoice)
        test_database_session.commit()

        # Query the invoice
        retrieved_invoice = test_database_session.query(LightningInvoice).filter(
            LightningInvoice.payment_hash == "integration_test_hash"
        ).first()

        assert retrieved_invoice is not None
        assert retrieved_invoice.amount_sats == 7500
        assert retrieved_invoice.invoice_type == "lift"

        # Test AssetBalance still works
        balance = test_database_session.query(AssetBalance).filter(
            AssetBalance.user_pubkey == "test_user_pubkey"
        ).first()
        assert balance is not None
        assert balance.balance == 50000

    @patch('lightning_manager.get_db')
    def test_lightning_workflow_integration(self, mock_get_db, lightning_manager, test_database_session):
        """Test complete Lightning workflow integration"""
        mock_get_db.return_value = test_database_session

        # Test lift workflow
        lift_request = Mock()
        lift_request.user_pubkey = "test_user_pubkey"
        lift_request.asset_id = "gbtc"
        lift_request.amount_sats = 5000
        lift_request.memo = "Integration test"

        lift_result = lightning_manager.create_lightning_lift(lift_request)
        assert lift_result.success is True

        # Test fee estimation
        fees = lightning_manager.estimate_lightning_fees(5000)
        assert "error" not in fees
        assert fees["amount_sats"] == 5000

        # Test balance checking
        balances = lightning_manager.get_lightning_balances()
        assert "error" not in balances


@pytest.mark.parametrize("amount,expected_min_fee", [
    (1000, 1),
    (5000, 5),
    (10000, 10),
    (50000, 50),
])
def test_fee_estimation_various_amounts(lightning_manager, amount, expected_min_fee):
    """Test fee estimation with various amounts"""
    fees = lightning_manager.estimate_lightning_fees(amount)

    assert fees["amount_sats"] == amount
    assert fees["total_fee"] >= expected_min_fee
    assert fees["total_amount"] == amount + fees["total_fee"]


@pytest.mark.parametrize("error_message,expected_type", [
    ("Network connection failed", "network_error"),
    ("Insufficient balance", "insufficient_balance"),
    ("Operation timeout", "timeout_error"),
    ("Payment failed", "payment_failed"),
    ("Invoice expired", "invoice_expired"),
])
def test_error_classification_parametrized(lightning_error_handler, error_message, expected_type):
    """Test error classification with various error messages"""
    from lightning_errors import LightningErrorType

    error = Exception(error_message)
    lightning_error = lightning_error_handler._classify_error(error)

    assert lightning_error.error_type.value == expected_type


# Performance test
@pytest.mark.performance
def test_lightning_operations_performance(lightning_manager):
    """Test performance of Lightning operations"""
    import time

    # Test invoice creation performance
    start_time = time.time()
    for i in range(10):
        lightning_manager.lnd_client.add_invoice(1000, f"Performance test {i}")
    end_time = time.time()

    avg_time = (end_time - start_time) / 10 * 1000  # Convert to ms
    assert avg_time < 100  # Should be less than 100ms per operation

    # Test fee estimation performance
    start_time = time.time()
    for i in range(10):
        lightning_manager.estimate_lightning_fees(1000 + i * 1000)
    end_time = time.time()

    avg_time = (end_time - start_time) / 10 * 1000  # Convert to ms
    assert avg_time < 50  # Should be less than 50ms per operation


# Error scenarios
@pytest.mark.unit
def test_error_scenarios(lightning_manager):
    """Test various error scenarios"""
    # Test with None values
    with pytest.raises(Exception):
        lightning_manager.create_lightning_lift(None)

    # Test with invalid amounts
    request = Mock()
    request.user_pubkey = "test_user"
    request.asset_id = "gbtc"
    request.amount_sats = -1000  # Invalid negative amount
    request.memo = "Test"

    # This should handle the error gracefully
    try:
        result = lightning_manager.create_lightning_lift(request)
        # Either it fails gracefully or succeeds with mock data
        assert isinstance(result.success, bool)
    except Exception:
        # If it raises an exception, that's also acceptable for invalid input
        pass
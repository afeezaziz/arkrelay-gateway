"""
Test cases for core models module
"""

import pytest
import uuid
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import Mock, patch

from core.models import (
    Base, Asset, AssetBalance, Vtxo, SigningSession,
    SigningChallenge, Transaction, JobLog, SystemMetrics,
    Heartbeat, get_session
)


@pytest.fixture
def test_db():
    """Create test database"""
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


@pytest.fixture
def sample_asset():
    """Sample asset for testing"""
    return Asset(
        asset_id="gbtc",
        name="Bitcoin",
        ticker="BTC",
        decimal_places=8,
        total_supply=21000000,
        is_active=True
    )


@pytest.fixture
def sample_asset_balance():
    """Sample asset balance for testing"""
    return AssetBalance(
        user_pubkey="test_user_pubkey",
        asset_id="gbtc",
        balance=100000,
        last_updated=datetime.now()
    )


@pytest.fixture
def sample_vtxo():
    """Sample VTXO for testing"""
    return Vtxo(
        vtxo_id="test_vtxo_id",
        txid="test_tx_id",
        vout=0,
        amount_sats=50000,
        script_pubkey=b"test_script_pubkey_bytes",  # Required LargeBinary field
        asset_id="gbtc",
        user_pubkey="test_user_pubkey",
        status="available",
        expires_at=datetime.now() + timedelta(hours=1),
        spending_txid=None  # Explicitly set nullable field
    )


@pytest.fixture
def sample_signing_session():
    """Sample signing session for testing"""
    return SigningSession(
        session_id=str(uuid.uuid4()),
        user_pubkey="test_user_pubkey",
        session_type="p2p_transfer",
        status="initiated",
        intent_data={"type": "transfer", "amount": 10000},
        context="Test context",
        expires_at=datetime.now() + timedelta(minutes=10)
    )


@pytest.fixture
def sample_signing_challenge():
    """Sample signing challenge for testing"""
    return SigningChallenge(
        challenge_id=str(uuid.uuid4()),
        session_id="test_session_id",
        challenge_data=b"test_challenge_data",
        context="Test challenge context",
        expires_at=datetime.now() + timedelta(minutes=5)
    )


@pytest.fixture
def sample_transaction():
    """Sample transaction for testing"""
    return Transaction(
        txid="test_tx_id",
        session_id="test_session_id",
        tx_type="ark_tx",
        raw_tx="test_raw_tx",
        amount_sats=10000,
        fee_sats=100,
        status="pending"
    )


class TestAsset:
    """Test cases for Asset model"""

    def test_asset_creation(self, test_db, sample_asset):
        """Test asset creation"""
        test_db.add(sample_asset)
        test_db.commit()

        saved_asset = test_db.query(Asset).first()
        assert saved_asset.asset_id == "gbtc"
        assert saved_asset.name == "Bitcoin"
        assert saved_asset.is_active is True

    def test_asset_unique_constraint(self, test_db, sample_asset):
        """Test asset unique constraint"""
        test_db.add(sample_asset)
        test_db.commit()

        duplicate_asset = Asset(
            asset_id="gbtc",
            name="Bitcoin Duplicate",
            ticker="BTCD",
            decimal_places=8,
            total_supply=21000000
        )

        test_db.add(duplicate_asset)
        with pytest.raises(Exception):
            test_db.commit()


class TestAssetBalance:
    """Test cases for AssetBalance model"""

    def test_asset_balance_creation(self, test_db, sample_asset, sample_asset_balance):
        """Test asset balance creation"""
        test_db.add(sample_asset)
        test_db.add(sample_asset_balance)
        test_db.commit()

        saved_balance = test_db.query(AssetBalance).first()
        assert saved_balance.user_pubkey == "test_user_pubkey"
        assert saved_balance.asset_id == "gbtc"
        assert saved_balance.balance == 100000

    def test_asset_balance_foreign_key(self, test_db, sample_asset_balance):
        """Test asset balance foreign key constraint"""
        # Enable foreign key constraints for SQLite
        from sqlalchemy import text
        test_db.execute(text("PRAGMA foreign_keys = ON"))
        test_db.add(sample_asset_balance)

        with pytest.raises(Exception):
            test_db.commit()


class TestVtxo:
    """Test cases for VTXO model"""

    def test_vtxo_creation(self, test_db, sample_asset, sample_vtxo):
        """Test VTXO creation"""
        test_db.add(sample_asset)
        test_db.add(sample_vtxo)
        test_db.commit()

        saved_vtxo = test_db.query(Vtxo).first()
        assert saved_vtxo.txid == "test_tx_id"
        assert saved_vtxo.amount_sats == 50000
        assert saved_vtxo.status == "available"

    def test_vtxo_expiration_check(self, test_db, sample_asset, sample_vtxo):
        """Test VTXO expiration check"""
        sample_vtxo.expires_at = datetime.now() - timedelta(hours=1)
        test_db.add(sample_asset)
        test_db.add(sample_vtxo)
        test_db.commit()

        saved_vtxo = test_db.query(Vtxo).first()
        assert saved_vtxo.expires_at < datetime.now()


class TestSigningSession:
    """Test cases for SigningSession model"""

    def test_signing_session_creation(self, test_db, sample_signing_session):
        """Test signing session creation"""
        test_db.add(sample_signing_session)
        test_db.commit()

        saved_session = test_db.query(SigningSession).first()
        assert saved_session.status == "initiated"
        assert saved_session.user_pubkey == "test_user_pubkey"

    def test_signing_session_state_transitions(self, test_db, sample_signing_session):
        """Test signing session state transitions"""
        test_db.add(sample_signing_session)
        test_db.commit()

        session = test_db.query(SigningSession).first()
        session.status = "challenge_sent"
        test_db.commit()

        updated_session = test_db.query(SigningSession).first()
        assert updated_session.status == "challenge_sent"

    def test_signing_session_expiration(self, test_db, sample_signing_session):
        """Test signing session expiration"""
        sample_signing_session.expires_at = datetime.now() - timedelta(minutes=1)
        test_db.add(sample_signing_session)
        test_db.commit()

        session = test_db.query(SigningSession).first()
        assert session.expires_at < datetime.now()


class TestSigningChallenge:
    """Test cases for SigningChallenge model"""

    def test_signing_challenge_creation(self, test_db, sample_signing_session, sample_signing_challenge):
        """Test signing challenge creation"""
        test_db.add(sample_signing_session)
        test_db.add(sample_signing_challenge)
        test_db.commit()

        saved_challenge = test_db.query(SigningChallenge).first()
        assert saved_challenge.session_id == "test_session_id"
        assert saved_challenge.challenge_data == b"test_challenge_data"

    def test_signing_challenge_expiration(self, test_db, sample_signing_session, sample_signing_challenge):
        """Test signing challenge expiration"""
        sample_signing_challenge.expires_at = datetime.now() - timedelta(minutes=1)
        test_db.add(sample_signing_session)
        test_db.add(sample_signing_challenge)
        test_db.commit()

        challenge = test_db.query(SigningChallenge).first()
        assert challenge.expires_at < datetime.now()


class TestTransaction:
    """Test cases for Transaction model"""

    def test_transaction_creation(self, test_db, sample_asset, sample_signing_session, sample_transaction):
        """Test transaction creation"""
        test_db.add(sample_asset)
        test_db.add(sample_signing_session)
        test_db.add(sample_transaction)
        test_db.commit()

        saved_transaction = test_db.query(Transaction).first()
        assert saved_transaction.txid == "test_tx_id"
        assert saved_transaction.status == "pending"
        assert saved_transaction.amount_sats == 10000

    def test_transaction_status_update(self, test_db, sample_asset, sample_signing_session, sample_transaction):
        """Test transaction status update"""
        test_db.add(sample_asset)
        test_db.add(sample_signing_session)
        test_db.add(sample_transaction)
        test_db.commit()

        transaction = test_db.query(Transaction).first()
        transaction.status = "completed"
        test_db.commit()

        updated_transaction = test_db.query(Transaction).first()
        assert updated_transaction.status == "completed"


class TestJobLog:
    """Test cases for JobLog model"""

    def test_job_log_creation(self, test_db):
        """Test job log creation"""
        job_log = JobLog(
            job_id="test_job_id",
            job_type="vtxo_replenishment",
            status="running",
            message="Test job log entry"
        )

        test_db.add(job_log)
        test_db.commit()

        saved_job_log = test_db.query(JobLog).first()
        assert saved_job_log.job_id == "test_job_id"
        assert saved_job_log.status == "running"


class TestSystemMetrics:
    """Test cases for SystemMetrics model"""

    def test_system_metrics_creation(self, test_db):
        """Test system metrics creation"""
        metrics = SystemMetrics(
            cpu_percent=25.5,
            memory_percent=60.2,
            memory_available_mb=8192.0,
            disk_percent=45.8,
            disk_free_gb=256.0,
            timestamp=datetime.now()
        )

        test_db.add(metrics)
        test_db.commit()

        saved_metrics = test_db.query(SystemMetrics).first()
        assert saved_metrics.cpu_percent == 25.5
        assert saved_metrics.memory_percent == 60.2
        assert saved_metrics.memory_available_mb == 8192.0


class TestHeartbeat:
    """Test cases for Heartbeat model"""

    def test_heartbeat_creation(self, test_db):
        """Test heartbeat creation"""
        heartbeat = Heartbeat(
            service_name="test_service",
            is_alive=True,
            timestamp=datetime.now(),
            message="Service is healthy"
        )

        test_db.add(heartbeat)
        test_db.commit()

        saved_heartbeat = test_db.query(Heartbeat).first()
        assert saved_heartbeat.service_name == "test_service"
        assert saved_heartbeat.is_alive is True


class TestGetSession:
    """Test cases for get_session function"""

    def test_get_session_success(self):
        """Test successful session creation"""
        with patch('models.create_engine') as mock_engine:
            session = get_session()
            assert session is not None

    def test_get_session_failure(self):
        """Test session creation failure"""
        with patch('core.models.create_engine', side_effect=Exception("Connection failed")):
            with pytest.raises(Exception):
                get_session()


@pytest.mark.integration
class TestModelIntegration:
    """Integration tests for models"""

    def test_complete_transaction_flow(self, test_db):
        """Test complete transaction flow across multiple models"""
        # Create asset
        asset = Asset(
            asset_id="gbtc",
            name="Bitcoin",
            ticker="BTC",
            decimal_places=8,
            total_supply=21000000,
            is_active=True
        )
        test_db.add(asset)

        # Create asset balance
        balance = AssetBalance(
            user_pubkey="test_user_pubkey",
            asset_id="gbtc",
            balance=100000
        )
        test_db.add(balance)

        # Create signing session
        session = SigningSession(
            session_id=str(uuid.uuid4()),
            user_pubkey="test_user_pubkey",
            session_type="p2p_transfer",
            status="initiated",
            intent_data={"type": "transfer"},
            context="Test transfer",
            expires_at=datetime.now() + timedelta(minutes=10)
        )
        test_db.add(session)

        # Create transaction
        transaction = Transaction(
            txid="test_tx_id",
            session_id=session.session_id,
            tx_type="ark_tx",
            raw_tx="test_raw_tx",
            amount_sats=10000,
            fee_sats=100,
            status="pending"
        )
        test_db.add(transaction)

        # Create VTXO
        vtxo = Vtxo(
            vtxo_id="test_vtxo_id",
            txid="test_tx_id",
            vout=0,
            amount_sats=10000,
            script_pubkey=b"test_script_pubkey",
            asset_id="gbtc",
            user_pubkey="test_user_pubkey",
            status="available",
            expires_at=datetime.now() + timedelta(hours=1)
        )
        test_db.add(vtxo)

        test_db.commit()

        # Verify all data was saved correctly
        assert test_db.query(Asset).count() == 1
        assert test_db.query(AssetBalance).count() == 1
        assert test_db.query(SigningSession).count() == 1
        assert test_db.query(Transaction).count() == 1
        assert test_db.query(Vtxo).count() == 1

        # Verify relationships
        saved_transaction = test_db.query(Transaction).first()
        assert saved_transaction.session_id == session.session_id

        saved_vtxo = test_db.query(Vtxo).first()
        assert saved_vtxo.txid == transaction.txid
        assert saved_vtxo.user_pubkey == "test_user_pubkey"
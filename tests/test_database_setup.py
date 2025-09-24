"""
Test database setup utilities for consistent test database management
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import tempfile
import os as _os
from core.models import Base
import os


@pytest.fixture(scope="function")
def test_db_session():
    """Create an isolated in-memory DB session per test, shared across threads."""
    # Use a temporary file-based SQLite DB to allow multiple connections across threads safely
    fd, db_path = tempfile.mkstemp(suffix=".sqlite")
    _os.close(fd)
    engine = create_engine(f'sqlite:///{db_path}', echo=False, connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionLocal()
    # Attach the engine so other fixtures can create new sessions bound to the same DB
    setattr(session, "_engine", engine)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
        try:
            _os.remove(db_path)
        except Exception:
            pass


# Compatibility fixtures for imports in some tests (may not be used directly)
@pytest.fixture(scope="session")
def test_engine():
    """Provide a disposable engine for compatibility (not used by per-test session)."""
    engine = create_engine('sqlite:///:memory:', echo=False)
    return engine


@pytest.fixture(scope="session")
def test_tables(test_engine):
    """Create/drop tables on the compatibility engine (for importers)."""
    Base.metadata.create_all(test_engine)
    yield
    Base.metadata.drop_all(test_engine)


@pytest.fixture
def mock_db_session():
    """Mock database session for unit tests"""
    from unittest.mock import Mock
    mock_session = Mock()
    mock_session.commit.return_value = None
    mock_session.rollback.return_value = None
    mock_session.query.return_value = Mock()
    mock_session.add.return_value = None
    mock_session.delete.return_value = None
    mock_session.execute.return_value = Mock()
    mock_session.refresh.return_value = None
    mock_session.close.return_value = None
    return mock_session


def sample_asset_data(asset_id='BTC'):
    """Sample asset data for testing"""
    return {
        'asset_id': asset_id,
        'name': 'Bitcoin',
        'ticker': 'BTC',
        'asset_type': 'normal',
        'decimal_places': 8,
        'total_supply': 2100000000000000,
        'is_active': True,
        'asset_metadata': {'description': 'Bitcoin cryptocurrency'}
    }


def sample_balance_data():
    """Sample balance data for testing"""
    return {
        'user_pubkey': 'test_user_pubkey_1234567890abcdef1234567890abcdef12345678',
        'asset_id': 'BTC',
        'balance': 5000,
        'reserved_balance': 1000
    }


def sample_vtxo_data():
    """Sample VTXO data for testing"""
    return {
        'vtxo_id': 'test_vtxo_id',
        'txid': 'test_txid',
        'vout': 0,
        'amount_sats': 1000,
        'script_pubkey': b'test_script_pubkey',
        'asset_id': 'BTC',
        'user_pubkey': 'test_user_pubkey_1234567890abcdef1234567890abcdef12345678',
        'status': 'available',
        'expires_at': None  # Will be set in test
    }


def sample_signing_session_data():
    """Sample signing session data for testing"""
    return {
        'session_id': 'test_session_id',
        'user_pubkey': 'test_user_pubkey_1234567890abcdef1234567890abcdef12345678',
        'session_type': 'p2p_transfer',
        'status': 'initiated',
        'intent_data': {'type': 'transfer', 'amount': 1000},
        'context': 'Test transfer session',
        'expires_at': None  # Will be set in test
    }


def sample_signing_challenge_data():
    """Sample signing challenge data for testing"""
    return {
        'challenge_id': 'test_challenge_id',
        'session_id': 'test_session_id',
        'challenge_data': b'test_challenge_data',
        'context': 'Test challenge context',
        'expires_at': None  # Will be set in test
    }


def sample_transaction_data():
    """Sample transaction data for testing"""
    return {
        'txid': 'test_txid',
        'session_id': 'test_session_id',
        'tx_type': 'ark_tx',
        'raw_tx': 'test_raw_transaction_hex',
        'amount_sats': 1000,
        'fee_sats': 100,
        'status': 'pending'
    }


# Factory functions for creating test objects
def create_test_asset(session, asset_data=None):
    """Create a test asset in the database"""
    from datetime import datetime
    from core.models import Asset
    import uuid

    if asset_data is None:
        asset_data = sample_asset_data(f'TEST_{uuid.uuid4().hex[:8]}')

    # Check if asset already exists
    existing_asset = session.query(Asset).filter_by(asset_id=asset_data['asset_id']).first()
    if existing_asset:
        return existing_asset

    asset = Asset(
        asset_id=asset_data['asset_id'],
        name=asset_data['name'],
        ticker=asset_data['ticker'],
        asset_type=asset_data['asset_type'],
        decimal_places=asset_data['decimal_places'],
        total_supply=asset_data['total_supply'],
        is_active=asset_data['is_active'],
        asset_metadata=asset_data.get('asset_metadata', {}),
        created_at=datetime.utcnow()
    )

    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


def create_test_balance(session, balance_data=None):
    """Create a test asset balance in the database"""
    from datetime import datetime
    from core.models import AssetBalance

    if balance_data is None:
        balance_data = sample_balance_data()

    balance = AssetBalance(
        user_pubkey=balance_data['user_pubkey'],
        asset_id=balance_data['asset_id'],
        balance=balance_data['balance'],
        reserved_balance=balance_data['reserved_balance'],
        last_updated=datetime.utcnow()
    )

    session.add(balance)
    session.commit()
    session.refresh(balance)
    return balance


def create_test_vtxo(session, vtxo_data=None):
    """Create a test VTXO in the database"""
    from datetime import datetime, timedelta
    from core.models import Vtxo

    if vtxo_data is None:
        vtxo_data = sample_vtxo_data()

    if vtxo_data['expires_at'] is None:
        vtxo_data['expires_at'] = datetime.utcnow() + timedelta(hours=24)

    vtxo = Vtxo(
        vtxo_id=vtxo_data['vtxo_id'],
        txid=vtxo_data['txid'],
        vout=vtxo_data['vout'],
        amount_sats=vtxo_data['amount_sats'],
        script_pubkey=vtxo_data['script_pubkey'],
        asset_id=vtxo_data['asset_id'],
        user_pubkey=vtxo_data['user_pubkey'],
        status=vtxo_data['status'],
        expires_at=vtxo_data['expires_at'],
        created_at=datetime.utcnow()
    )

    session.add(vtxo)
    session.commit()
    session.refresh(vtxo)
    return vtxo


def create_test_signing_session(session, session_data=None):
    """Create a test signing session in the database"""
    from datetime import datetime, timedelta
    from core.models import SigningSession

    if session_data is None:
        session_data = sample_signing_session_data()

    if session_data['expires_at'] is None:
        session_data['expires_at'] = datetime.utcnow() + timedelta(minutes=30)

    signing_session = SigningSession(
        session_id=session_data['session_id'],
        user_pubkey=session_data['user_pubkey'],
        session_type=session_data['session_type'],
        status=session_data['status'],
        intent_data=session_data['intent_data'],
        context=session_data['context'],
        expires_at=session_data['expires_at'],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    session.add(signing_session)
    session.commit()
    session.refresh(signing_session)
    return signing_session


def create_test_signing_challenge(session, challenge_data=None):
    """Create a test signing challenge in the database"""
    from datetime import datetime, timedelta
    from core.models import SigningChallenge

    if challenge_data is None:
        challenge_data = sample_signing_challenge_data()

    if challenge_data['expires_at'] is None:
        challenge_data['expires_at'] = datetime.utcnow() + timedelta(minutes=10)

    challenge = SigningChallenge(
        challenge_id=challenge_data['challenge_id'],
        session_id=challenge_data['session_id'],
        challenge_data=challenge_data['challenge_data'],
        context=challenge_data['context'],
        expires_at=challenge_data['expires_at'],
        created_at=datetime.utcnow()
    )

    session.add(challenge)
    session.commit()
    session.refresh(challenge)
    return challenge


def create_test_transaction(session, transaction_data=None):
    """Create a test transaction in the database"""
    from datetime import datetime
    from core.models import Transaction

    if transaction_data is None:
        transaction_data = sample_transaction_data()

    transaction = Transaction(
        txid=transaction_data['txid'],
        session_id=transaction_data['session_id'],
        tx_type=transaction_data['tx_type'],
        raw_tx=transaction_data['raw_tx'],
        amount_sats=transaction_data['amount_sats'],
        fee_sats=transaction_data['fee_sats'],
        status=transaction_data['status'],
        created_at=datetime.utcnow()
    )

    session.add(transaction)
    session.commit()
    session.refresh(transaction)
    return transaction


# Patch get_session to use test database
@pytest.fixture(autouse=True)
def patch_get_session(test_db_session):
    """Patch get_session to always return the single per-test session.

    Also patch core.asset_manager.get_session alias so methods that imported it
    at module load use the same session. This avoids nested SAVEPOINT usage and
    ensures that the db_connection rollback cleans up state per test.
    """
    from unittest.mock import patch

    engine = getattr(test_db_session, "_engine", None)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False) if engine is not None else None

    def _new_session():
        # Return a new Session per call bound to the same per-test engine
        return SessionLocal() if SessionLocal else test_db_session

    with (
        patch('core.models.get_session', side_effect=_new_session),
        # Asset manager should use the shared per-test Session so object state is consistent across calls
        patch('core.asset_manager.get_session', new=lambda: test_db_session),
        patch('core.session_manager.get_session', side_effect=_new_session),
        patch('builtins.get_session', new=lambda: test_db_session),
        patch('tests.test_transaction_processor.test_engine', new=engine),
        patch('tests.test_transaction_processor.TestSession', new=lambda: test_db_session),
    ):
        yield


# Cleanup function
@pytest.fixture(autouse=True)
def cleanup_test_data():
    """No-op: per-test DB ensures isolation automatically."""
    yield
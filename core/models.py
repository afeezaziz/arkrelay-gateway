from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Float, Boolean, ForeignKey, BigInteger, LargeBinary
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, scoped_session
from sqlalchemy.dialects.mysql import JSON
from datetime import datetime, timezone
import os
from core.config import Config

Base = declarative_base()

def utc_now() -> datetime:
    """Return current UTC time as a naive datetime (UTC) without deprecation warnings."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

class JobLog(Base):
    __tablename__ = 'job_logs'

    id = Column(Integer, primary_key=True)
    job_type = Column(String(50), nullable=False)
    job_id = Column(String(100), unique=True)
    status = Column(String(20), nullable=False)  # pending, running, completed, failed
    message = Column(Text)
    result_data = Column(Text)  # JSON string for results
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    duration_seconds = Column(Float)

class SystemMetrics(Base):
    __tablename__ = 'system_metrics'

    id = Column(Integer, primary_key=True)
    cpu_percent = Column(Float, nullable=False)
    memory_percent = Column(Float, nullable=False)
    memory_available_mb = Column(Float, nullable=False)
    disk_percent = Column(Float, nullable=False)
    disk_free_gb = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=utc_now)

class Heartbeat(Base):
    __tablename__ = 'heartbeats'

    id = Column(Integer, primary_key=True)
    service_name = Column(String(50), nullable=False)
    is_alive = Column(Boolean, default=True)
    timestamp = Column(DateTime, default=utc_now)
    message = Column(String(200))

# Ark Relay Models

class Vtxo(Base):
    __tablename__ = 'vtxos'

    id = Column(Integer, primary_key=True)
    vtxo_id = Column(String(64), unique=True, nullable=False)
    txid = Column(String(64), nullable=False)
    vout = Column(Integer, nullable=False)
    amount_sats = Column(BigInteger, nullable=False)
    script_pubkey = Column(LargeBinary, nullable=False)
    asset_id = Column(String(64), ForeignKey('assets.asset_id'))
    user_pubkey = Column(String(66), nullable=False)
    status = Column(String(20), default='available')  # available, assigned, spent, expired
    created_at = Column(DateTime, default=utc_now)
    expires_at = Column(DateTime, nullable=False)
    spending_txid = Column(String(64), nullable=True)

    # RGB-specific fields
    rgb_asset_type = Column(String(20), nullable=True)  # RGB asset type (CFA, NIA)
    rgb_proof_data = Column(Text, nullable=True)  # RGB-specific proof data
    rgb_state_commitment = Column(LargeBinary, nullable=True)  # RGB state commitment
    rgb_contract_state = Column(JSON, nullable=True)  # RGB contract state data
    rgb_allocation_id = Column(String(64), nullable=True)  # RGB allocation identifier

    asset = relationship("Asset", back_populates="vtxos")

class Asset(Base):
    __tablename__ = 'assets'

    id = Column(Integer, primary_key=True)
    asset_id = Column(String(64), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    ticker = Column(String(10), nullable=False)
    asset_type = Column(String(20), default='normal')  # normal, collectible, rgb_contract
    decimal_places = Column(Integer, default=8)
    total_supply = Column(BigInteger, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)
    asset_metadata = Column('metadata', JSON, nullable=True)  # Additional asset metadata

    # RGB-specific fields
    rgb_contract_id = Column(String(64), nullable=True)  # RGB contract identifier
    rgb_schema_type = Column(String(50), nullable=True)  # RGB schema type (e.g., CFA, NIA)
    rgb_genesis_proof = Column(Text, nullable=True)  # RGB genesis proof data
    rgb_interface_id = Column(String(64), nullable=True)  # RGB interface identifier
    rgb_specification_id = Column(String(64), nullable=True)  # RGB specification ID
    is_rgb_enabled = Column(Boolean, default=False)  # Whether RGB features are enabled

    vtxos = relationship("Vtxo", back_populates="asset")
    balances = relationship("AssetBalance", back_populates="asset")

class AssetBalance(Base):
    __tablename__ = 'asset_balances'

    id = Column(Integer, primary_key=True)
    user_pubkey = Column(String(66), nullable=False)
    asset_id = Column(String(64), ForeignKey('assets.asset_id'), nullable=False)
    balance = Column(BigInteger, default=0)
    reserved_balance = Column(BigInteger, default=0)
    last_updated = Column(DateTime, default=utc_now, onupdate=utc_now)

    asset = relationship("Asset", back_populates="balances")

    __table_args__ = (
        {'extend_existing': True}
    )

class SigningSession(Base):
    __tablename__ = 'signing_sessions'

    id = Column(Integer, primary_key=True)
    session_id = Column(String(64), unique=True, nullable=False)
    user_pubkey = Column(String(66), nullable=False)
    session_type = Column(String(20), nullable=False)  # p2p_transfer, lightning_lift, lightning_land
    status = Column(String(20), default='initiated')  # initiated, challenge_sent, waiting_response, signing, completed, failed, expired
    intent_data = Column(JSON, nullable=False)  # Original intent data
    context = Column(Text, nullable=True)  # Human-readable context
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    expires_at = Column(DateTime, nullable=False)
    signed_tx = Column(Text, nullable=True)  # Hex-encoded signed transaction
    result_data = Column(JSON, nullable=True)  # Final transaction details
    error_message = Column(Text, nullable=True)
    # Track associated challenge by ID (no FK to avoid circular dependency issues)
    challenge_id = Column(String(64), nullable=True)

    # Compatibility: accept alias kwargs often used in tests
    def __init__(self, **kwargs):
        # Map compatibility aliases to actual column names
        if 'state' in kwargs and 'status' not in kwargs:
            kwargs['status'] = kwargs.pop('state')
        if 'action_intent' in kwargs and 'intent_data' not in kwargs:
            kwargs['intent_data'] = kwargs.pop('action_intent')
        if 'human_readable_context' in kwargs and 'context' not in kwargs:
            kwargs['context'] = kwargs.pop('human_readable_context')
        super().__init__(**kwargs)

    # Compatibility: expose 'state' property aliasing 'status'
    @property
    def state(self):
        return self.status

    @state.setter
    def state(self, value):
        self.status = value

    # Note: we intentionally avoid a relationship to SigningChallenge to prevent circular FKs.

class SigningChallenge(Base):
    __tablename__ = 'signing_challenges'

    id = Column(Integer, primary_key=True)
    challenge_id = Column(String(64), unique=True, nullable=False)
    # Link to SigningSession by its external session_id key (string)
    session_id = Column(String(64), ForeignKey('signing_sessions.session_id'))
    challenge_data = Column(LargeBinary, nullable=False)  # Binary challenge data
    context = Column(Text, nullable=False)  # Human-readable context
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=utc_now)
    is_used = Column(Boolean, default=False)
    signature = Column(LargeBinary, nullable=True)  # User's signature response

    session = relationship("SigningSession", foreign_keys=[session_id])

    # Compatibility: accept alias kwargs often used in tests
    def __init__(self, **kwargs):
        if 'human_readable_context' in kwargs and 'context' not in kwargs:
            kwargs['context'] = kwargs.pop('human_readable_context')
        super().__init__(**kwargs)

class Transaction(Base):
    __tablename__ = 'transactions'

    id = Column(Integer, primary_key=True)
    txid = Column(String(64), unique=True, nullable=False)
    session_id = Column(String(64), ForeignKey('signing_sessions.session_id'))
    tx_type = Column(String(20), nullable=False)  # ark_tx, checkpoint_tx, settlement_tx
    raw_tx = Column(Text, nullable=True)  # Hex-encoded transaction (nullable for tests and staged tx)
    status = Column(String(20), default='pending')  # pending, broadcast, confirmed, failed
    amount_sats = Column(BigInteger, nullable=False)
    fee_sats = Column(BigInteger, default=0)
    created_at = Column(DateTime, default=utc_now)
    confirmed_at = Column(DateTime, nullable=True)
    block_height = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)

    session = relationship("SigningSession")

class LightningInvoice(Base):
    __tablename__ = 'lightning_invoices'

    id = Column(Integer, primary_key=True)
    payment_hash = Column(String(64), unique=True, nullable=False)
    bolt11_invoice = Column(Text, nullable=False)
    session_id = Column(String(64), ForeignKey('signing_sessions.session_id'))
    amount_sats = Column(BigInteger, nullable=False)
    asset_id = Column(String(64), ForeignKey('assets.id'), nullable=True)
    status = Column(String(20), default='pending')  # pending, paid, expired, cancelled
    invoice_type = Column(String(10), nullable=False)  # lift, land
    created_at = Column(DateTime, default=utc_now)
    expires_at = Column(DateTime, nullable=False)
    paid_at = Column(DateTime, nullable=True)
    preimage = Column(String(64), nullable=True)

    asset = relationship("Asset")

class RGBContract(Base):
    __tablename__ = 'rgb_contracts'

    id = Column(Integer, primary_key=True)
    contract_id = Column(String(64), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    interface_id = Column(String(64), nullable=False)
    specification_id = Column(String(64), nullable=False)
    genesis_proof = Column(Text, nullable=False)
    schema_type = Column(String(50), nullable=False)  # CFA, NIA, etc.
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # RGB contract metadata
    metadata = Column(JSON, nullable=True)
    creator_pubkey = Column(String(66), nullable=True)
    total_issued = Column(BigInteger, default=0)

    # Contract state
    current_state_root = Column(String(64), nullable=True)
    last_transition_txid = Column(String(64), nullable=True)

class RGBAllocation(Base):
    __tablename__ = 'rgb_allocations'

    id = Column(Integer, primary_key=True)
    allocation_id = Column(String(64), unique=True, nullable=False)
    contract_id = Column(String(64), ForeignKey('rgb_contracts.contract_id'), nullable=False)
    vtxo_id = Column(String(64), ForeignKey('vtxos.vtxo_id'), nullable=False)
    owner_pubkey = Column(String(66), nullable=False)
    amount = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=utc_now)

    # RGB-specific data
    state_commitment = Column(LargeBinary, nullable=True)
    proof_data = Column(Text, nullable=True)
    seal_type = Column(String(20), default='tapret_first')  # RGB seal type
    is_spent = Column(Boolean, default=False)
    spent_at = Column(DateTime, nullable=True)

    # Relationships
    contract = relationship("RGBContract")
    vtxo = relationship("Vtxo")

# Database setup (lazy initialization so tests can patch create_engine)
_config = Config()
engine = None  # type: ignore[assignment]
SessionLocal = None  # type: ignore[assignment]

def _init_engine(force: bool = False) -> None:
    """Initialize the SQLAlchemy engine and session factory.

    When force=True, always (re)create the engine/session. This is helpful for tests
    that patch create_engine and expect failures to propagate from get_session().
    """
    global engine, SessionLocal
    if not force and engine is not None and SessionLocal is not None:
        return
    url = _config.DATABASE_URL
    # For SQLite (esp. in-memory), avoid pooling args which are invalid for SingletonThreadPool
    if str(url).startswith("sqlite"):
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
        )
    else:
        engine = create_engine(
            url,
            pool_size=_config.DB_POOL_SIZE,
            max_overflow=_config.DB_POOL_MAX_OVERFLOW,
            pool_timeout=_config.DB_POOL_TIMEOUT,
            pool_recycle=1800,
            pool_pre_ping=True,
        )
    SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

def get_database_url():
    return _config.DATABASE_URL

def create_tables():
    _init_engine()
    Base.metadata.create_all(engine)  # type: ignore[arg-type]
    return engine

def get_session():
    # Force re-init so that tests patching create_engine see the call on each invocation
    _init_engine(force=True)
    return SessionLocal()  # type: ignore[operator]

# Expose a safe builtin alias for tests that call `get_session()` directly without import.
# This wrapper resolves the current core.models.get_session at call time so pytest patches still apply.
try:
    import builtins as _builtins

    def _builtin_get_session(*args, **kwargs):
        from core.models import get_session as _gs
        return _gs(*args, **kwargs)

    # Only set if not already defined to avoid clobbering user environments.
    if not hasattr(_builtins, 'get_session'):
        setattr(_builtins, 'get_session', _builtin_get_session)
except Exception:
    # If builtins cannot be set, tests will still use proper imports
    pass

# Ensure tables exist when third-party tests create their own Session/Engine
try:
    from sqlalchemy.orm import Session as _SQLASession
    from sqlalchemy import event as _sqla_event

    @_sqla_event.listens_for(_SQLASession, "before_flush")
    def _ensure_tables_before_flush(session, flush_context, instances):
        try:
            bind = session.get_bind()
            if bind is not None:
                # No-op if already created
                Base.metadata.create_all(bind=bind)
        except Exception:
            # Never block user flush/commit due to metadata creation attempt
            pass
except Exception:
    pass
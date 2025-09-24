"""
Lightning Manager Implementation

This module provides high-level Lightning operations for the Ark Relay Gateway,
integrating with the LND client and database models.
"""

import logging
from typing import Optional, Dict, Any, List, Generator
from datetime import datetime, timedelta
from dataclasses import dataclass

from sqlalchemy.orm import Session
from core.models import LightningInvoice, AssetBalance, SigningSession, Transaction, get_session
from grpc_clients.lnd_client import LndClient, LightningInvoice as LndLightningInvoice, Payment
from core.lightning_errors import lightning_error_handler, lightning_payment_recovery, lightning_invoice_recovery, LightningError, LightningErrorType

logger = logging.getLogger(__name__)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session (generator style) for easy patching in tests."""
    db = get_session()
    try:
        yield db
    finally:
        db.close()


@dataclass
class LightningLiftRequest:
    """Lightning lift (on-ramp) request"""
    user_pubkey: str
    asset_id: str
    amount_sats: int
    memo: str = ""


@dataclass
class LightningLandRequest:
    """Lightning land (off-ramp) request"""
    user_pubkey: str
    asset_id: str
    amount_sats: int
    lightning_invoice: str


@dataclass
class LightningOperationResult:
    """Result of Lightning operation"""
    success: bool
    operation_id: str
    payment_hash: Optional[str] = None
    bolt11_invoice: Optional[str] = None
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class LightningManager:
    """High-level Lightning operations manager"""

    def __init__(self, lnd_client: LndClient):
        self.lnd_client = lnd_client

    def create_lightning_lift(self, request: LightningLiftRequest) -> LightningOperationResult:
        """
        Create a Lightning lift (on-ramp) operation
        User pays Lightning invoice to receive VTXOs
        """
        try:
            db = next(get_db())

            # Check if user has sufficient asset balance for the lift
            asset_balance = db.query(AssetBalance).filter(
                AssetBalance.user_pubkey == request.user_pubkey,
                AssetBalance.asset_id == request.asset_id
            ).first()

            if not asset_balance or asset_balance.balance < request.amount_sats:
                error = LightningError(
                    error_type=LightningErrorType.INSUFFICIENT_BALANCE,
                    message=f"Insufficient asset balance for user {request.user_pubkey}",
                    recoverable=False
                )
                lightning_error_handler._record_error(error)
                return LightningOperationResult(
                    success=False,
                    operation_id="",
                    error="Insufficient asset balance"
                )

            # Create Lightning invoice with error recovery
            def _create_invoice():
                memo = f"Ark Relay Lift: {request.amount_sats} sats for {request.asset_id}"
                if request.memo:
                    memo += f" - {request.memo}"

                return self.lnd_client.add_invoice(
                    amount=request.amount_sats,
                    memo=memo,
                    expiry=3600  # 1 hour expiry
                )

            invoice_data = {
                "amount": request.amount_sats,
                "memo": f"Ark Relay Lift: {request.amount_sats} sats for {request.asset_id}",
                "expiry": 3600
            }

            try:
                lnd_invoice = lightning_invoice_recovery.recover_invoice_creation(invoice_data, _create_invoice)
            except Exception as e:
                error = lightning_error_handler.handle_error(e)
                return LightningOperationResult(
                    success=False,
                    operation_id="",
                    error=f"Failed to create invoice: {error.message}"
                )

            # Create database record
            db_invoice = LightningInvoice(
                payment_hash=lnd_invoice.payment_hash,
                bolt11_invoice=lnd_invoice.payment_request,
                session_id=None,  # Will be set when user initiates signing session
                amount_sats=request.amount_sats,
                asset_id=request.asset_id,
                status="pending",
                invoice_type="lift",
                created_at=datetime.now(),
                expires_at=datetime.now() + timedelta(seconds=3600)
            )
            db.add(db_invoice)
            db.commit()

            logger.info(f"Created Lightning lift invoice {lnd_invoice.payment_hash} for {request.amount_sats} sats")

            return LightningOperationResult(
                success=True,
                operation_id=db_invoice.id,
                payment_hash=lnd_invoice.payment_hash,
                bolt11_invoice=lnd_invoice.payment_request,
                details={
                    "user_pubkey": request.user_pubkey,
                    "asset_id": request.asset_id,
                    "amount_sats": request.amount_sats,
                    "expires_at": db_invoice.expires_at.isoformat()
                }
            )

        except Exception as e:
            error = lightning_error_handler.handle_error(e, {
                "user_pubkey": request.user_pubkey,
                "asset_id": request.asset_id,
                "amount_sats": request.amount_sats
            })
            return LightningOperationResult(
                success=False,
                operation_id="",
                error=f"Failed to create Lightning lift: {error.message}"
            )

    def process_lightning_land(self, request: LightningLandRequest) -> LightningOperationResult:
        """
        Process a Lightning land (off-ramp) operation
        User sends VTXOs to receive Lightning payment
        """
        try:
            db = next(get_db())

            # Check if user has sufficient asset balance
            asset_balance = db.query(AssetBalance).filter(
                AssetBalance.user_pubkey == request.user_pubkey,
                AssetBalance.asset_id == request.asset_id
            ).first()

            if not asset_balance or asset_balance.balance < request.amount_sats:
                return LightningOperationResult(
                    success=False,
                    operation_id="",
                    error="Insufficient asset balance"
                )

            # Parse and validate the Lightning invoice
            invoice = self.lnd_client.lookup_invoice_by_request(request.lightning_invoice)
            if not invoice:
                return LightningOperationResult(
                    success=False,
                    operation_id="",
                    error="Invalid Lightning invoice"
                )

            # Check if invoice amount matches requested amount
            if invoice.value != request.amount_sats:
                return LightningOperationResult(
                    success=False,
                    operation_id="",
                    error=f"Invoice amount {invoice.value} does not match requested amount {request.amount_sats}"
                )

            # Create database record
            db_invoice = LightningInvoice(
                payment_hash=invoice.payment_hash,
                bolt11_invoice=request.lightning_invoice,
                session_id=None,  # Will be set when user initiates signing session
                amount_sats=request.amount_sats,
                asset_id=request.asset_id,
                status="pending_payment",
                invoice_type="land",
                created_at=datetime.now(),
                expires_at=datetime.now() + timedelta(seconds=3600)
            )
            db.add(db_invoice)
            db.commit()

            logger.info(f"Created Lightning land invoice {invoice.payment_hash} for {request.amount_sats} sats")

            return LightningOperationResult(
                success=True,
                operation_id=db_invoice.id,
                payment_hash=invoice.payment_hash,
                bolt11_invoice=request.lightning_invoice,
                details={
                    "user_pubkey": request.user_pubkey,
                    "asset_id": request.asset_id,
                    "amount_sats": request.amount_sats,
                    "expires_at": db_invoice.expires_at.isoformat()
                }
            )

        except Exception as e:
            logger.error(f"Failed to process Lightning land: {e}")
            return LightningOperationResult(
                success=False,
                operation_id="",
                error=str(e)
            )

    def pay_lightning_invoice(self, payment_hash: str) -> LightningOperationResult:
        """
        Pay a Lightning invoice (for land operations)
        """
        try:
            db = next(get_db())

            # Get invoice from database
            db_invoice = db.query(LightningInvoice).filter(
                LightningInvoice.payment_hash == payment_hash
            ).first()

            if not db_invoice:
                return LightningOperationResult(
                    success=False,
                    operation_id="",
                    error="Invoice not found"
                )

            if db_invoice.status != "pending_payment":
                return LightningOperationResult(
                    success=False,
                    operation_id="",
                    error=f"Invoice status is {db_invoice.status}, not pending_payment"
                )

            # Pay the invoice using LND with error recovery
            def _send_payment():
                return self.lnd_client.send_payment(db_invoice.bolt11_invoice)

            try:
                payment = lightning_payment_recovery.recover_payment(payment_hash, _send_payment)
            except Exception as e:
                error = lightning_error_handler.handle_error(e, {"payment_hash": payment_hash})
                return LightningOperationResult(
                    success=False,
                    operation_id="",
                    error=f"Failed to pay invoice: {error.message}"
                )

            # Update invoice status
            db_invoice.status = "paid"
            db_invoice.paid_at = datetime.now()
            db_invoice.preimage = payment.payment_preimage
            db.commit()

            logger.info(f"Paid Lightning invoice {payment_hash} for {db_invoice.amount_sats} sats")

            return LightningOperationResult(
                success=True,
                operation_id=db_invoice.id,
                payment_hash=payment_hash,
                details={
                    "payment_preimage": payment.payment_preimage,
                    "fee": payment.fee,
                    "paid_at": db_invoice.paid_at.isoformat()
                }
            )

        except Exception as e:
            error = lightning_error_handler.handle_error(e, {"payment_hash": payment_hash})
            return LightningOperationResult(
                success=False,
                operation_id="",
                error=f"Failed to pay Lightning invoice: {error.message}"
            )

    def check_invoice_status(self, payment_hash: str) -> Dict[str, Any]:
        """
        Check the status of a Lightning invoice
        """
        try:
            db = next(get_db())

            # Get invoice from database
            db_invoice = db.query(LightningInvoice).filter(
                LightningInvoice.payment_hash == payment_hash
            ).first()

            if not db_invoice:
                return {"error": "Invoice not found"}

            # Check LND for real-time status
            lnd_invoice = self.lnd_client.lookup_invoice(payment_hash)

            # Update database status if LND shows different status
            if lnd_invoice and lnd_invoice.settled and db_invoice.status != "paid":
                db_invoice.status = "paid"
                db_invoice.paid_at = datetime.now()
                db.commit()

            return {
                "payment_hash": payment_hash,
                "status": db_invoice.status,
                "amount_sats": db_invoice.amount_sats,
                "asset_id": db_invoice.asset_id,
                "invoice_type": db_invoice.invoice_type,
                "created_at": db_invoice.created_at.isoformat(),
                "expires_at": db_invoice.expires_at.isoformat(),
                "paid_at": db_invoice.paid_at.isoformat() if db_invoice.paid_at else None,
                "bolt11_invoice": db_invoice.bolt11_invoice,
                "lnd_settled": lnd_invoice.settled if lnd_invoice else False
            }

        except Exception as e:
            logger.error(f"Failed to check invoice status {payment_hash}: {e}")
            return {"error": str(e)}

    def get_lightning_balances(self) -> Dict[str, Any]:
        """
        Get Lightning balance information
        """
        try:
            lightning_balance = self.lnd_client.get_lightning_balance()
            onchain_balance = self.lnd_client.get_onchain_balance()

            return {
                "lightning": {
                    "local_balance": lightning_balance.local_balance,
                    "remote_balance": lightning_balance.remote_balance,
                    "pending_open_local": lightning_balance.pending_open_local,
                    "pending_open_remote": lightning_balance.pending_open_remote
                },
                "onchain": {
                    "total_balance": onchain_balance.total_balance,
                    "confirmed_balance": onchain_balance.confirmed_balance,
                    "unconfirmed_balance": onchain_balance.unconfirmed_balance
                },
                "total_wallet_balance": lightning_balance.local_balance + onchain_balance.confirmed_balance
            }

        except Exception as e:
            logger.error(f"Failed to get Lightning balances: {e}")
            return {"error": str(e)}

    def get_user_lightning_activity(self, user_pubkey: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get user's Lightning activity history
        """
        try:
            db = next(get_db())

            # Get user's Lightning invoices
            invoices = db.query(LightningInvoice).filter(
                LightningInvoice.session_id.in_(
                    db.query(SigningSession.id).filter(
                        SigningSession.user_pubkey == user_pubkey
                    )
                )
            ).order_by(LightningInvoice.created_at.desc()).limit(limit).all()

            activity = []
            for invoice in invoices:
                activity.append({
                    "payment_hash": invoice.payment_hash,
                    "amount_sats": invoice.amount_sats,
                    "asset_id": invoice.asset_id,
                    "invoice_type": invoice.invoice_type,
                    "status": invoice.status,
                    "created_at": invoice.created_at.isoformat(),
                    "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
                    "bolt11_invoice": invoice.bolt11_invoice
                })

            return activity

        except Exception as e:
            logger.error(f"Failed to get user Lightning activity: {e}")
            return []

    def estimate_lightning_fees(self, amount_sats: int) -> Dict[str, Any]:
        """
        Estimate Lightning fees for a given amount
        """
        try:
            # Base fee calculation (simplified)
            base_fee = max(1, amount_sats // 1000)  # 0.1% base fee
            routing_fee = max(10, amount_sats // 5000)  # 0.02% routing fee

            total_fee = base_fee + routing_fee
            total_amount = amount_sats + total_fee

            return {
                "amount_sats": amount_sats,
                "base_fee": base_fee,
                "routing_fee": routing_fee,
                "total_fee": total_fee,
                "total_amount": total_amount,
                "fee_percentage": round((total_fee / amount_sats) * 100, 4)
            }

        except Exception as e:
            logger.error(f"Failed to estimate Lightning fees: {e}")
            return {"error": str(e)}

    def expire_pending_invoices(self) -> int:
        """
        Expire pending invoices that have passed their expiry time
        Returns number of expired invoices
        """
        try:
            db = next(get_db())

            # Find expired pending invoices
            expired_invoices = db.query(LightningInvoice).filter(
                LightningInvoice.status == "pending",
                LightningInvoice.expires_at < datetime.now()
            ).all()

            count = len(expired_invoices)
            for invoice in expired_invoices:
                invoice.status = "expired"
                logger.info(f"Expired invoice {invoice.payment_hash}")

            db.commit()
            return count

        except Exception as e:
            logger.error(f"Failed to expire pending invoices: {e}")
            return 0


# Add helper method to LndClient for lookup by payment request
def lookup_invoice_by_request(self, payment_request: str) -> Optional[LndLightningInvoice]:
    """Lookup invoice by payment request"""
    try:
        # Extract payment hash from payment request (simplified)
        # In production, would properly parse BOLT11 invoice
        for invoice_data in self._invoices_db.values():
            if invoice_data['payment_request'] == payment_request:
                return LndLightningInvoice(
                    payment_request=invoice_data['payment_request'],
                    r_hash=invoice_data['r_hash'],
                    payment_hash=invoice_data['payment_hash'],
                    value=invoice_data['value'],
                    settled=invoice_data['settled'],
                    creation_date=invoice_data['creation_date'],
                    expiry=invoice_data['expiry'],
                    memo=invoice_data['memo']
                )
        return None
    except Exception as e:
        logger.error(f"Failed to lookup invoice by request: {e}")
        return None


# Add the method to LndClient
LndClient.lookup_invoice_by_request = lookup_invoice_by_request
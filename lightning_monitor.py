"""
Lightning Monitor Implementation

This module provides real-time monitoring and status tracking for Lightning operations,
integrating with Redis pub/sub for event-driven updates.
"""

import logging
import json
import threading
import time
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from sqlalchemy.orm import Session
from models import LightningInvoice, AssetBalance, SystemMetrics, get_session
from lightning_manager import LightningManager

# Try to import redis_client, fallback to None if not available
try:
    from config import redis_client
except ImportError:
    redis_client = None

logger = logging.getLogger(__name__)


@dataclass
class LightningEvent:
    """Lightning event data structure"""
    event_type: str
    payment_hash: str
    timestamp: datetime
    data: Dict[str, Any] = field(default_factory=dict)


class LightningMonitor:
    """Real-time Lightning monitoring service"""

    def __init__(self, lightning_manager: LightningManager):
        self.lightning_manager = lightning_manager
        self.is_running = False
        self.monitor_thread = None
        self.event_handlers: Dict[str, List[Callable]] = {}
        self.last_check_time = datetime.now()
        self.check_interval = 5  # seconds

        # Redis pub/sub channels
        self.invoice_channel = "lightning:invoice_events"
        self.payment_channel = "lightning:payment_events"
        self.balance_channel = "lightning:balance_events"

    def start_monitoring(self):
        """Start the Lightning monitoring service"""
        if self.is_running:
            logger.warning("Lightning monitor is already running")
            return

        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

        logger.info("Lightning monitoring service started")

    def stop_monitoring(self):
        """Stop the Lightning monitoring service"""
        if not self.is_running:
            return

        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)

        logger.info("Lightning monitoring service stopped")

    def add_event_handler(self, event_type: str, handler: Callable):
        """Add an event handler for specific event types"""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)

    def remove_event_handler(self, event_type: str, handler: Callable):
        """Remove an event handler"""
        if event_type in self.event_handlers:
            try:
                self.event_handlers[event_type].remove(handler)
            except ValueError:
                pass

    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.is_running:
            try:
                self._check_invoice_statuses()
                self._check_lightning_balances()
                self._monitor_payments()
                self._cleanup_expired_invoices()

                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in Lightning monitor loop: {e}")
                time.sleep(self.check_interval)

    def _check_invoice_statuses(self):
        """Check for invoice status changes"""
        try:
            db = next(get_db())

            # Get pending invoices
            pending_invoices = db.query(LightningInvoice).filter(
                LightningInvoice.status.in_(["pending", "pending_payment"])
            ).all()

            for invoice in pending_invoices:
                try:
                    # Check LND for current status
                    lnd_invoice = self.lightning_manager.lnd_client.lookup_invoice(invoice.payment_hash)

                    if lnd_invoice and lnd_invoice.settled and invoice.status != "paid":
                        # Invoice was paid
                        self._handle_invoice_paid(invoice, lnd_invoice)

                except Exception as e:
                    logger.error(f"Error checking invoice {invoice.payment_hash}: {e}")

        except Exception as e:
            logger.error(f"Error checking invoice statuses: {e}")

    def _handle_invoice_paid(self, invoice: LightningInvoice, lnd_invoice):
        """Handle when an invoice is paid"""
        try:
            db = next(get_db())

            # Update invoice status
            invoice.status = "paid"
            invoice.paid_at = datetime.now()
            db.commit()

            # Create event
            event = LightningEvent(
                event_type="invoice_paid",
                payment_hash=invoice.payment_hash,
                timestamp=datetime.now(),
                data={
                    "amount_sats": invoice.amount_sats,
                    "asset_id": invoice.asset_id,
                    "invoice_type": invoice.invoice_type,
                    "user_pubkey": invoice.session.user_pubkey if invoice.session else None,
                    "paid_at": invoice.paid_at.isoformat()
                }
            )

            # Publish to Redis
            self._publish_event(self.invoice_channel, event)

            # Trigger event handlers
            self._trigger_event_handlers("invoice_paid", event)

            logger.info(f"Invoice paid event: {invoice.payment_hash} for {invoice.amount_sats} sats")

            # Update user balance for lift operations
            if invoice.invoice_type == "lift":
                self._update_user_balance_for_lift(invoice)

        except Exception as e:
            logger.error(f"Error handling invoice paid {invoice.payment_hash}: {e}")

    def _update_user_balance_for_lift(self, invoice: LightningInvoice):
        """Update user balance when lift invoice is paid"""
        try:
            db = next(get_db())

            if not invoice.session:
                logger.warning(f"No session found for invoice {invoice.payment_hash}")
                return

            user_pubkey = invoice.session.user_pubkey
            asset_id = invoice.asset_id
            amount = invoice.amount_sats

            # Check if user has asset balance, create if not
            asset_balance = db.query(AssetBalance).filter(
                AssetBalance.user_pubkey == user_pubkey,
                AssetBalance.asset_id == asset_id
            ).first()

            if asset_balance:
                asset_balance.balance += amount
            else:
                asset_balance = AssetBalance(
                    user_pubkey=user_pubkey,
                    asset_id=asset_id,
                    balance=amount
                )
                db.add(asset_balance)

            db.commit()

            logger.info(f"Updated user balance: {user_pubkey} +{amount} {asset_id}")

        except Exception as e:
            logger.error(f"Error updating user balance for lift: {e}")

    def _check_lightning_balances(self):
        """Check Lightning balance changes"""
        try:
            balances = self.lightning_manager.get_lightning_balances()

            if "error" not in balances:
                # Create balance event
                event = LightningEvent(
                    event_type="balance_update",
                    payment_hash="balance_update",
                    timestamp=datetime.now(),
                    data=balances
                )

                # Publish to Redis
                self._publish_event(self.balance_channel, event)

                # Store in system metrics
                self._store_balance_metrics(balances)

        except Exception as e:
            logger.error(f"Error checking Lightning balances: {e}")

    def _store_balance_metrics(self, balances: Dict[str, Any]):
        """Store balance metrics in database"""
        try:
            db = next(get_db())

            metric = SystemMetrics(
                metric_type="lightning_balance",
                metric_value=json.dumps(balances),
                timestamp=datetime.now()
            )
            db.add(metric)
            db.commit()

        except Exception as e:
            logger.error(f"Error storing balance metrics: {e}")

    def _monitor_payments(self):
        """Monitor Lightning payments"""
        try:
            # Get recent payments from LND
            payments = self.lightning_manager.lnd_client.list_payments()

            # Check for new payments
            for payment in payments:
                if payment.creation_time > self.last_check_time:
                    self._handle_new_payment(payment)

        except Exception as e:
            logger.error(f"Error monitoring payments: {e}")

    def _handle_new_payment(self, payment):
        """Handle new payment event"""
        try:
            event = LightningEvent(
                event_type="payment_sent",
                payment_hash=payment.payment_hash,
                timestamp=datetime.now(),
                data={
                    "value": payment.value,
                    "fee": payment.fee,
                    "status": payment.status,
                    "payment_preimage": payment.payment_preimage
                }
            )

            # Publish to Redis
            self._publish_event(self.payment_channel, event)

            # Trigger event handlers
            self._trigger_event_handlers("payment_sent", event)

            logger.info(f"Payment sent event: {payment.payment_hash} for {payment.value} sats")

        except Exception as e:
            logger.error(f"Error handling new payment {payment.payment_hash}: {e}")

    def _cleanup_expired_invoices(self):
        """Clean up expired invoices"""
        try:
            expired_count = self.lightning_manager.expire_pending_invoices()
            if expired_count > 0:
                logger.info(f"Cleaned up {expired_count} expired invoices")
        except Exception as e:
            logger.error(f"Error cleaning up expired invoices: {e}")

    def _publish_event(self, channel: str, event: LightningEvent):
        """Publish event to Redis channel"""
        try:
            if redis_client:
                event_data = {
                    "event_type": event.event_type,
                    "payment_hash": event.payment_hash,
                    "timestamp": event.timestamp.isoformat(),
                    "data": event.data
                }
                redis_client.publish(channel, json.dumps(event_data))
        except Exception as e:
            logger.error(f"Error publishing event to Redis: {e}")

    def _trigger_event_handlers(self, event_type: str, event: LightningEvent):
        """Trigger event handlers for specific event types"""
        if event_type in self.event_handlers:
            for handler in self.event_handlers[event_type]:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Error in event handler for {event_type}: {e}")

    def get_invoice_status_history(self, payment_hash: str, hours: int = 24) -> List[Dict[str, Any]]:
        """Get status history for an invoice"""
        try:
            # Get from Redis cache if available
            cache_key = f"invoice_history:{payment_hash}"
            cached_history = None

            if redis_client:
                cached_data = redis_client.get(cache_key)
                if cached_data:
                    cached_history = json.loads(cached_data)

            if cached_history:
                # Filter by time range
                cutoff_time = datetime.now() - timedelta(hours=hours)
                return [event for event in cached_history
                       if datetime.fromisoformat(event['timestamp']) > cutoff_time]

            # Return empty list if not cached
            return []

        except Exception as e:
            logger.error(f"Error getting invoice status history: {e}")
            return []

    def get_lightning_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """Get Lightning operation statistics"""
        try:
            db = next(get_db())
            cutoff_time = datetime.now() - timedelta(hours=hours)

            # Get invoice statistics
            total_invoices = db.query(LightningInvoice).filter(
                LightningInvoice.created_at >= cutoff_time
            ).count()

            paid_invoices = db.query(LightningInvoice).filter(
                LightningInvoice.created_at >= cutoff_time,
                LightningInvoice.status == "paid"
            ).count()

            lift_invoices = db.query(LightningInvoice).filter(
                LightningInvoice.created_at >= cutoff_time,
                LightningInvoice.invoice_type == "lift"
            ).count()

            land_invoices = db.query(LightningInvoice).filter(
                LightningInvoice.created_at >= cutoff_time,
                LightningInvoice.invoice_type == "land"
            ).count()

            # Calculate total volume
            total_volume = db.query(LightningInvoice).filter(
                LightningInvoice.created_at >= cutoff_time,
                LightningInvoice.status == "paid"
            ).with_entities(LightningInvoice.amount_sats).all()

            total_sats = sum(amount for amount, in total_volume)

            return {
                "time_range_hours": hours,
                "total_invoices": total_invoices,
                "paid_invoices": paid_invoices,
                "pending_invoices": total_invoices - paid_invoices,
                "lift_invoices": lift_invoices,
                "land_invoices": land_invoices,
                "total_volume_sats": total_sats,
                "payment_rate": round((paid_invoices / total_invoices * 100) if total_invoices > 0 else 0, 2)
            }

        except Exception as e:
            logger.error(f"Error getting Lightning statistics: {e}")
            return {"error": str(e)}

    def health_check(self) -> Dict[str, Any]:
        """Health check for the monitor service"""
        return {
            "is_running": self.is_running,
            "last_check_time": self.last_check_time.isoformat(),
            "check_interval": self.check_interval,
            "event_handlers_count": sum(len(handlers) for handlers in self.event_handlers.values()),
            "redis_connected": redis_client is not None,
            "lnd_connected": self.lightning_manager.lnd_client._health_check_impl()
        }
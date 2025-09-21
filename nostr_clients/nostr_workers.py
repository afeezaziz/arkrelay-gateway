import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from core.models import get_session, SigningSession, SigningChallenge, Transaction, AssetBalance, Asset
from core.config import Config
from .nostr_redis import get_redis_manager
from .nostr_client import get_nostr_client

logger = logging.getLogger(__name__)

class NostrWorker:
    def __init__(self):
        self.redis_manager = get_redis_manager()
        self.nostr_client = get_nostr_client()

    def process_action_intent(self, event_data: Dict[str, Any]):
        """Process an action intent from Redis queue"""
        try:
            session_id = event_data.get('session_id')
            user_pubkey = event_data.get('user_pubkey')
            session_type = event_data.get('session_type')
            intent_data = event_data.get('intent_data')

            logger.info(f"Processing action intent for session {session_id}")

            # Get session from database
            session = get_session()
            try:
                signing_session = session.query(SigningSession).filter_by(
                    session_id=session_id
                ).first()

                if not signing_session:
                    logger.error(f"Session {session_id} not found")
                    return

                # Update session status
                signing_session.status = 'processing'
                session.commit()

                # Process based on session type
                if session_type == 'p2p_transfer':
                    self._process_p2p_transfer(signing_session, intent_data)
                elif session_type == 'lightning_lift':
                    self._process_lightning_lift(signing_session, intent_data)
                elif session_type == 'lightning_land':
                    self._process_lightning_land(signing_session, intent_data)
                else:
                    logger.error(f"Unknown session type: {session_type}")
                    signing_session.status = 'failed'
                    signing_session.error_message = f"Unknown session type: {session_type}"

                session.commit()

            except Exception as e:
                logger.error(f"Error processing action intent for session {session_id}: {e}")
                session.rollback()

                # Update session status to failed
                signing_session = session.query(SigningSession).filter_by(
                    session_id=session_id
                ).first()
                if signing_session:
                    signing_session.status = 'failed'
                    signing_session.error_message = str(e)
                    session.commit()

            finally:
                session.close()

        except Exception as e:
            logger.error(f"Error in process_action_intent: {e}")

    def process_signing_response(self, event_data: Dict[str, Any]):
        """Process a signing response from Redis queue"""
        try:
            session_id = event_data.get('session_id')
            challenge_id = event_data.get('challenge_id')
            user_pubkey = event_data.get('user_pubkey')
            signature = event_data.get('signature')

            logger.info(f"Processing signing response for session {session_id}")

            # Get session from database
            session = get_session()
            try:
                signing_session = session.query(SigningSession).filter_by(
                    session_id=session_id
                ).first()

                if not signing_session:
                    logger.error(f"Session {session_id} not found")
                    return

                # Get challenge
                challenge = session.query(SigningChallenge).filter_by(
                    challenge_id=challenge_id
                ).first()

                if not challenge:
                    logger.error(f"Challenge {challenge_id} not found")
                    return

                # Verify signature (simplified for now)
                if not self._verify_signature(signing_session, challenge, signature):
                    logger.error(f"Signature verification failed for session {session_id}")
                    signing_session.status = 'failed'
                    signing_session.error_message = "Signature verification failed"
                    session.commit()
                    return

                # Process the signing based on session type
                if signing_session.session_type == 'p2p_transfer':
                    self._complete_p2p_transfer(signing_session)
                elif signing_session.session_type == 'lightning_lift':
                    self._complete_lightning_lift(signing_session)
                elif signing_session.session_type == 'lightning_land':
                    self._complete_lightning_land(signing_session)
                else:
                    logger.error(f"Unknown session type: {signing_session.session_type}")
                    signing_session.status = 'failed'
                    signing_session.error_message = f"Unknown session type: {signing_session.session_type}"

                session.commit()

                # Publish session status update
                self.nostr_client.publish_session_status(
                    session_id=session_id,
                    status=signing_session.status,
                    user_pubkey=user_pubkey
                )

            except Exception as e:
                logger.error(f"Error processing signing response for session {session_id}: {e}")
                session.rollback()

                # Update session status to failed
                signing_session = session.query(SigningSession).filter_by(
                    session_id=session_id
                ).first()
                if signing_session:
                    signing_session.status = 'failed'
                    signing_session.error_message = str(e)
                    session.commit()

            finally:
                session.close()

        except Exception as e:
            logger.error(f"Error in process_signing_response: {e}")

    def _process_p2p_transfer(self, signing_session: SigningSession, intent_data: Dict[str, Any]):
        """Process a P2P transfer"""
        try:
            recipient_pubkey = intent_data.get('recipient_pubkey')
            asset_id = intent_data.get('asset_id')
            amount = intent_data.get('amount')

            logger.info(f"Processing P2P transfer: {amount} {asset_id} to {recipient_pubkey}")

            # Check sender balance
            if not self._check_balance(signing_session.user_pubkey, asset_id, amount):
                raise ValueError("Insufficient balance")

            # Reserve balance
            if not self._reserve_balance(signing_session.user_pubkey, asset_id, amount):
                raise ValueError("Failed to reserve balance")

            # Update session status
            signing_session.status = 'awaiting_signature'
            logger.info(f"P2P transfer processed, awaiting signature")

        except Exception as e:
            logger.error(f"Error processing P2P transfer: {e}")
            raise

    def _process_lightning_lift(self, signing_session: SigningSession, intent_data: Dict[str, Any]):
        """Process a Lightning lift (asset to Lightning)"""
        try:
            asset_id = intent_data.get('asset_id')
            amount = intent_data.get('amount')
            invoice = intent_data.get('invoice')

            logger.info(f"Processing Lightning lift: {amount} {asset_id} to {invoice}")

            # Check user balance
            if not self._check_balance(signing_session.user_pubkey, asset_id, amount):
                raise ValueError("Insufficient balance")

            # Reserve balance
            if not self._reserve_balance(signing_session.user_pubkey, asset_id, amount):
                raise ValueError("Failed to reserve balance")

            # Validate invoice (simplified)
            if not self._validate_lightning_invoice(invoice):
                raise ValueError("Invalid Lightning invoice")

            # Update session status
            signing_session.status = 'awaiting_signature'
            logger.info(f"Lightning lift processed, awaiting signature")

        except Exception as e:
            logger.error(f"Error processing Lightning lift: {e}")
            raise

    def _process_lightning_land(self, signing_session: SigningSession, intent_data: Dict[str, Any]):
        """Process a Lightning land (Lightning to asset)"""
        try:
            asset_id = intent_data.get('asset_id')
            amount = intent_data.get('amount')
            invoice = intent_data.get('invoice')

            logger.info(f"Processing Lightning land: {invoice} to {amount} {asset_id}")

            # Validate invoice (simplified)
            if not self._validate_lightning_invoice(invoice):
                raise ValueError("Invalid Lightning invoice")

            # Update session status
            signing_session.status = 'awaiting_signature'
            logger.info(f"Lightning land processed, awaiting signature")

        except Exception as e:
            logger.error(f"Error processing Lightning land: {e}")
            raise

    def _complete_p2p_transfer(self, signing_session: SigningSession):
        """Complete a P2P transfer after signing"""
        try:
            intent_data = signing_session.intent_data
            recipient_pubkey = intent_data.get('recipient_pubkey')
            asset_id = intent_data.get('asset_id')
            amount = intent_data.get('amount')

            logger.info(f"Completing P2P transfer: {amount} {asset_id} to {recipient_pubkey}")

            # Transfer balance
            if not self._transfer_balance(
                signing_session.user_pubkey,
                recipient_pubkey,
                asset_id,
                amount
            ):
                raise ValueError("Balance transfer failed")

            # Create transaction record
            self._create_transaction_record(
                signing_session,
                'p2p_transfer',
                amount
            )

            # Update session status
            signing_session.status = 'completed'
            signing_session.result_data = {
                'transfer_completed': True,
                'recipient': recipient_pubkey,
                'asset_id': asset_id,
                'amount': amount
            }

            logger.info(f"P2P transfer completed successfully")

        except Exception as e:
            logger.error(f"Error completing P2P transfer: {e}")
            signing_session.status = 'failed'
            signing_session.error_message = str(e)
            raise

    def _complete_lightning_lift(self, signing_session: SigningSession):
        """Complete a Lightning lift after signing"""
        try:
            intent_data = signing_session.intent_data
            asset_id = intent_data.get('asset_id')
            amount = intent_data.get('amount')
            invoice = intent_data.get('invoice')

            logger.info(f"Completing Lightning lift: {amount} {asset_id} to {invoice}")

            # Deduct balance
            if not self._deduct_balance(signing_session.user_pubkey, asset_id, amount):
                raise ValueError("Balance deduction failed")

            # Pay Lightning invoice (placeholder)
            payment_result = self._pay_lightning_invoice(invoice)

            # Create transaction record
            self._create_transaction_record(
                signing_session,
                'lightning_lift',
                amount
            )

            # Update session status
            signing_session.status = 'completed'
            signing_session.result_data = {
                'lift_completed': True,
                'invoice': invoice,
                'asset_id': asset_id,
                'amount': amount,
                'payment_result': payment_result
            }

            logger.info(f"Lightning lift completed successfully")

        except Exception as e:
            logger.error(f"Error completing Lightning lift: {e}")
            signing_session.status = 'failed'
            signing_session.error_message = str(e)
            raise

    def _complete_lightning_land(self, signing_session: SigningSession):
        """Complete a Lightning land after signing"""
        try:
            intent_data = signing_session.intent_data
            asset_id = intent_data.get('asset_id')
            amount = intent_data.get('amount')
            invoice = intent_data.get('invoice')

            logger.info(f"Completing Lightning land: {invoice} to {amount} {asset_id}")

            # Add balance
            if not self._add_balance(signing_session.user_pubkey, asset_id, amount):
                raise ValueError("Balance addition failed")

            # Create transaction record
            self._create_transaction_record(
                signing_session,
                'lightning_land',
                amount
            )

            # Update session status
            signing_session.status = 'completed'
            signing_session.result_data = {
                'land_completed': True,
                'invoice': invoice,
                'asset_id': asset_id,
                'amount': amount
            }

            logger.info(f"Lightning land completed successfully")

        except Exception as e:
            logger.error(f"Error completing Lightning land: {e}")
            signing_session.status = 'failed'
            signing_session.error_message = str(e)
            raise

    def _check_balance(self, user_pubkey: str, asset_id: str, amount: int) -> bool:
        """Check if user has sufficient balance"""
        session = get_session()
        try:
            balance = session.query(AssetBalance).filter_by(
                user_pubkey=user_pubkey,
                asset_id=asset_id
            ).first()

            return balance and balance.balance >= amount

        except Exception as e:
            logger.error(f"Error checking balance: {e}")
            return False
        finally:
            session.close()

    def _reserve_balance(self, user_pubkey: str, asset_id: str, amount: int) -> bool:
        """Reserve balance for a transaction"""
        session = get_session()
        try:
            balance = session.query(AssetBalance).filter_by(
                user_pubkey=user_pubkey,
                asset_id=asset_id
            ).first()

            if not balance or balance.balance < amount:
                return False

            balance.balance -= amount
            balance.reserved_balance += amount
            session.commit()

            return True

        except Exception as e:
            logger.error(f"Error reserving balance: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    def _deduct_balance(self, user_pubkey: str, asset_id: str, amount: int) -> bool:
        """Deduct balance from reserved"""
        session = get_session()
        try:
            balance = session.query(AssetBalance).filter_by(
                user_pubkey=user_pubkey,
                asset_id=asset_id
            ).first()

            if not balance or balance.reserved_balance < amount:
                return False

            balance.reserved_balance -= amount
            session.commit()

            return True

        except Exception as e:
            logger.error(f"Error deducting balance: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    def _add_balance(self, user_pubkey: str, asset_id: str, amount: int) -> bool:
        """Add balance to user"""
        session = get_session()
        try:
            balance = session.query(AssetBalance).filter_by(
                user_pubkey=user_pubkey,
                asset_id=asset_id
            ).first()

            if not balance:
                # Create new balance record
                balance = AssetBalance(
                    user_pubkey=user_pubkey,
                    asset_id=asset_id,
                    balance=amount,
                    reserved_balance=0
                )
                session.add(balance)
            else:
                balance.balance += amount

            session.commit()
            return True

        except Exception as e:
            logger.error(f"Error adding balance: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    def _transfer_balance(self, from_pubkey: str, to_pubkey: str, asset_id: str, amount: int) -> bool:
        """Transfer balance between users"""
        session = get_session()
        try:
            # Deduct from sender
            from_balance = session.query(AssetBalance).filter_by(
                user_pubkey=from_pubkey,
                asset_id=asset_id
            ).first()

            if not from_balance or from_balance.reserved_balance < amount:
                return False

            from_balance.reserved_balance -= amount

            # Add to recipient
            to_balance = session.query(AssetBalance).filter_by(
                user_pubkey=to_pubkey,
                asset_id=asset_id
            ).first()

            if not to_balance:
                to_balance = AssetBalance(
                    user_pubkey=to_pubkey,
                    asset_id=asset_id,
                    balance=amount,
                    reserved_balance=0
                )
                session.add(to_balance)
            else:
                to_balance.balance += amount

            session.commit()
            return True

        except Exception as e:
            logger.error(f"Error transferring balance: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    def _verify_signature(self, signing_session: SigningSession, challenge: SigningChallenge, signature: str) -> bool:
        """Verify a signature (simplified implementation)"""
        # In a real implementation, you would cryptographically verify the signature
        # For now, we'll just check that the signature exists and is not empty
        return bool(signature and signature.strip())

    def _validate_lightning_invoice(self, invoice: str) -> bool:
        """Validate a Lightning invoice (simplified)"""
        # In a real implementation, you would properly validate the Lightning invoice
        # For now, we'll just check basic format
        return invoice and invoice.startswith('ln') and len(invoice) > 100

    def _pay_lightning_invoice(self, invoice: str) -> Dict[str, Any]:
        """Pay a Lightning invoice (placeholder implementation)"""
        # In a real implementation, you would use LND to pay the invoice
        return {
            'payment_hash': 'placeholder_hash',
            'payment_preimage': 'placeholder_preimage',
            'payment_success': True
        }

    def _create_transaction_record(self, signing_session: SigningSession, tx_type: str, amount: int):
        """Create a transaction record"""
        session = get_session()
        try:
            transaction = Transaction(
                txid=f"placeholder_{int(time.time())}_{signing_session.session_id[:8]}",
                session_id=signing_session.session_id,
                tx_type=tx_type,
                raw_tx="placeholder_raw_tx",
                status='completed',
                amount_sats=amount,
                fee_sats=0
            )

            session.add(transaction)
            session.commit()

        except Exception as e:
            logger.error(f"Error creating transaction record: {e}")
            session.rollback()
        finally:
            session.close()

# Worker instances
_action_intent_worker = None
_signing_response_worker = None

def get_action_intent_worker() -> NostrWorker:
    """Get the action intent worker instance"""
    global _action_intent_worker
    if _action_intent_worker is None:
        _action_intent_worker = NostrWorker()
    return _action_intent_worker

def get_signing_response_worker() -> NostrWorker:
    """Get the signing response worker instance"""
    global _signing_response_worker
    if _signing_response_worker is None:
        _signing_response_worker = NostrWorker()
    return _signing_response_worker
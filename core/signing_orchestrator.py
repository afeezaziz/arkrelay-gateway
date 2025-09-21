import uuid
import json
import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List, Tuple
from enum import Enum
import logging
from core.models import Transaction, SigningSession, get_session
from core.session_manager import get_session_manager, SessionState
from core.challenge_manager import get_challenge_manager
from core.transaction_processor import get_transaction_processor, TransactionError
from grpc_clients import get_grpc_manager, ServiceType
from nostr_clients.nostr_client import get_nostr_client

logger = logging.getLogger(__name__)

class SigningStep(Enum):
    INTENT_VERIFICATION = 1
    ARK_TRANSACTION_PREP = 2
    CHECKPOINT_TRANSACTION_PREP = 3
    SIGNATURE_COLLECTION = 4
    ARK_PROTOCOL_EXECUTION = 5
    FINALIZATION = 6

class SigningCeremonyError(Exception):
    """Raised when signing ceremony fails"""
    pass

class SigningTimeoutError(SigningCeremonyError):
    """Raised when signing ceremony times out"""
    pass

class SigningOrchestrator:
    """Orchestrates the 6-step signing ceremony for Ark Relay transactions"""

    def __init__(self, step_timeout: int = 300, total_timeout: int = 1800):
        """
        Initialize signing orchestrator

        Args:
            step_timeout: Timeout per step in seconds (5 minutes)
            total_timeout: Total ceremony timeout in seconds (30 minutes)
        """
        self.step_timeout = step_timeout
        self.total_timeout = total_timeout
        self.transaction_processor = get_transaction_processor()
        self.grpc_manager = get_grpc_manager()

    def start_signing_ceremony(self, session_id: str) -> Dict[str, Any]:
        """
        Start the signing ceremony for a session

        Args:
            session_id: Session ID to start ceremony for

        Returns:
            Ceremony status dictionary
        """
        session_manager = get_session_manager()
        session = session_manager.get_session(session_id)

        if not session:
            raise SigningCeremonyError(f"Session {session_id} not found")

        if session.status != SessionState.AWAITING_SIGNATURE.value:
            raise SigningCeremonyError(f"Session {session_id} is not ready for signing")

        # Initialize ceremony state
        ceremony_state = {
            'session_id': session_id,
            'current_step': SigningStep.INTENT_VERIFICATION.value,
            'start_time': datetime.utcnow(),
            'step_start_time': datetime.utcnow(),
            'completed_steps': [],
            'signatures_collected': {},
            'transactions': {},
            'ark_tx_id': None,
            'checkpoint_tx_id': None
        }

        # Store ceremony state in session result_data
        session_manager._update_session_result(session_id, {
            'ceremony_state': ceremony_state,
            'ceremony_status': 'in_progress'
        })

        # Start with step 1
        return self._execute_signing_step(session_id, SigningStep.INTENT_VERIFICATION, ceremony_state)

    def execute_signing_step(self, session_id: str, step: SigningStep,
                           signature_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Execute a specific signing step

        Args:
            session_id: Session ID
            step: Step to execute
            signature_data: Optional signature data for the step

        Returns:
            Step result dictionary
        """
        session_manager = get_session_manager()
        session = session_manager.get_session(session_id)

        if not session:
            raise SigningCeremonyError(f"Session {session_id} not found")

        # Get ceremony state
        ceremony_state = session.result_data.get('ceremony_state', {})
        if not ceremony_state:
            raise SigningCeremonyError(f"No ceremony state found for session {session_id}")

        # Check timeout
        if self._is_ceremony_timed_out(ceremony_state):
            raise SigningTimeoutError(f"Signing ceremony for session {session_id} has timed out")

        # Execute step
        try:
            step_result = self._execute_signing_step(session_id, step, ceremony_state, signature_data)

            # Update ceremony state
            ceremony_state['completed_steps'].append(step.value)
            ceremony_state['current_step'] = step.value + 1 if step.value < 6 else 6
            ceremony_state['step_start_time'] = datetime.utcnow()

            # Update session
            session_manager._update_session_result(session_id, {
                'ceremony_state': ceremony_state,
                'last_step_result': step_result
            })

            # Check if ceremony is complete
            if step == SigningStep.FINALIZATION:
                session_manager.complete_session(session_id, step_result)
            else:
                session_manager.update_session_status(session_id, SessionState.SIGNING.value,
                                                   f"Completed step {step.value}")

            return step_result

        except Exception as e:
            # Handle ceremony failure
            error_result = {
                'step': step.value,
                'status': 'failed',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }

            session_manager.fail_session(session_id, f"Step {step.value} failed: {str(e)}")
            raise SigningCeremonyError(f"Step {step.value} failed: {str(e)}")

    def _execute_signing_step(self, session_id: str, step: SigningStep,
                            ceremony_state: Dict[str, Any],
                            signature_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute a specific signing step"""

        if step == SigningStep.INTENT_VERIFICATION:
            return self._verify_intent(session_id, ceremony_state)
        elif step == SigningStep.ARK_TRANSACTION_PREP:
            return self._prepare_ark_transaction(session_id, ceremony_state)
        elif step == SigningStep.CHECKPOINT_TRANSACTION_PREP:
            return self._prepare_checkpoint_transaction(session_id, ceremony_state)
        elif step == SigningStep.SIGNATURE_COLLECTION:
            return self._collect_signatures(session_id, ceremony_state, signature_data)
        elif step == SigningStep.ARK_PROTOCOL_EXECUTION:
            return self._execute_ark_protocol(session_id, ceremony_state)
        elif step == SigningStep.FINALIZATION:
            return self._finalize_ceremony(session_id, ceremony_state)
        else:
            raise ValueError(f"Unknown signing step: {step}")

    def _verify_intent(self, session_id: str, ceremony_state: Dict[str, Any]) -> Dict[str, Any]:
        """Step 1: Verify the user's intent"""
        logger.info(f"Starting intent verification for session {session_id}")

        session_manager = get_session_manager()
        session = session_manager.get_session(session_id)

        if not session:
            raise SigningCeremonyError(f"Session {session_id} not found")

        intent_data = session.intent_data
        session_type = session.session_type

        # Validate intent data based on session type
        if session_type == 'p2p_transfer':
            required_fields = ['recipient_pubkey', 'amount', 'asset_id']
            for field in required_fields:
                if field not in intent_data:
                    raise SigningCeremonyError(f"Missing required field: {field}")

            # Validate amounts
            amount = intent_data.get('amount', 0)
            if amount <= 0:
                raise SigningCeremonyError("Invalid amount: must be positive")

            # Validate recipient pubkey
            recipient_pubkey = intent_data.get('recipient_pubkey')
            if not self._validate_pubkey(recipient_pubkey):
                raise SigningCeremonyError("Invalid recipient public key")

        elif session_type in ['lightning_lift', 'lightning_land']:
            required_fields = ['amount', 'asset_id']
            for field in required_fields:
                if field not in intent_data:
                    raise SigningCeremonyError(f"Missing required field: {field}")

            amount = intent_data.get('amount', 0)
            if amount <= 0:
                raise SigningCeremonyError("Invalid amount: must be positive")

        # Log intent verification
        logger.info(f"Intent verification completed for session {session_id}: {session_type}")

        return {
            'step': SigningStep.INTENT_VERIFICATION.value,
            'status': 'completed',
            'session_type': session_type,
            'intent_validated': True,
            'timestamp': datetime.utcnow().isoformat()
        }

    def _prepare_ark_transaction(self, session_id: str, ceremony_state: Dict[str, Any]) -> Dict[str, Any]:
        """Step 2: Prepare ARK transaction"""
        logger.info(f"Preparing ARK transaction for session {session_id}")

        try:
            # Get session details
            session_manager = get_session_manager()
            session = session_manager.get_session(session_id)

            if not session:
                raise SigningCeremonyError(f"Session {session_id} not found")

            # Process transaction based on session type
            if session.session_type == 'p2p_transfer':
                tx_result = self.transaction_processor.process_p2p_transfer(session_id)
                ark_tx_id = tx_result['txid']
            else:
                # For Lightning operations, create a simple ARK transaction
                ark_tx_id = self._create_ark_transaction(session)

            # Store transaction ID
            ceremony_state['ark_tx_id'] = ark_tx_id
            ceremony_state['transactions']['ark_tx'] = ark_tx_id

            logger.info(f"ARK transaction prepared: {ark_tx_id}")

            return {
                'step': SigningStep.ARK_TRANSACTION_PREP.value,
                'status': 'completed',
                'ark_tx_id': ark_tx_id,
                'timestamp': datetime.utcnow().isoformat()
            }

        except TransactionError as e:
            raise SigningCeremonyError(f"Failed to prepare ARK transaction: {str(e)}")

    def _prepare_checkpoint_transaction(self, session_id: str, ceremony_state: Dict[str, Any]) -> Dict[str, Any]:
        """Step 3: Prepare checkpoint transaction"""
        logger.info(f"Preparing checkpoint transaction for session {session_id}")

        try:
            # Create checkpoint transaction using ARKD
            arkd_client = self.grpc_manager.get_client(ServiceType.ARKD)
            if not arkd_client:
                raise SigningCeremonyError("ARKD client not available")

            # Create checkpoint transaction
            checkpoint_result = arkd_client.create_checkpoint_transaction(ceremony_state['ark_tx_id'])

            if not checkpoint_result.get('success'):
                raise SigningCeremonyError(f"Failed to create checkpoint transaction: {checkpoint_result.get('error')}")

            checkpoint_tx_id = checkpoint_result['txid']
            ceremony_state['checkpoint_tx_id'] = checkpoint_tx_id
            ceremony_state['transactions']['checkpoint_tx'] = checkpoint_tx_id

            logger.info(f"Checkpoint transaction prepared: {checkpoint_tx_id}")

            return {
                'step': SigningStep.CHECKPOINT_TRANSACTION_PREP.value,
                'status': 'completed',
                'checkpoint_tx_id': checkpoint_tx_id,
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            raise SigningCeremonyError(f"Failed to prepare checkpoint transaction: {str(e)}")

    def _collect_signatures(self, session_id: str, ceremony_state: Dict[str, Any],
                          signature_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Step 4: Collect signatures"""
        logger.info(f"Collecting signatures for session {session_id}")

        try:
            session_manager = get_session_manager()
            session = session_manager.get_session(session_id)

            if not session:
                raise SigningCeremonyError(f"Session {session_id} not found")

            # Get challenge response
            if not signature_data:
                # This would typically involve waiting for user signature via Nostr
                # For now, we'll use the session's challenge signature
                challenge_manager = get_challenge_manager()
                challenge = session_manager.get_session(session_id).challenge

                if not challenge or not challenge.signature:
                    raise SigningCeremonyError("No signature available for collection")

                signature_data = {
                    'user_signature': challenge.signature.hex(),
                    'timestamp': datetime.utcnow().isoformat()
                }

            # Store signatures
            ceremony_state['signatures_collected']['user'] = signature_data['user_signature']
            ceremony_state['signatures_collected']['gateway'] = self._sign_with_gateway_key(session_id)

            # Get additional signatures if needed
            if session.session_type == 'p2p_transfer':
                # Need recipient signature
                recipient_signature = self._request_recipient_signature(session_id)
                if recipient_signature:
                    ceremony_state['signatures_collected']['recipient'] = recipient_signature

            logger.info(f"Signatures collected for session {session_id}")

            return {
                'step': SigningStep.SIGNATURE_COLLECTION.value,
                'status': 'completed',
                'signatures_collected': list(ceremony_state['signatures_collected'].keys()),
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            raise SigningCeremonyError(f"Failed to collect signatures: {str(e)}")

    def _execute_ark_protocol(self, session_id: str, ceremony_state: Dict[str, Any]) -> Dict[str, Any]:
        """Step 5: Execute Ark protocol"""
        logger.info(f"Executing Ark protocol for session {session_id}")

        try:
            arkd_client = self.grpc_manager.get_client(ServiceType.ARKD)
            if not arkd_client:
                raise SigningCeremonyError("ARKD client not available")

            # Execute Ark protocol with collected signatures
            ark_tx_id = ceremony_state['ark_tx_id']
            signatures = ceremony_state['signatures_collected']

            protocol_result = arkd_client.execute_ark_protocol(
                ark_tx_id,
                signatures
            )

            if not protocol_result.get('success'):
                raise SigningCeremonyError(f"Ark protocol execution failed: {protocol_result.get('error')}")

            logger.info(f"Ark protocol executed successfully for session {session_id}")

            return {
                'step': SigningStep.ARK_PROTOCOL_EXECUTION.value,
                'status': 'completed',
                'protocol_result': protocol_result,
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            raise SigningCeremonyError(f"Failed to execute Ark protocol: {str(e)}")

    def _finalize_ceremony(self, session_id: str, ceremony_state: Dict[str, Any]) -> Dict[str, Any]:
        """Step 6: Finalize the ceremony"""
        logger.info(f"Finalizing ceremony for session {session_id}")

        try:
            session_manager = get_session_manager()
            session = session_manager.get_session(session_id)

            if not session:
                raise SigningCeremonyError(f"Session {session_id} not found")

            # Get final transaction details
            final_tx_id = ceremony_state.get('ark_tx_id')
            if not final_tx_id:
                raise SigningCeremonyError("No final transaction ID available")

            # Broadcast the final transaction
            broadcast_result = self.transaction_processor.broadcast_transaction(final_tx_id)

            if not broadcast_result:
                raise SigningCeremonyError("Failed to broadcast final transaction")

            # Update session with final result
            final_result = {
                'txid': final_tx_id,
                'session_type': session.session_type,
                'status': 'completed',
                'completed_steps': ceremony_state['completed_steps'],
                'transactions': ceremony_state['transactions'],
                'broadcast_success': True,
                'timestamp': datetime.utcnow().isoformat()
            }

            logger.info(f"Ceremony finalized for session {session_id}: {final_tx_id}")

            return final_result

        except Exception as e:
            raise SigningCeremonyError(f"Failed to finalize ceremony: {str(e)}")

    def _create_ark_transaction(self, session) -> str:
        """Create a basic ARK transaction for non-P2P sessions"""
        # Generate transaction ID
        tx_id = hashlib.sha256(f"{session.session_id}{datetime.utcnow().isoformat()}".encode()).hexdigest()

        # Create transaction record
        db_session = get_session()
        try:
            transaction = Transaction(
                txid=tx_id,
                session_id=session.session_id,
                tx_type='ark_tx',
                status='pending',
                amount_sats=session.intent_data.get('amount', 0),
                fee_sats=100  # Default fee
            )
            db_session.add(transaction)
            db_session.commit()

            return tx_id

        except Exception as e:
            db_session.rollback()
            raise SigningCeremonyError(f"Failed to create ARK transaction: {str(e)}")
        finally:
            db_session.close()

    def _sign_with_gateway_key(self, session_id: str) -> str:
        """Sign with the gateway's private key"""
        # This is a placeholder - in reality, you'd use the gateway's actual private key
        signature_data = f"{session_id}{datetime.utcnow().isoformat()}"
        return hashlib.sha256(signature_data.encode()).hexdigest()

    def _request_recipient_signature(self, session_id: str) -> Optional[str]:
        """Request signature from recipient via Nostr"""
        # This is a placeholder - in reality, you'd send a Nostr DM to the recipient
        # and wait for their signature response
        return None

    def _validate_pubkey(self, pubkey: str) -> bool:
        """Validate a public key format"""
        try:
            # Basic validation - should be hex string of appropriate length
            if len(pubkey) not in [66, 130]:  # Compressed or uncompressed
                return False

            # Try to decode as hex
            bytes.fromhex(pubkey)
            return True

        except ValueError:
            return False

    def _is_ceremony_timed_out(self, ceremony_state: Dict[str, Any]) -> bool:
        """Check if the ceremony has timed out"""
        start_time = ceremony_state.get('start_time')
        if not start_time:
            return False

        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))

        elapsed = (datetime.utcnow() - start_time).total_seconds()
        return elapsed > self.total_timeout

    def get_ceremony_status(self, session_id: str) -> Dict[str, Any]:
        """Get the current status of a signing ceremony"""
        session_manager = get_session_manager()
        session = session_manager.get_session(session_id)

        if not session:
            return {'error': 'Session not found'}

        ceremony_state = session.result_data.get('ceremony_state', {})

        status = {
            'session_id': session_id,
            'session_status': session.status,
            'ceremony_status': 'not_started' if not ceremony_state else 'in_progress',
            'current_step': ceremony_state.get('current_step', 0),
            'completed_steps': ceremony_state.get('completed_steps', []),
            'transactions': ceremony_state.get('transactions', {}),
            'signatures_collected': ceremony_state.get('signatures_collected', {}),
            'start_time': ceremony_state.get('start_time'),
            'last_updated': session.updated_at.isoformat()
        }

        if ceremony_state:
            start_time = ceremony_state.get('start_time')
            if isinstance(start_time, str):
                start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))

            elapsed = (datetime.utcnow() - start_time).total_seconds()
            status['time_elapsed'] = elapsed
            status['time_remaining'] = max(0, self.total_timeout - elapsed)

        return status

    def cancel_ceremony(self, session_id: str, reason: str = "User cancelled") -> bool:
        """Cancel an in-progress signing ceremony"""
        session_manager = get_session_manager()
        return session_manager.fail_session(session_id, f"Ceremony cancelled: {reason}")

# Global signing orchestrator instance
signing_orchestrator = SigningOrchestrator()

def get_signing_orchestrator() -> SigningOrchestrator:
    """Get the global signing orchestrator instance"""
    return signing_orchestrator
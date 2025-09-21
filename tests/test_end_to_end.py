"""
End-to-end transaction testing for Ark Relay Gateway
"""

import pytest
import time
import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from decimal import Decimal

from tests.test_config import configure_test_environment


class TestEndToEndTransactions:
    """End-to-end transaction testing suite"""

    @pytest.fixture
    def e2e_config(self):
        """End-to-end test configuration"""
        return {
            'test_user_pubkey': 'test_user_pubkey_123',
            'recipient_pubkey': 'recipient_pubkey_456',
            'asset_id': 'gbtc',
            'transfer_amount': 10000,
            'lightning_amount': 50000,
            'session_timeout': 300,  # 5 minutes
            'confirmation_timeout': 1800,  # 30 minutes
            'max_retries': 3
        }

    @pytest.fixture
    def complete_mock_services(self):
        """Complete mock services for end-to-end testing"""
        with patch('grpc_clients.arkd_client.ArkClient') as mock_arkd, \
             patch('grpc_clients.lnd_client.LndClient') as mock_lnd, \
             patch('grpc_clients.tapd_client.TapClient') as mock_tapd, \
             patch('session_manager.SessionManager') as mock_session, \
             patch('models.get_session') as mock_db, \
             patch('nostr_clients.nostr_client.NostrClient') as mock_nostr, \
             patch('redis.Redis') as mock_redis:

            # ARKD Client
            arkd_client = Mock()
            arkd_client.health_check.return_value = True
            arkd_client.get_round_info.return_value = {
                'round_id': 1,
                'state': 'active',
                'participants': 3,
                'amount': 100000
            }
            arkd_client.list_vtxos.return_value = [
                {
                    'tx_id': 'existing_vtxo_tx',
                    'vout': 0,
                    'amount': 50000,
                    'asset_id': 'gbtc',
                    'is_spent': False
                }
            ]

            # LND Client
            lnd_client = Mock()
            lnd_client.health_check.return_value = True
            lnd_client.get_wallet_balance.return_value = {
                'confirmed_balance': 1000000,
                'unconfirmed_balance': 0
            }
            lnd_client.get_channel_balance.return_value = {
                'balance': 500000,
                'pending_open_balance': 0
            }
            lnd_client.add_invoice.return_value = {
                'payment_request': 'lnbc1000n1p3k3m2pp5test',
                'r_hash': 'test_r_hash',
                'payment_hash': 'test_payment_hash',
                'value': 1000
            }
            lnd_client.send_payment.return_value = {
                'payment_hash': 'test_payment_hash',
                'status': 'complete',
                'fee': 10
            }
            lnd_client.lookup_invoice.return_value = {
                'state': 'SETTLED',
                'value': 1000
            }

            # TAPD Client
            tapd_client = Mock()
            tapd_client.health_check.return_value = True
            tapd_client.list_assets.return_value = [
                {
                    'asset_id': 'gbtc',
                    'name': 'Bitcoin',
                    'amount': 21000000,
                    'genesis_point': 'test_genesis_point'
                }
            ]
            tapd_client.get_asset_balance.return_value = {
                'asset_id': 'gbtc',
                'balance': 100000
            }
            tapd_client.mint_asset.return_value = {
                'asset_id': 'gbtc',
                'amount': 100000
            }

            # Session Manager
            session_manager = Mock()
            session_manager.create_signing_session.return_value = Mock(
                session_id='test_session_id',
                user_pubkey='test_user_pubkey_123',
                state='pending',
                created_at=datetime.now(),
                expires_at=datetime.now() + timedelta(minutes=10)
            )
            session_manager.get_session.return_value = Mock(
                session_id='test_session_id',
                state='challenge_sent'
            )
            session_manager.create_signing_challenge.return_value = Mock(
                challenge_id='test_challenge_id',
                session_id='test_session_id',
                challenge_data='test_challenge_data'
            )
            session_manager.verify_signing_response.return_value = True

            # Database
            db_session = Mock()
            db_session.query.return_value.all.return_value = []
            db_session.add.return_value = None
            db_session.commit.return_value = None

            # Nostr Client
            nostr_client = Mock()
            nostr_client.connect.return_value = True
            nostr_client.publish_event.return_value = True
            nostr_client.subscribe_events.return_value = True

            # Redis
            redis_client = Mock()
            redis_client.ping.return_value = True
            redis_client.set.return_value = True
            redis_client.get.return_value = json.dumps({'status': 'pending'})
            redis_client.delete.return_value = True

            mock_arkd.return_value = arkd_client
            mock_lnd.return_value = lnd_client
            mock_tapd.return_value = tapd_client
            mock_session.return_value = session_manager
            mock_db.return_value = db_session
            mock_nostr.return_value = nostr_client
            mock_redis.return_value = redis_client

            yield {
                'arkd': arkd_client,
                'lnd': lnd_client,
                'tapd': tapd_client,
                'session': session_manager,
                'db': db_session,
                'nostr': nostr_client,
                'redis': redis_client
            }

    @pytest.mark.e2e
    def test_complete_p2p_transfer_workflow(self, e2e_config, complete_mock_services):
        """Test complete P2P transfer workflow"""
        services = complete_mock_services

        # Step 1: User initiates transfer
        action_intent = {
            'type': 'p2p_transfer',
            'amount': e2e_config['transfer_amount'],
            'recipient': e2e_config['recipient_pubkey'],
            'asset_id': e2e_config['asset_id']
        }

        session = services['session'].create_signing_session(
            e2e_config['test_user_pubkey'],
            action_intent,
            f"Transfer {e2e_config['transfer_amount']} sats to {e2e_config['recipient_pubkey']}"
        )

        assert session is not None
        assert session.user_pubkey == e2e_config['test_user_pubkey']

        # Step 2: System creates signing challenge
        challenge = services['session'].create_signing_challenge(
            session.session_id,
            'test_challenge_data',
            'Please sign this transfer'
        )

        assert challenge is not None
        assert challenge.session_id == session.session_id

        # Step 3: User responds with signature
        signature_response = 'test_signature_response'
        is_valid = services['session'].verify_signing_response(
            session.session_id,
            'test_signature',
            signature_response
        )

        assert is_valid is True

        # Step 4: System processes transaction
        asset_balance = services['tapd'].get_asset_balance(e2e_config['asset_id'])
        assert asset_balance['balance'] >= e2e_config['transfer_amount']

        # Step 5: System creates VTXOs
        vtxo_creation = services['arkd'].create_vtxos(
            e2e_config['transfer_amount'],
            e2e_config['asset_id']
        )

        assert vtxo_creation is not None
        assert 'tx_id' in vtxo_creation

        # Step 6: System publishes confirmation to Nostr
        nostr_event = {
            'kind': 31510,
            'content': json.dumps({
                'tx_id': vtxo_creation['tx_id'],
                'status': 'completed',
                'amount': e2e_config['transfer_amount'],
                'recipient': e2e_config['recipient_pubkey']
            })
        }

        nostr_success = services['nostr'].publish_event(nostr_event)
        assert nostr_success is True

        # Step 7: Update database
        services['db'].add(Mock())
        services['db'].commit()

        # Verify complete workflow
        assert services['session'].create_signing_session.called
        assert services['session'].create_signing_challenge.called
        assert services['session'].verify_signing_response.called
        assert services['tapd'].get_asset_balance.called
        assert services['arkd'].create_vtxos.called
        assert services['nostr'].publish_event.called
        assert services['db'].commit.called

    @pytest.mark.e2e
    def test_lightning_lift_workflow(self, e2e_config, complete_mock_services):
        """Test complete Lightning lift workflow"""
        services = complete_mock_services

        # Step 1: User requests Lightning lift
        lift_request = {
            'type': 'lightning_lift',
            'asset_id': e2e_config['asset_id'],
            'amount_sats': e2e_config['lightning_amount'],
            'memo': 'Lightning lift test'
        }

        # Step 2: System validates user balance
        asset_balance = services['tapd'].get_asset_balance(e2e_config['asset_id'])
        assert asset_balance['balance'] >= e2e_config['lightning_amount']

        # Step 3: System creates signing session
        session = services['session'].create_signing_session(
            e2e_config['test_user_pubkey'],
            lift_request,
            f"Lightning lift: {e2e_config['lightning_amount']} sats"
        )

        assert session is not None

        # Step 4: System creates signing challenge
        challenge = services['session'].create_signing_challenge(
            session.session_id,
            'lift_challenge_data',
            'Please sign this Lightning lift request'
        )

        assert challenge is not None

        # Step 5: User signs challenge
        is_valid = services['session'].verify_signing_response(
            session.session_id,
            'test_signature',
            'test_response'
        )

        assert is_valid is True

        # Step 6: System processes asset conversion
        conversion_result = services['tapd'].mint_asset(e2e_config['lightning_amount'])
        assert conversion_result is not None

        # Step 7: System creates Lightning invoice
        invoice = services['lnd'].add_invoice(e2e_config['lightning_amount'])
        assert 'payment_request' in invoice

        # Step 8: System processes payment
        payment_result = services['lnd'].send_payment(invoice['payment_request'])
        assert payment_result['status'] == 'complete'

        # Step 9: System updates state
        state_update = {
            'session_id': session.session_id,
            'status': 'completed',
            'invoice': invoice['payment_request'],
            'payment_hash': payment_result['payment_hash']
        }

        services['redis'].set(
            f'lift_session_{session.session_id}',
            json.dumps(state_update)
        )

        # Verify workflow completion
        assert services['session'].create_signing_session.called
        assert services['tapd'].get_asset_balance.called
        assert services['lnd'].add_invoice.called
        assert services['lnd'].send_payment.called
        assert services['redis'].set.called

    @pytest.mark.e2e
    def test_lightning_land_workflow(self, e2e_config, complete_mock_services):
        """Test complete Lightning land workflow"""
        services = complete_mock_services

        # Step 1: User provides Lightning invoice
        lightning_invoice = 'lnbc1000n1p3k3m2pp5test_invoice'
        land_request = {
            'type': 'lightning_land',
            'asset_id': e2e_config['asset_id'],
            'amount_sats': e2e_config['lightning_amount'],
            'lightning_invoice': lightning_invoice
        }

        # Step 2: System validates invoice
        invoice_lookup = services['lnd'].lookup_invoice(lightning_invoice)
        assert invoice_lookup['state'] == 'SETTLED'

        # Step 3: System creates signing session
        session = services['session'].create_signing_session(
            e2e_config['test_user_pubkey'],
            land_request,
            f"Lightning land: {e2e_config['lightning_amount']} sats"
        )

        assert session is not None

        # Step 4: System creates signing challenge
        challenge = services['session'].create_signing_challenge(
            session.session_id,
            'land_challenge_data',
            'Please sign this Lightning land request'
        )

        assert challenge is not None

        # Step 5: User signs challenge
        is_valid = services['session'].verify_signing_response(
            session.session_id,
            'test_signature',
            'test_response'
        )

        assert is_valid is True

        # Step 6: System mints new assets
        mint_result = services['tapd'].mint_asset(e2e_config['lightning_amount'])
        assert mint_result is not None

        # Step 7: System creates VTXOs for user
        vtxo_creation = services['arkd'].create_vtxos(
            e2e_config['lightning_amount'],
            e2e_config['asset_id']
        )

        assert vtxo_creation is not None

        # Step 8: System publishes confirmation to Nostr
        nostr_event = {
            'kind': 31512,
            'content': json.dumps({
                'session_id': session.session_id,
                'status': 'completed',
                'amount': e2e_config['lightning_amount'],
                'asset_id': e2e_config['asset_id'],
                'vtxo_tx_id': vtxo_creation['tx_id']
            })
        }

        nostr_success = services['nostr'].publish_event(nostr_event)
        assert nostr_success is True

        # Verify workflow completion
        assert services['session'].create_signing_session.called
        assert services['lnd'].lookup_invoice.called
        assert services['tapd'].mint_asset.called
        assert services['arkd'].create_vtxos.called
        assert services['nostr'].publish_event.called

    @pytest.mark.e2e
    def test_multi_step_transaction_orchestration(self, e2e_config, complete_mock_services):
        """Test multi-step transaction orchestration"""
        services = complete_mock_services

        # Complex transaction involving multiple steps
        transaction_steps = [
            {
                'step': 'initiate',
                'action': 'create_session',
                'params': {
                    'user_pubkey': e2e_config['test_user_pubkey'],
                    'intent': {'type': 'complex_transfer', 'amount': 50000}
                }
            },
            {
                'step': 'challenge',
                'action': 'create_challenge',
                'params': {
                    'challenge_data': 'complex_challenge'
                }
            },
            {
                'step': 'verify',
                'action': 'verify_signature',
                'params': {
                    'signature': 'complex_signature'
                }
            },
            {
                'step': 'process',
                'action': 'create_vtxos',
                'params': {
                    'amount': 50000,
                    'asset_id': e2e_config['asset_id']
                }
            },
            {
                'step': 'confirm',
                'action': 'publish_nostr',
                'params': {
                    'status': 'completed'
                }
            }
        ]

        # Execute multi-step transaction
        for step in transaction_steps:
            if step['action'] == 'create_session':
                result = services['session'].create_signing_session(
                    step['params']['user_pubkey'],
                    step['params']['intent'],
                    'Complex multi-step transaction'
                )
                assert result is not None

            elif step['action'] == 'create_challenge':
                result = services['session'].create_signing_challenge(
                    'test_session_id',
                    step['params']['challenge_data'],
                    'Complex challenge'
                )
                assert result is not None

            elif step['action'] == 'verify_signature':
                result = services['session'].verify_signing_response(
                    'test_session_id',
                    step['params']['signature'],
                    'test_response'
                )
                assert result is True

            elif step['action'] == 'create_vtxos':
                result = services['arkd'].create_vtxos(
                    step['params']['amount'],
                    step['params']['asset_id']
                )
                assert result is not None

            elif step['action'] == 'publish_nostr':
                result = services['nostr'].publish_event({
                    'kind': 31510,
                    'content': json.dumps(step['params'])
                })
                assert result is True

        # Verify all steps were executed
        assert services['session'].create_signing_session.called
        assert services['session'].create_signing_challenge.called
        assert services['session'].verify_signing_response.called
        assert services['arkd'].create_vtxos.called
        assert services['nostr'].publish_event.called

    @pytest.mark.e2e
    def test_concurrent_transaction_processing(self, e2e_config, complete_mock_services):
        """Test concurrent transaction processing"""
        services = complete_mock_services
        import threading
        import queue

        def process_transaction(transaction_id, results):
            """Process a single transaction"""
            try:
                # Create session
                session = services['session'].create_signing_session(
                    f'user_{transaction_id}',
                    {'type': 'transfer', 'amount': 10000},
                    f'Concurrent transfer {transaction_id}'
                )

                # Create challenge
                challenge = services['session'].create_signing_challenge(
                    session.session_id,
                    f'challenge_{transaction_id}',
                    f'Challenge {transaction_id}'
                )

                # Verify signature
                is_valid = services['session'].verify_signing_response(
                    session.session_id,
                    f'signature_{transaction_id}',
                    f'response_{transaction_id}'
                )

                # Create VTXOs
                vtxos = services['arkd'].create_vtxos(10000, 'gbtc')

                # Publish to Nostr
                nostr_success = services['nostr'].publish_event({
                    'kind': 31510,
                    'content': json.dumps({
                        'tx_id': vtxos['tx_id'],
                        'transaction_id': transaction_id,
                        'status': 'completed'
                    })
                })

                results.append({
                    'transaction_id': transaction_id,
                    'success': True,
                    'session_id': session.session_id,
                    'nostr_published': nostr_success
                })

            except Exception as e:
                results.append({
                    'transaction_id': transaction_id,
                    'success': False,
                    'error': str(e)
                })

        # Execute concurrent transactions
        results = []
        threads = []

        for i in range(10):
            thread = threading.Thread(target=process_transaction, args=(i, results))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Analyze results
        successful = [r for r in results if r['success']]
        failed = [r for r in results if not r['success']]

        assert len(successful) > 0
        assert len(successful) + len(failed) == 10

        # Verify all transactions have unique session IDs
        session_ids = [r['session_id'] for r in successful]
        assert len(set(session_ids)) == len(session_ids)

    @pytest.mark.e2e
    def test_transaction_state_consistency(self, e2e_config, complete_mock_services):
        """Test transaction state consistency across all components"""
        services = complete_mock_services

        # Track state changes throughout transaction
        state_changes = []

        def track_state_change(component, state):
            state_changes.append({
                'component': component,
                'state': state,
                'timestamp': time.time()
            })

        # Step 1: Initial state
        track_state_change('session_manager', 'initial')

        # Step 2: Create session
        session = services['session'].create_signing_session(
            e2e_config['test_user_pubkey'],
            {'type': 'transfer', 'amount': 10000},
            'State consistency test'
        )
        track_state_change('session_manager', 'session_created')

        # Step 3: Create challenge
        challenge = services['session'].create_signing_challenge(
            session.session_id,
            'consistency_challenge',
            'Consistency test challenge'
        )
        track_state_change('session_manager', 'challenge_created')

        # Step 4: Verify signature
        is_valid = services['session'].verify_signing_response(
            session.session_id,
            'test_signature',
            'test_response'
        )
        track_state_change('session_manager', 'signature_verified')

        # Step 5: Process transaction
        vtxos = services['arkd'].create_vtxos(10000, 'gbtc')
        track_state_change('arkd', 'vtxos_created')

        # Step 6: Update database
        services['db'].add(Mock())
        services['db'].commit()
        track_state_change('database', 'transaction_recorded')

        # Step 7: Publish to Nostr
        services['nostr'].publish_event({
            'kind': 31510,
            'content': json.dumps({'tx_id': vtxos['tx_id'], 'status': 'completed'})
        })
        track_state_change('nostr', 'event_published')

        # Verify state sequence
        expected_sequence = [
            'initial',
            'session_created',
            'challenge_created',
            'signature_verified',
            'vtxos_created',
            'transaction_recorded',
            'event_published'
        ]

        actual_sequence = [change['state'] for change in state_changes]

        assert actual_sequence == expected_sequence

        # Verify timestamps are sequential
        timestamps = [change['timestamp'] for change in state_changes]
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i-1]

    @pytest.mark.e2e
    def test_error_recovery_in_workflow(self, e2e_config, complete_mock_services):
        """Test error recovery within transaction workflow"""
        services = complete_mock_services

        # Simulate failure that can be recovered
        failure_count = 0

        def flaky_vtxo_creation(amount, asset_id):
            nonlocal failure_count
            failure_count += 1
            if failure_count <= 2:
                raise Exception(f"VTXO creation failed (attempt {failure_count})")
            return {'tx_id': 'recovered_vtxo', 'vtxos': []}

        services['arkd'].create_vtxos.side_effect = flaky_vtxo_creation

        # Execute workflow with recovery
        session = services['session'].create_signing_session(
            e2e_config['test_user_pubkey'],
            {'type': 'transfer', 'amount': 10000},
            'Recovery test'
        )

        challenge = services['session'].create_signing_challenge(
            session.session_id,
            'recovery_challenge',
            'Recovery test challenge'
        )

        is_valid = services['session'].verify_signing_response(
            session.session_id,
            'test_signature',
            'test_response'
        )

        assert is_valid is True

        # Should recover after failures
        vtxos = None
        for attempt in range(3):
            try:
                vtxos = services['arkd'].create_vtxos(10000, 'gbtc')
                if vtxos:
                    break
            except Exception:
                time.sleep(0.1)

        assert vtxos is not None
        assert vtxos['tx_id'] == 'recovered_vtxo'
        assert failure_count == 3

    @pytest.mark.e2e
    def test_transaction_idempotency(self, e2e_config, complete_mock_services):
        """Test transaction idempotency"""
        services = complete_mock_services

        # Execute same transaction multiple times
        transaction_id = str(uuid.uuid4())
        results = []

        for attempt in range(3):
            try:
                session = services['session'].create_signing_session(
                    e2e_config['test_user_pubkey'],
                    {'type': 'transfer', 'amount': 10000, 'id': transaction_id},
                    f'Idempotency test {attempt}'
                )

                challenge = services['session'].create_signing_challenge(
                    session.session_id,
                    f'challenge_{attempt}',
                    f'Challenge {attempt}'
                )

                is_valid = services['session'].verify_signing_response(
                    session.session_id,
                    f'signature_{attempt}',
                    f'response_{attempt}'
                )

                vtxos = services['arkd'].create_vtxos(10000, 'gbtc')

                results.append({
                    'attempt': attempt,
                    'success': True,
                    'session_id': session.session_id,
                    'vtxo_tx_id': vtxos['tx_id']
                })

            except Exception as e:
                results.append({
                    'attempt': attempt,
                    'success': False,
                    'error': str(e)
                })

        # All attempts should succeed (idempotency)
        successful = [r for r in results if r['success']]
        assert len(successful) == 3

        # Should use same session ID for same transaction
        session_ids = [r['session_id'] for r in successful]
        assert len(set(session_ids)) == 1  # All should be the same

    @pytest.mark.e2e
    def test_cross_asset_transaction(self, e2e_config, complete_mock_services):
        """Test cross-asset transaction workflow"""
        services = complete_mock_services

        # Configure multiple assets
        services['tapd'].list_assets.return_value = [
            {'asset_id': 'gbtc', 'name': 'Bitcoin', 'amount': 21000000},
            {'asset_id': 'usdt', 'name': 'Tether', 'amount': 1000000}
        ]

        services['tapd'].get_asset_balance.side_effect = lambda asset_id: {
            'gbtc': {'balance': 100000},
            'usdt': {'balance': 50000}
        }[asset_id]

        # Cross-asset transaction
        cross_asset_request = {
            'type': 'cross_asset_transfer',
            'from_asset': 'gbtc',
            'to_asset': 'usdt',
            'amount': 10000,
            'exchange_rate': 50000  # 1 BTC = 50,000 USDT
        }

        # Execute cross-asset workflow
        session = services['session'].create_signing_session(
            e2e_config['test_user_pubkey'],
            cross_asset_request,
            'Cross-asset transfer: 10000 sat to USDT'
        )

        # Check source asset balance
        source_balance = services['tapd'].get_asset_balance('gbtc')
        assert source_balance['balance'] >= 10000

        # Simulate conversion and transfer
        converted_amount = 10000 / cross_asset_request['exchange_rate']

        # Create VTXOs for target asset
        vtxos = services['arkd'].create_vtxos(int(converted_amount), 'usdt')
        assert vtxos is not None

        # Publish cross-asset transaction to Nostr
        nostr_event = {
            'kind': 31510,
            'content': json.dumps({
                'type': 'cross_asset',
                'from_asset': 'gbtc',
                'to_asset': 'usdt',
                'original_amount': 10000,
                'converted_amount': converted_amount,
                'exchange_rate': cross_asset_request['exchange_rate'],
                'status': 'completed'
            })
        }

        nostr_success = services['nostr'].publish_event(nostr_event)
        assert nostr_success is True

        # Verify cross-asset transaction
        assert services['tapd'].list_assets.called
        assert services['tapd'].get_asset_balance.called
        assert services['arkd'].create_vtxos.called
        assert services['nostr'].publish_event.called

    @pytest.mark.e2e
    def test_transaction_metrics_and_audit(self, e2e_config, complete_mock_services):
        """Test transaction metrics and audit trail"""
        services = complete_mock_services

        # Execute transaction with metrics tracking
        start_time = time.time()

        session = services['session'].create_signing_session(
            e2e_config['test_user_pubkey'],
            {'type': 'transfer', 'amount': 10000},
            'Metrics test'
        )

        challenge_creation_start = time.time()
        challenge = services['session'].create_signing_challenge(
            session.session_id,
            'metrics_challenge',
            'Metrics test challenge'
        )
        challenge_creation_time = time.time() - challenge_creation_start

        verification_start = time.time()
        is_valid = services['session'].verify_signing_response(
            session.session_id,
            'test_signature',
            'test_response'
        )
        verification_time = time.time() - verification_start

        vtxo_creation_start = time.time()
        vtxos = services['arkd'].create_vtxos(10000, 'gbtc')
        vtxo_creation_time = time.time() - vtxo_creation_start

        nostr_publish_start = time.time()
        nostr_success = services['nostr'].publish_event({
            'kind': 31510,
            'content': json.dumps({'tx_id': vtxos['tx_id'], 'status': 'completed'})
        })
        nostr_publish_time = time.time() - nostr_publish_start

        total_time = time.time() - start_time

        # Verify metrics
        metrics = {
            'total_transaction_time': total_time,
            'challenge_creation_time': challenge_creation_time,
            'signature_verification_time': verification_time,
            'vtxo_creation_time': vtxo_creation_time,
            'nostr_publish_time': nostr_publish_time,
            'transaction_successful': is_valid and nostr_success
        }

        assert metrics['total_transaction_time'] < 10  # Should complete within 10 seconds
        assert metrics['challenge_creation_time'] < 1
        assert metrics['signature_verification_time'] < 1
        assert metrics['vtxo_creation_time'] < 2
        assert metrics['nostr_publish_time'] < 1
        assert metrics['transaction_successful'] is True

        # Verify audit trail
        assert services['session'].create_signing_session.called
        assert services['session'].create_signing_challenge.called
        assert services['session'].verify_signing_response.called
        assert services['arkd'].create_vtxos.called
        assert services['nostr'].publish_event.called
"""
Tests for RGB Manager functionality
"""

import pytest
import json
from unittest.mock import Mock, patch
from datetime import datetime, timezone

from core.rgb_manager import RGBManager, RGBValidationError, RGBContractError, RGBSchemaType
from core.models import RGBContract, RGBAllocation, Asset, Vtxo
from tests.conftest import get_test_session


class TestRGBManager:
    """Test RGB Manager functionality"""

    def setup_method(self):
        """Setup test fixtures"""
        self.rgb_manager = RGBManager()
        self.session = get_test_session()

    def test_register_rgb_contract_success(self):
        """Test successful RGB contract registration"""
        contract_data = {
            'contract_id': 'test_contract_001',
            'name': 'Test RGB Contract',
            'description': 'A test RGB contract',
            'interface_id': 'RGB20Interface',
            'specification_id': 'RGB20Spec',
            'genesis_proof': 'test_genesis_proof_data',
            'schema_type': 'cfa',
            'metadata': {'field': 'value'},
            'creator_pubkey': 'npub1test123456789'
        }

        with patch('core.rgb_manager.get_session') as mock_session:
            mock_session.return_value = self.session

            # Mock the session query to return None (contract doesn't exist)
            self.session.query = Mock()
            self.session.query.return_value.filter_by.return_value.first.return_value = None

            # Mock asset query to return None (asset doesn't exist)
            self.session.query.return_value.filter_by.return_value.first.return_value = None

            result = self.rgb_manager.register_rgb_contract(contract_data)

            assert result['contract_id'] == 'test_contract_001'
            assert result['name'] == 'Test RGB Contract'
            assert result['schema_type'] == 'cfa'
            assert result['status'] == 'registered'
            assert 'created_at' in result

    def test_register_rgb_contract_missing_required_fields(self):
        """Test RGB contract registration with missing required fields"""
        contract_data = {
            'contract_id': 'test_contract_001',
            'name': 'Test RGB Contract'
            # Missing required fields
        }

        with pytest.raises(RGBValidationError) as exc_info:
            self.rgb_manager.register_rgb_contract(contract_data)

        assert 'Missing required field' in str(exc_info.value)

    def test_register_rgb_contract_already_exists(self):
        """Test RGB contract registration when contract already exists"""
        contract_data = {
            'contract_id': 'existing_contract',
            'name': 'Existing Contract',
            'interface_id': 'RGB20Interface',
            'specification_id': 'RGB20Spec',
            'genesis_proof': 'test_proof',
            'schema_type': 'cfa'
        }

        with patch('core.rgb_manager.get_session') as mock_session:
            mock_session.return_value = self.session

            # Mock existing contract
            existing_contract = Mock()
            self.session.query = Mock()
            self.session.query.return_value.filter_by.return_value.first.return_value = existing_contract

            with pytest.raises(RGBContractError) as exc_info:
                self.rgb_manager.register_rgb_contract(contract_data)

            assert 'already exists' in str(exc_info.value)

    def test_get_rgb_contract_success(self):
        """Test successful RGB contract retrieval"""
        with patch('core.rgb_manager.get_session') as mock_session:
            mock_session.return_value = self.session

            # Mock contract
            mock_contract = Mock()
            mock_contract.contract_id = 'test_contract_001'
            mock_contract.name = 'Test Contract'
            mock_contract.description = 'Test description'
            mock_contract.interface_id = 'RGB20Interface'
            mock_contract.specification_id = 'RGB20Spec'
            mock_contract.schema_type = 'cfa'
            mock_contract.genesis_proof = 'test_proof'
            mock_contract.metadata = {}
            mock_contract.creator_pubkey = 'npub1test'
            mock_contract.total_issued = 1000000
            mock_contract.current_state_root = 'root123'
            mock_contract.last_transition_txid = 'tx123'
            mock_contract.created_at = datetime.now(timezone.utc)
            mock_contract.updated_at = datetime.now(timezone.utc)

            # Mock asset
            mock_asset = Mock()
            mock_asset.asset_id = 'rgb_test_contract_001'
            mock_asset.ticker = 'RGBTEST'

            self.session.query = Mock()

            # Mock contract query
            def mock_contract_query(table):
                if table == RGBContract:
                    mock_query = Mock()
                    mock_query.filter_by.return_value.first.return_value = mock_contract
                    return mock_query
                elif table == Asset:
                    mock_query = Mock()
                    mock_query.filter_by.return_value.first.return_value = mock_asset
                    return mock_query
                return Mock()

            self.session.query.side_effect = mock_contract_query

            result = self.rgb_manager.get_rgb_contract('test_contract_001')

            assert result is not None
            assert result['contract_id'] == 'test_contract_001'
            assert result['name'] == 'Test Contract'
            assert result['schema_type'] == 'cfa'
            assert result['asset_id'] == 'rgb_test_contract_001'
            assert result['asset_ticker'] == 'RGBTEST'

    def test_get_rgb_contract_not_found(self):
        """Test RGB contract retrieval when contract doesn't exist"""
        with patch('core.rgb_manager.get_session') as mock_session:
            mock_session.return_value = self.session

            # Mock no contract found
            self.session.query = Mock()
            self.session.query.return_value.filter_by.return_value.first.return_value = None

            result = self.rgb_manager.get_rgb_contract('nonexistent_contract')

            assert result is None

    def test_create_rgb_allocation_success(self):
        """Test successful RGB allocation creation"""
        allocation_data = {
            'contract_id': 'test_contract_001',
            'vtxo_id': 'test_vtxo_001',
            'owner_pubkey': 'npub1test123456789',
            'amount': 1000000,
            'state_commitment': b'test_state',
            'proof_data': 'test_proof_data'
        }

        with patch('core.rgb_manager.get_session') as mock_session:
            mock_session.return_value = self.session

            # Mock existing contract
            mock_contract = Mock()
            mock_contract.contract_id = 'test_contract_001'
            mock_contract.schema_type = 'cfa'

            # Mock existing VTXO
            mock_vtxo = Mock()
            mock_vtxo.vtxo_id = 'test_vtxo_001'
            mock_vtxo.status = 'available'

            # Mock no existing allocation
            self.session.query = Mock()

            def mock_query(table):
                mock_q = Mock()
                if table == RGBContract:
                    mock_q.filter_by.return_value.first.return_value = mock_contract
                elif table == Vtxo:
                    mock_q.filter_by.return_value.first.return_value = mock_vtxo
                elif table == RGBAllocation:
                    mock_q.filter_by.return_value.first.return_value = None
                return mock_q

            self.session.query.side_effect = mock_query

            result = self.rgb_manager.create_rgb_allocation(allocation_data)

            assert result['contract_id'] == 'test_contract_001'
            assert result['vtxo_id'] == 'test_vtxo_001'
            assert result['owner_pubkey'] == 'npub1test123456789'
            assert result['amount'] == 1000000
            assert 'created_at' in result

    def test_create_rgb_allocation_missing_vtxo(self):
        """Test RGB allocation creation when VTXO doesn't exist"""
        allocation_data = {
            'contract_id': 'test_contract_001',
            'vtxo_id': 'nonexistent_vtxo',
            'owner_pubkey': 'npub1test123456789',
            'amount': 1000000
        }

        with patch('core.rgb_manager.get_session') as mock_session:
            mock_session.return_value = self.session

            # Mock existing contract
            mock_contract = Mock()

            # Mock no VTXO found
            self.session.query = Mock()

            def mock_query(table):
                mock_q = Mock()
                if table == RGBContract:
                    mock_q.filter_by.return_value.first.return_value = mock_contract
                elif table == Vtxo:
                    mock_q.filter_by.return_value.first.return_value = None
                return mock_q

            self.session.query.side_effect = mock_query

            with pytest.raises(RGBValidationError) as exc_info:
                self.rgb_manager.create_rgb_allocation(allocation_data)

            assert 'not found or not available' in str(exc_info.value)

    def test_validate_rgb_proof_success(self):
        """Test successful RGB proof validation"""
        with patch('core.rgb_manager.get_session') as mock_session:
            mock_session.return_value = self.session

            # Mock existing contract
            mock_contract = Mock()
            mock_contract.contract_id = 'test_contract_001'
            mock_contract.is_active = True

            self.session.query = Mock()
            self.session.query.return_value.filter_by.return_value.first.return_value = mock_contract

            result = self.rgb_manager.validate_rgb_proof('test_proof_data', 'test_contract_001')

            assert result is True

    def test_validate_rgb_proof_contract_not_found(self):
        """Test RGB proof validation when contract doesn't exist"""
        with patch('core.rgb_manager.get_session') as mock_session:
            mock_session.return_value = self.session

            # Mock no contract found
            self.session.query = Mock()
            self.session.query.return_value.filter_by.return_value.first.return_value = None

            result = self.rgb_manager.validate_rgb_proof('test_proof_data', 'nonexistent_contract')

            assert result is False

    def test_transfer_rgb_allocation_success(self):
        """Test successful RGB allocation transfer"""
        with patch('core.rgb_manager.get_session') as mock_session:
            mock_session.return_value = self.session

            # Mock existing allocation
            mock_allocation = Mock()
            mock_allocation.allocation_id = 'test_allocation_001'
            mock_allocation.contract_id = 'test_contract_001'
            mock_allocation.vtxo_id = 'test_vtxo_001'
            mock_allocation.owner_pubkey = 'npub1sender123456'
            mock_allocation.amount = 1000000
            mock_allocation.state_commitment = b'test_state'
            mock_allocation.proof_data = 'test_proof'
            mock_allocation.seal_type = 'tapret_first'
            mock_allocation.is_spent = False

            self.session.query = Mock()
            self.session.query.return_value.filter_by.return_value.first.return_value = mock_allocation

            result = self.rgb_manager.transfer_rgb_allocation(
                'npub1sender123456',
                'npub1receiver123456',
                'test_allocation_001',
                500000  # Partial transfer
            )

            assert result['from_allocation_id'] == 'test_allocation_001'
            assert result['contract_id'] == 'test_contract_001'
            assert result['amount'] == 500000
            assert result['from_pubkey'] == 'npub1sender123456'
            assert result['to_pubkey'] == 'npub1receiver123456'

    def test_transfer_rgb_allocation_not_owner(self):
        """Test RGB allocation transfer when sender is not owner"""
        with patch('core.rgb_manager.get_session') as mock_session:
            mock_session.return_value = self.session

            # Mock allocation owned by different pubkey
            mock_allocation = Mock()
            mock_allocation.owner_pubkey = 'npub1actualowner456'
            mock_allocation.is_spent = False

            self.session.query = Mock()
            self.session.query.return_value.filter_by.return_value.first.return_value = mock_allocation

            with pytest.raises(RGBValidationError) as exc_info:
                self.rgb_manager.transfer_rgb_allocation(
                    'npub1notowner123',
                    'npub1receiver123456',
                    'test_allocation_001'
                )

            assert 'owned by' in str(exc_info.value)

    def test_get_rgb_stats_success(self):
        """Test successful RGB statistics retrieval"""
        with patch('core.rgb_manager.get_session') as mock_session:
            mock_session.return_value = self.session

            # Mock statistics queries
            self.session.query = Mock()

            def mock_query(table):
                mock_q = Mock()
                if table == RGBContract:
                    # Mock count queries
                    def mock_count():
                        if hasattr(mock_q, '_call_count'):
                            mock_q._call_count += 1
                        else:
                            mock_q._call_count = 1

                        if mock_q._call_count == 1:
                            return 5  # total contracts
                        elif mock_q._call_count == 2:
                            return 4  # active contracts
                        return 0

                    mock_q.count.side_effect = mock_count
                    mock_q.filter_by.return_value.count.side_effect = mock_count

                elif table == RGBAllocation:
                    # Mock allocation stats
                    def mock_alloc_count():
                        if hasattr(mock_q, '_call_count'):
                            mock_q._call_count += 1
                        else:
                            mock_q._call_count = 1

                        if mock_q._call_count == 1:
                            return 10  # total allocations
                        elif mock_q._call_count == 2:
                            return 8  # active allocations
                        return 0

                    mock_q.count.side_effect = mock_alloc_count
                    mock_q.filter_by.return_value.count.side_effect = mock_alloc_count

                    # Mock sum query
                    mock_sum = Mock()
                    mock_sum.scalar.return_value = 5000000  # total value
                    mock_q.filter.return_value.scalar.return_value = mock_sum

                return mock_q

            self.session.query.side_effect = mock_query

            result = self.rgb_manager.get_rgb_stats()

            assert result['contracts']['total'] == 5
            assert result['contracts']['active'] == 4
            assert result['contracts']['inactive'] == 1
            assert result['allocations']['total'] == 10
            assert result['allocations']['active'] == 8
            assert result['allocations']['spent'] == 2
            assert result['allocations']['total_value'] == 5000000
            assert 'timestamp' in result

    def test_list_rgb_contracts_success(self):
        """Test successful RGB contracts listing"""
        with patch('core.rgb_manager.get_session') as mock_session:
            mock_session.return_value = self.session

            # Mock contracts list
            mock_contract1 = Mock()
            mock_contract1.contract_id = 'contract1'
            mock_contract1.name = 'Contract 1'
            mock_contract1.schema_type = 'cfa'
            mock_contract1.total_issued = 1000000
            mock_contract1.is_active = True
            mock_contract1.created_at = datetime.now(timezone.utc)

            mock_contract2 = Mock()
            mock_contract2.contract_id = 'contract2'
            mock_contract2.name = 'Contract 2'
            mock_contract2.schema_type = 'nia'
            mock_contract2.total_issued = 500000
            mock_contract2.is_active = True
            mock_contract2.created_at = datetime.now(timezone.utc)

            mock_query = Mock()
            mock_query.order_by.return_value.all.return_value = [mock_contract1, mock_contract2]

            # Mock asset queries
            def mock_asset_query(table):
                if table == Asset:
                    mock_q = Mock()
                    mock_q.filter_by.return_value.first.return_value = Mock(asset_id='asset1', ticker='RGB1')
                    return mock_q
                return mock_query

            self.session.query = Mock()
            self.session.query.side_effect = [mock_query] + [Mock() for _ in range(10)]  # First call for contracts, then assets

            result = self.rgb_manager.list_rgb_contracts(active_only=True)

            assert len(result) == 2
            assert result[0]['contract_id'] == 'contract1'
            assert result[0]['name'] == 'Contract 1'
            assert result[0]['schema_type'] == 'cfa'
            assert result[1]['contract_id'] == 'contract2'
            assert result[1]['schema_type'] == 'nia'

    def test_rgb_schema_type_enum(self):
        """Test RGB schema type enum values"""
        assert RGBSchemaType.CFA.value == 'cfa'
        assert RGBSchemaType.NIA.value == 'nia'
        assert RGBSchemaType.RIA.value == 'ria'
        assert RGBSchemaType.UDA.value == 'uda'

    def test_rgb_error_hierarchy(self):
        """Test RGB error class hierarchy"""
        from core.rgb_manager import RGBError

        # Test that specific error types inherit from RGBError
        assert issubclass(RGBValidationError, RGBError)
        assert issubclass(RGBContractError, RGBError)

        # Test error creation
        validation_error = RGBValidationError("Test validation error")
        contract_error = RGBContractError("Test contract error")

        assert str(validation_error) == "Test validation error"
        assert str(contract_error) == "Test contract error"
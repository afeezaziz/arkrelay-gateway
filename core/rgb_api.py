"""
RGB API Blueprint for Ark Relay Gateway

This module provides HTTP endpoints for RGB smart contract operations including:
- RGB contract registration and management
- RGB allocation creation and tracking
- RGB VTXO operations
- RGB proof validation
"""

from flask import Blueprint, request, jsonify
from typing import Dict, Any, Optional
import logging
from core.rgb_manager import get_rgb_manager, RGBValidationError, RGBContractError
from core.vtxo_manager import get_vtxo_manager
from core.asset_manager import get_asset_manager
from core.models import get_session

logger = logging.getLogger(__name__)

# Create RGB API blueprint
rgb_bp = Blueprint('rgb', __name__, url_prefix='/rgb')

@rgb_bp.route('/contracts', methods=['POST'])
def register_rgb_contract():
    """Register a new RGB contract"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        # Validate required fields
        required_fields = ['contract_id', 'name', 'interface_id', 'specification_id', 'genesis_proof', 'schema_type']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400

        rgb_manager = get_rgb_manager()
        result = rgb_manager.register_rgb_contract(data)

        return jsonify({
            'success': True,
            'data': result,
            'message': f"RGB contract {data['contract_id']} registered successfully"
        }), 201

    except RGBValidationError as e:
        return jsonify({'error': f'Validation error: {str(e)}'}), 400
    except RGBContractError as e:
        return jsonify({'error': f'Contract error: {str(e)}'}), 409
    except Exception as e:
        logger.error(f"❌ Failed to register RGB contract: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@rgb_bp.route('/contracts', methods=['GET'])
def list_rgb_contracts():
    """List all RGB contracts"""
    try:
        active_only = request.args.get('active_only', 'true').lower() == 'true'

        rgb_manager = get_rgb_manager()
        contracts = rgb_manager.list_rgb_contracts(active_only)

        return jsonify({
            'success': True,
            'data': contracts,
            'count': len(contracts)
        }), 200

    except Exception as e:
        logger.error(f"❌ Failed to list RGB contracts: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@rgb_bp.route('/contracts/<contract_id>', methods=['GET'])
def get_rgb_contract(contract_id: str):
    """Get RGB contract information"""
    try:
        rgb_manager = get_rgb_manager()
        contract = rgb_manager.get_rgb_contract(contract_id)

        if not contract:
            return jsonify({'error': 'RGB contract not found'}), 404

        return jsonify({
            'success': True,
            'data': contract
        }), 200

    except Exception as e:
        logger.error(f"❌ Failed to get RGB contract: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@rgb_bp.route('/allocations', methods=['POST'])
def create_rgb_allocation():
    """Create a new RGB allocation within a VTXO"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        # Validate required fields
        required_fields = ['contract_id', 'vtxo_id', 'owner_pubkey', 'amount']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400

        rgb_manager = get_rgb_manager()
        result = rgb_manager.create_rgb_allocation(data)

        return jsonify({
            'success': True,
            'data': result,
            'message': f"RGB allocation {result['allocation_id']} created successfully"
        }), 201

    except RGBValidationError as e:
        return jsonify({'error': f'Validation error: {str(e)}'}), 400
    except RGBContractError as e:
        return jsonify({'error': f'Contract error: {str(e)}'}), 409
    except Exception as e:
        logger.error(f"❌ Failed to create RGB allocation: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@rgb_bp.route('/allocations', methods=['GET'])
def get_rgb_allocations():
    """Get RGB allocations with optional filtering"""
    try:
        owner_pubkey = request.args.get('owner_pubkey')
        contract_id = request.args.get('contract_id')

        if not owner_pubkey and not contract_id:
            return jsonify({'error': 'At least one filter parameter (owner_pubkey or contract_id) is required'}), 400

        rgb_manager = get_rgb_manager()
        allocations = rgb_manager.get_rgb_allocations(owner_pubkey, contract_id)

        return jsonify({
            'success': True,
            'data': allocations,
            'count': len(allocations)
        }), 200

    except Exception as e:
        logger.error(f"❌ Failed to get RGB allocations: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@rgb_bp.route('/allocations/transfer', methods=['POST'])
def transfer_rgb_allocation():
    """Transfer RGB allocation from one user to another"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        # Validate required fields
        required_fields = ['from_pubkey', 'to_pubkey', 'allocation_id']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400

        rgb_manager = get_rgb_manager()
        result = rgb_manager.transfer_rgb_allocation(
            data['from_pubkey'],
            data['to_pubkey'],
            data['allocation_id'],
            data.get('amount')  # Optional amount for partial transfers
        )

        return jsonify({
            'success': True,
            'data': result,
            'message': f"RGB allocation transferred successfully"
        }), 200

    except RGBValidationError as e:
        return jsonify({'error': f'Validation error: {str(e)}'}), 400
    except Exception as e:
        logger.error(f"❌ Failed to transfer RGB allocation: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@rgb_bp.route('/vtxos/create', methods=['POST'])
def create_rgb_vtxo():
    """Create a VTXO specifically for RGB allocations"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        # Validate required fields
        required_fields = ['user_pubkey', 'asset_id', 'amount_sats', 'rgb_contract_id']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400

        vtxo_manager = get_vtxo_manager()
        vtxo = vtxo_manager.create_rgb_vtxo(
            data['user_pubkey'],
            data['asset_id'],
            data['amount_sats'],
            data['rgb_contract_id'],
            data.get('rgb_allocation_data')
        )

        if not vtxo:
            return jsonify({'error': 'Failed to create RGB VTXO'}), 500

        return jsonify({
            'success': True,
            'data': {
                'vtxo_id': vtxo.vtxo_id,
                'txid': vtxo.txid,
                'vout': vtxo.vout,
                'amount_sats': vtxo.amount_sats,
                'asset_id': vtxo.asset_id,
                'rgb_asset_type': vtxo.rgb_asset_type,
                'rgb_allocation_id': vtxo.rgb_allocation_id,
                'status': vtxo.status,
                'created_at': vtxo.created_at.isoformat()
            },
            'message': f"RGB VTXO {vtxo.vtxo_id} created successfully"
        }), 201

    except Exception as e:
        logger.error(f"❌ Failed to create RGB VTXO: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@rgb_bp.route('/vtxos/<vtxo_id>/split', methods=['POST'])
def split_rgb_vtxo(vtxo_id: str):
    """Split an RGB VTXO into multiple VTXOs with corresponding allocations"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        # Validate required fields
        if 'split_amounts' not in data:
            return jsonify({'error': 'Missing required field: split_amounts'}), 400

        split_amounts = data['split_amounts']
        if not isinstance(split_amounts, list) or len(split_amounts) == 0:
            return jsonify({'error': 'split_amounts must be a non-empty list'}), 400

        vtxo_manager = get_vtxo_manager()
        success = vtxo_manager.split_rgb_vtxo(
            vtxo_id,
            split_amounts,
            data.get('rgb_allocation_splits')
        )

        if not success:
            return jsonify({'error': 'Failed to split RGB VTXO'}), 500

        return jsonify({
            'success': True,
            'message': f"RGB VTXO {vtxo_id} split successfully into {len(split_amounts)} VTXOs"
        }), 200

    except Exception as e:
        logger.error(f"❌ Failed to split RGB VTXO: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@rgb_bp.route('/vtxos/user/<user_pubkey>', methods=['GET'])
def get_user_rgb_vtxos(user_pubkey: str):
    """Get all RGB VTXOs for a user, optionally filtered by contract"""
    try:
        contract_id = request.args.get('contract_id')

        vtxo_manager = get_vtxo_manager()
        vtxos = vtxo_manager.get_user_rgb_vtxos(user_pubkey, contract_id)

        result = []
        for vtxo in vtxos:
            result.append({
                'vtxo_id': vtxo.vtxo_id,
                'txid': vtxo.txid,
                'vout': vtxo.vout,
                'amount_sats': vtxo.amount_sats,
                'asset_id': vtxo.asset_id,
                'rgb_asset_type': vtxo.rgb_asset_type,
                'rgb_allocation_id': vtxo.rgb_allocation_id,
                'status': vtxo.status,
                'created_at': vtxo.created_at.isoformat(),
                'expires_at': vtxo.expires_at.isoformat()
            })

        return jsonify({
            'success': True,
            'data': result,
            'count': len(result)
        }), 200

    except Exception as e:
        logger.error(f"❌ Failed to get user RGB VTXOs: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@rgb_bp.route('/vtxos/<vtxo_id>/validate', methods=['GET'])
def validate_rgb_vtxo_state(vtxo_id: str):
    """Validate the RGB state of a VTXO"""
    try:
        vtxo_manager = get_vtxo_manager()
        result = vtxo_manager.validate_rgb_vtxo_state(vtxo_id)

        return jsonify({
            'success': True,
            'data': result
        }), 200

    except Exception as e:
        logger.error(f"❌ Failed to validate RGB VTXO state: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@rgb_bp.route('/proofs/validate', methods=['POST'])
def validate_rgb_proof():
    """Validate RGB proof data against contract"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        # Validate required fields
        required_fields = ['proof_data', 'contract_id']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400

        rgb_manager = get_rgb_manager()
        is_valid = rgb_manager.validate_rgb_proof(data['proof_data'], data['contract_id'])

        return jsonify({
            'success': True,
            'data': {
                'valid': is_valid,
                'contract_id': data['contract_id']
            },
            'message': f"RGB proof is {'valid' if is_valid else 'invalid'}"
        }), 200

    except Exception as e:
        logger.error(f"❌ Failed to validate RGB proof: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@rgb_bp.route('/stats', methods=['GET'])
def get_rgb_stats():
    """Get RGB system statistics"""
    try:
        rgb_manager = get_rgb_manager()
        stats = rgb_manager.get_rgb_stats()

        return jsonify({
            'success': True,
            'data': stats
        }), 200

    except Exception as e:
        logger.error(f"❌ Failed to get RGB stats: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@rgb_bp.route('/health', methods=['GET'])
def rgb_health_check():
    """RGB service health check"""
    try:
        rgb_manager = get_rgb_manager()
        stats = rgb_manager.get_rgb_stats()

        # Check if RGB manager is functioning
        is_healthy = 'error' not in stats

        return jsonify({
            'status': 'healthy' if is_healthy else 'unhealthy',
            'timestamp': stats.get('timestamp'),
            'contracts_count': stats.get('contracts', {}).get('total', 0),
            'allocations_count': stats.get('allocations', {}).get('total', 0)
        }), 200 if is_healthy else 503

    except Exception as e:
        logger.error(f"❌ RGB health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 503

# Error handlers
@rgb_bp.errorhandler(400)
def bad_request(error):
    return jsonify({'error': 'Bad request'}), 400

@rgb_bp.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Resource not found'}), 404

@rgb_bp.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500
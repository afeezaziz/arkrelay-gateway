"""Add RGB support to Ark Relay Gateway

Revision ID: add_rgb_support
Revises: e25db603fb30
Create Date: 2025-09-30 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'add_rgb_support'
down_revision = 'e25db603fb30'
branch_labels = None
depends_on = None


def upgrade():
    """Add RGB support to existing tables and create new RGB tables"""

    # Add RGB columns to assets table
    op.add_column('assets', sa.Column('rgb_contract_id', sa.String(64), nullable=True))
    op.add_column('assets', sa.Column('rgb_schema_type', sa.String(50), nullable=True))
    op.add_column('assets', sa.Column('rgb_genesis_proof', sa.Text(), nullable=True))
    op.add_column('assets', sa.Column('rgb_interface_id', sa.String(64), nullable=True))
    op.add_column('assets', sa.Column('rgb_specification_id', sa.String(64), nullable=True))
    op.add_column('assets', sa.Column('is_rgb_enabled', sa.Boolean(), nullable=False, server_default='0'))

    # Add RGB columns to vtxos table
    op.add_column('vtxos', sa.Column('rgb_asset_type', sa.String(20), nullable=True))
    op.add_column('vtxos', sa.Column('rgb_proof_data', sa.Text(), nullable=True))
    op.add_column('vtxos', sa.Column('rgb_state_commitment', sa.LargeBinary(), nullable=True))
    op.add_column('vtxos', sa.Column('rgb_contract_state', sa.JSON(), nullable=True))
    op.add_column('vtxos', sa.Column('rgb_allocation_id', sa.String(64), nullable=True))

    # Create rgb_contracts table
    op.create_table('rgb_contracts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contract_id', sa.String(64), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('interface_id', sa.String(64), nullable=False),
        sa.Column('specification_id', sa.String(64), nullable=False),
        sa.Column('genesis_proof', sa.Text(), nullable=False),
        sa.Column('schema_type', sa.String(50), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('creator_pubkey', sa.String(66), nullable=True),
        sa.Column('total_issued', sa.BigInteger(), nullable=False),
        sa.Column('current_state_root', sa.String(64), nullable=True),
        sa.Column('last_transition_txid', sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('contract_id')
    )
    op.create_index(op.f('ix_rgb_contracts_contract_id'), 'rgb_contracts', ['contract_id'], unique=False)
    op.create_index(op.f('ix_rgb_contracts_is_active'), 'rgb_contracts', ['is_active'], unique=False)

    # Create rgb_allocations table
    op.create_table('rgb_allocations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('allocation_id', sa.String(64), nullable=False),
        sa.Column('contract_id', sa.String(64), nullable=False),
        sa.Column('vtxo_id', sa.String(64), nullable=False),
        sa.Column('owner_pubkey', sa.String(66), nullable=False),
        sa.Column('amount', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('state_commitment', sa.LargeBinary(), nullable=True),
        sa.Column('proof_data', sa.Text(), nullable=True),
        sa.Column('seal_type', sa.String(20), nullable=False),
        sa.Column('is_spent', sa.Boolean(), nullable=False),
        sa.Column('spent_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['contract_id'], ['rgb_contracts.contract_id'], ),
        sa.ForeignKeyConstraint(['vtxo_id'], ['vtxos.vtxo_id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('allocation_id')
    )
    op.create_index(op.f('ix_rgb_allocations_allocation_id'), 'rgb_allocations', ['allocation_id'], unique=False)
    op.create_index(op.f('ix_rgb_allocations_contract_id'), 'rgb_allocations', ['contract_id'], unique=False)
    op.create_index(op.f('ix_rgb_allocations_is_spent'), 'rgb_allocations', ['is_spent'], unique=False)
    op.create_index(op.f('ix_rgb_allocations_owner_pubkey'), 'rgb_allocations', ['owner_pubkey'], unique=False)
    op.create_index(op.f('ix_rgb_allocations_vtxo_id'), 'rgb_allocations', ['vtxo_id'], unique=False)


def downgrade():
    """Remove RGB support"""

    # Drop RGB tables
    op.drop_index(op.f('ix_rgb_allocations_vtxo_id'), table_name='rgb_allocations')
    op.drop_index(op.f('ix_rgb_allocations_owner_pubkey'), table_name='rgb_allocations')
    op.drop_index(op.f('ix_rgb_allocations_is_spent'), table_name='rgb_allocations')
    op.drop_index(op.f('ix_rgb_allocations_contract_id'), table_name='rgb_allocations')
    op.drop_index(op.f('ix_rgb_allocations_allocation_id'), table_name='rgb_allocations')
    op.drop_table('rgb_allocations')

    op.drop_index(op.f('ix_rgb_contracts_is_active'), table_name='rgb_contracts')
    op.drop_index(op.f('ix_rgb_contracts_contract_id'), table_name='rgb_contracts')
    op.drop_table('rgb_contracts')

    # Remove RGB columns from vtxos table
    op.drop_column('vtxos', 'rgb_allocation_id')
    op.drop_column('vtxos', 'rgb_contract_state')
    op.drop_column('vtxos', 'rgb_state_commitment')
    op.drop_column('vtxos', 'rgb_proof_data')
    op.drop_column('vtxos', 'rgb_asset_type')

    # Remove RGB columns from assets table
    op.drop_column('assets', 'is_rgb_enabled')
    op.drop_column('assets', 'rgb_specification_id')
    op.drop_column('assets', 'rgb_interface_id')
    op.drop_column('assets', 'rgb_genesis_proof')
    op.drop_column('assets', 'rgb_schema_type')
    op.drop_column('assets', 'rgb_contract_id')
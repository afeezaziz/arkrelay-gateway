"""
gRPC Client Package for Ark Relay Gateway

This package provides unified gRPC client interfaces for communicating with
ARKD, TAPD, and LND daemons.
"""

from .grpc_client import GrpcClientManager, get_grpc_manager, ServiceType, ConnectionConfig, CircuitBreaker, CircuitBreakerState
from .arkd_client import ArkdClient, VtxoInfo, ArkTransaction, SigningRequest
from .tapd_client import TapdClient, AssetInfo, AssetBalance, AssetProof, LightningInvoice
from .lnd_client import LndClient, LightningBalance, OnchainBalance, ChannelInfo, Payment

__all__ = [
    # Core interfaces
    'GrpcClientManager',
    'get_grpc_manager',
    'ServiceType',
    'ConnectionConfig',
    'CircuitBreaker',
    'CircuitBreakerState',

    # ARKD client
    'ArkdClient',
    'VtxoInfo',
    'ArkTransaction',
    'SigningRequest',

    # TAPD client
    'TapdClient',
    'AssetInfo',
    'AssetBalance',
    'AssetProof',
    'LightningInvoice',

    # LND client
    'LndClient',
    'LightningBalance',
    'OnchainBalance',
    'ChannelInfo',
    'Payment',
]
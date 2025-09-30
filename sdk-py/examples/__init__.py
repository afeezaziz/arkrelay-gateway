"""
ArkRelay SDK Examples

This package contains comprehensive examples for using the ArkRelay Python SDK.
"""

from pathlib import Path

# Get the gateway root directory
GATEWAY_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = GATEWAY_ROOT / "examples"

# Make examples available for import
__all__ = [
    "LightningOperationsDemo",
    "VtxoSplitOperationsDemo",
    "ServiceRequestDemo"
]

# Import example classes when available
try:
    import sys
    if str(EXAMPLES_DIR) not in sys.path:
        sys.path.insert(0, str(EXAMPLES_DIR))

    from service_requests import ServiceRequestDemo
    from lightning_operations import LightningOperationsDemo
    from vtxo_split_operations import VtxoSplitOperationsDemo
except ImportError:
    # Examples not available in installed package
    # This happens when installed via PyPI
    pass

def run_example(name: str, **kwargs):
    """
    Run an example by name

    Args:
        name: Example name ('lightning', 'vtxo', 'service')
        **kwargs: Arguments to pass to the example
    """
    if name == "lightning":
        demo = LightningOperationsDemo(kwargs.get("gateway_url", "http://localhost:8000"))
        return demo.execute_lift_flow(kwargs.get("amount", 100000), kwargs.get("asset_id", "gBTC"))
    elif name == "vtxo":
        demo = VtxoSplitOperationsDemo(kwargs.get("gateway_url", "http://localhost:8000"))
        return demo.execute_multi_vtxo_flow(
            kwargs.get("asset_id", "gUSD"),
            kwargs.get("amount", 400000000),
            kwargs.get("recipient", "npub1recipient...")
        )
    elif name == "service":
        demo = ServiceRequestDemo(
            kwargs.get("gateway_url", "http://localhost:8000"),
            kwargs.get("user_npub", "npub1user..."),
            kwargs.get("gateway_npub", "npub1gateway...")
        )
        return demo.execute_sync_state_flow()
    else:
        raise ValueError(f"Unknown example: {name}")

def list_examples():
    """List available examples"""
    return {
        "lightning": "Lightning operations (lift/land)",
        "vtxo": "VTXO operations (split, multi-vTXO, change)",
        "service": "Service request patterns (31500/31501/31502)"
    }
# Phase 5 Test Guide

## Overview

This document provides comprehensive testing guidance for Phase 5 of the Ark Relay Gateway implementation, which includes Core Business Logic functionality.

## Test Coverage

### 1. Transaction Processor Tests (`test_transaction_processor.py`)

**Coverage Areas:**
- P2P transfer processing
- Transaction validation and fee calculation
- Transaction broadcasting and status tracking
- User transaction history management
- Balance updates with pending/reserved states
- Error handling for various failure scenarios

**Key Test Cases:**
- `test_process_p2p_transfer_success`: Successful P2P transfer
- `test_process_p2p_transfer_insufficient_funds`: Insufficient balance handling
- `test_validate_transaction_valid`: Transaction validation
- `test_broadcast_transaction_success`: Transaction broadcasting
- `test_get_transaction_status_broadcast`: Transaction status tracking
- `test_confirm_transaction_success`: Transaction confirmation

### 2. Signing Orchestrator Tests (`test_signing_orchestrator.py`)

**Coverage Areas:**
- 6-step signing ceremony orchestration
- Intent verification and validation
- ARK and checkpoint transaction preparation
- Signature collection from multiple parties
- Ark protocol execution
- Ceremony finalization and error handling
- Timeout management and ceremony cancellation

**Key Test Cases:**
- `test_start_signing_ceremony_success`: Ceremony initiation
- `test_execute_signing_step_intent_verification_success`: Intent verification
- `test_execute_signing_step_ark_transaction_prep_success`: ARK transaction prep
- `test_execute_signing_step_signature_collection_success`: Signature collection
- `test_execute_signing_step_finalization_success`: Ceremony finalization
- `test_cancel_ceremony_success`: Ceremony cancellation

### 3. Asset Manager Tests (`test_asset_manager.py`)

**Coverage Areas:**
- Asset creation and management
- Asset balance tracking with reserves
- Asset transfers between users
- VTXO lifecycle management
- Reserve requirements calculation
- Asset statistics and reporting
- Expired VTXO cleanup

**Key Test Cases:**
- `test_create_asset_success`: Asset creation
- `test_mint_assets_success`: Asset minting
- `test_transfer_assets_success`: Asset transfers
- `test_manage_vtxos_create`: VTXO creation
- `test_get_asset_stats`: Asset statistics
- `test_get_reserve_requirements`: Reserve calculations

### 4. Integration Tests (`test_phase5_integration.py`)

**Coverage Areas:**
- API endpoint functionality
- Complete workflow testing
- Error handling at API level
- Request/response validation
- Authentication and authorization

**Key Test Cases:**
- `test_process_p2p_transfer_endpoint`: P2P transfer API
- `test_start_signing_ceremony_endpoint`: Ceremony start API
- `test_create_asset_endpoint`: Asset creation API
- `test_complete_p2p_transfer_flow`: Complete workflow integration

## Running Tests

### Individual Test Files

```bash
# Run transaction processor tests
python -m pytest tests/test_transaction_processor.py -v

# Run signing orchestrator tests
python -m pytest tests/test_signing_orchestrator.py -v

# Run asset manager tests
python -m pytest tests/test_asset_manager.py -v

# Run integration tests
python -m pytest tests/test_phase5_integration.py -v
```

### Complete Test Suite

```bash
# Run all Phase 5 tests
python tests/run_tests.py

# Run with coverage
python -m pytest tests/ --cov=. --cov-report=html
```

### Specific Test Categories

```bash
# Run only unit tests
python -m pytest tests/ -k "not integration" -v

# Run only integration tests
python -m pytest tests/ -k "integration" -v

# Run tests with specific markers
python -m pytest tests/ -m "slow" -v
```

## Test Data Setup

### Required Test Data

1. **Test Assets**: BTC, ETH, and test assets
2. **Test Users**: Multiple user public keys
3. **Test Balances**: Initial asset balances
4. **Test Sessions**: Various session types
5. **Test VTXOs**: Sample VTXOs for testing

### Database Setup

Tests will automatically create and clean up test data. However, ensure:

1. Database is accessible
2. Test environment has proper permissions
3. Redis is running for caching
4. gRPC mock services are available

## Test Configuration

### Environment Variables

```bash
# Test database configuration
export TEST_DATABASE_URL="sqlite:///test_arkrelay.db"

# Redis configuration for testing
export TEST_REDIS_URL="redis://localhost:6379/1"

# gRPC service endpoints (can be mocked)
export TEST_ARKD_ENDPOINT="localhost:10009"
export TEST_TAPD_ENDPOINT="localhost:10010"
export TEST_LND_ENDPOINT="localhost:10011"
```

### Mock Services

The test suite includes comprehensive mocking for:

1. **gRPC Clients**: ARKD, TAPD, LND services
2. **External APIs**: Blockchain explorers, fee estimators
3. **Nostr Services**: Relays and event handling
4. **Cryptographic Operations**: Signing and verification

## Test Scenarios

### Happy Path Scenarios

1. **Complete P2P Transfer Flow**
   - Asset creation → User funding → Session creation → Signing ceremony → Transaction broadcast → Confirmation

2. **Asset Management Workflow**
   - Asset creation → Minting → Balance checking → Transfer → Reserve validation

3. **Signing Ceremony Flow**
   - Session creation → Challenge generation → Signature collection → Protocol execution → Finalization

### Error Scenarios

1. **Insufficient Funds**: Transfer attempts with inadequate balance
2. **Invalid Transactions**: Malformed transaction data
3. **Ceremony Timeouts**: Operations exceeding time limits
4. **Network Failures**: gRPC service unavailability
5. **Validation Failures**: Invalid signatures, malformed data

### Edge Cases

1. **Concurrent Operations**: Multiple simultaneous transfers
2. **Large Amounts**: Transfers approaching supply limits
3. **Expired Sessions**: Operations on expired sessions
4. **Reserved Balances**: Transfers affecting reserved funds

## Performance Testing

### Load Testing Scenarios

```python
# High-frequency transaction processing
def test_high_frequency_transfers():
    # Test rapid succession of P2P transfers

# Large-scale asset management
def test_large_asset_balances():
    # Test handling of large asset balances

# Concurrent signing ceremonies
def test_concurrent_ceremonies():
    # Test multiple simultaneous ceremonies
```

### Performance Metrics

- Transaction processing speed
- Ceremony completion time
- Asset transfer throughput
- API response times
- Database query performance

## Debugging Tests

### Common Issues

1. **Database Connection**: Ensure test database is accessible
2. **Missing Dependencies**: Install required packages with `pip install -e .`
3. **Port Conflicts**: Ensure test ports are available
4. **Permission Issues**: Verify file and database permissions

### Debug Commands

```bash
# Run tests with verbose output
python -m pytest tests/ -v -s

# Run specific test with debugging
python -m pytest tests/test_transaction_processor.py::TestTransactionProcessor::test_process_p2p_transfer_success -v -s

# Check test coverage
python -m pytest tests/ --cov=. --cov-report=term-missing
```

### Test Debugging Tips

1. Use `print()` statements for debugging test flow
2. Check database state after test runs
3. Verify mock service configurations
4. Inspect request/response payloads
5. Validate environment variables

## Continuous Integration

### GitHub Actions Integration

The test suite is designed to run in CI/CD environments:

```yaml
- name: Run Phase 5 Tests
  run: |
    python -m pytest tests/test_transaction_processor.py -v
    python -m pytest tests/test_signing_orchestrator.py -v
    python -m pytest tests/test_asset_manager.py -v
    python -m pytest tests/test_phase5_integration.py -v
```

### Test Reporting

Generate comprehensive test reports:

```bash
# HTML coverage report
python -m pytest tests/ --cov=. --cov-report=html

# JUnit XML report for CI
python -m pytest tests/ --junitxml=reports/test-results.xml
```

## Test Maintenance

### Adding New Tests

1. Follow the existing naming convention: `test_*.py`
2. Use pytest fixtures for common setup
3. Include comprehensive assertions
4. Add proper error handling
5. Document test scenarios

### Test Data Management

1. Use fixtures for test data setup
2. Clean up after tests complete
3. Isolate test data from production
4. Use transactions for data consistency

### Mock Strategy

1. Mock external dependencies
2. Use realistic mock responses
3. Test both success and failure cases
4. Verify mock interactions

## Conclusion

Phase 5 testing provides comprehensive coverage of the Core Business Logic functionality. The test suite ensures reliability, correctness, and performance of all implemented features while maintaining flexibility for future enhancements.
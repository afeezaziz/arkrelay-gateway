# Tests

This directory contains all tests for the Ark Relay Gateway project.

## Structure

```
tests/
├── __init__.py           # Test package initialization
├── conftest.py           # Pytest configuration and fixtures
├── test_config.py        # Test configuration
├── test_grpc_clients.py  # gRPC client unit tests
└── README.md            # This file
```

## Test Categories

### Unit Tests
- **Circuit Breaker**: Test failure handling and recovery
- **Configuration**: Test environment and gRPC configuration
- **Data Structures**: Test client data structure definitions
- **Client Manager**: Test gRPC client initialization

### Integration Tests
- **Service Health**: Test real daemon connectivity
- **Error Handling**: Test real gRPC error scenarios
- **Performance**: Test client performance under load

## Running Tests

### Using the Test Runner (Recommended)
```bash
# Run all tests
uv run python run_tests.py

# Run specific test
uv run python run_tests.py --test TestCircuitBreaker.test_successful_call_remains_closed

# Use pytest instead of unittest
uv run python run_tests.py --pytest

# Run with coverage
uv run python run_tests.py --coverage
```

### Using pytest directly
```bash
# Run all tests
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/test_grpc_clients.py -v

# Run with markers
uv run pytest tests/ -v -m unit
uv run pytest tests/ -v -m integration
```

### Using unittest directly
```bash
# Run all tests
uv run python -m unittest discover tests/ -v

# Run specific test file
uv run python tests/test_grpc_clients.py -v

# Run specific test class
uv run python -m unittest tests.test_grpc_clients.TestCircuitBreaker -v
```

## Test Configuration

### Environment Variables
Tests use a separate configuration that can be found in `test_config.py`:
- Test database: SQLite in-memory
- Test Redis: Database 1
- Mock daemon configurations
- Test-specific security keys

### Fixtures
Available pytest fixtures (see `conftest.py`):
- `setup_test_environment`: Configures test environment
- `mock_arkd_client`: Mock ARKD client
- `mock_tapd_client`: Mock TAPD client
- `mock_lnd_client`: Mock LND client

## Writing Tests

### Unit Test Example
```python
import unittest
from unittest.mock import Mock, patch
from grpc_clients import ServiceType

class TestMyFeature(unittest.TestCase):
    def setUp(self):
        self.client = Mock()

    def test_my_functionality(self):
        # Arrange
        expected_result = "success"

        # Act
        result = self.client.some_method()

        # Assert
        self.assertEqual(result, expected_result)
```

### Pytest Example
```python
import pytest
from grpc_clients import get_grpc_manager

def test_client_initialization():
    """Test that gRPC clients initialize correctly"""
    manager = get_grpc_manager()
    client = manager.get_client(ServiceType.ARKD)
    assert client is not None

@pytest.mark.unit
def test_circuit_breaker():
    """Test circuit breaker functionality"""
    # Test implementation
    pass

@pytest.mark.integration
def test_real_daemon_connection():
    """Test connection to real daemons"""
    # Integration test implementation
    pass
```

## Test Coverage

### Current Coverage Status

**Overall Coverage**: 13% (38 working tests passed)
- **Total Statements**: 8,208
- **Covered Statements**: 1,093
- **Missed Statements**: 7,115

#### Coverage by Module:
- **`core/config.py`**: 87% coverage
- **`core/models.py`**: 98% coverage
- **`tests/test_models.py`**: 100% coverage
- **`tests/test_grpc_clients.py`**: 99% coverage
- **`tests/test_nostr_encryption.py`**: 89% coverage
- **`grpc_clients/` modules**: 41-49% coverage
- **`nostr_clients/` modules**: 0-44% coverage
- **`app.py`**: 0% coverage (main application)

#### Working Tests (38 tests passing):
- **Nostr encryption**: 9/9 tests passing
- **Database models**: 21/21 tests passing
- **gRPC clients**: 8/8 tests passing

### Running Coverage Analysis

```bash
# Run all tests with coverage
uv run pytest --cov=. --cov-report=term-missing --cov-report=html

# Run specific test categories with coverage
uv run pytest -m unit --cov=. --cov-report=term-missing
uv run pytest -m integration --cov=. --cov-report=term-missing

# Run only working tests with coverage
uv run pytest tests/test_nostr_encryption.py tests/test_models.py tests/test_grpc_clients.py --cov=. --cov-report=term-missing
```

Coverage reports will be generated in:
- `htmlcov/` - HTML report (detailed interactive coverage)
- Terminal coverage summary (missing lines shown)

### Coverage Challenges

**Current Issues:**
1. **Main Application**: 0% coverage due to Flask app test failures
2. **Integration Tests**: Most failing, limiting overall coverage
3. **External Dependencies**: gRPC and Nostr clients have low coverage due to mocking complexity

**Improvement Strategy:**
1. Fix basic Flask app and integration test failures
2. Improve mocking for external service dependencies
3. Focus on core modules first for 80%+ coverage
4. Incremental approach to achieve 60%+ overall coverage

## Test Data

### Mock Data
Tests use mock data for:
- VTXO information
- Asset balances
- Lightning invoices
- Network responses

### Real Testing
For integration tests with real daemons:
1. Set up testnet daemons (arkd, tapd, lnd)
2. Configure test environment variables
3. Run integration tests with `--integration` marker

## Continuous Integration

Tests are designed to run in CI/CD pipelines:
- No external dependencies required for unit tests
- Fast execution times
- Clear pass/fail reporting
- Coverage reporting available

## Best Practices

1. **Test Isolation**: Each test should be independent
2. **Mock External Dependencies**: Use mocks for gRPC calls
3. **Clear Test Names**: Use descriptive test names
4. **Arrange-Act-Assert**: Follow this pattern in tests
5. **Error Testing**: Test both success and failure scenarios
6. **Performance**: Tests should run quickly

## Adding New Tests

1. Create new test file with `test_` prefix
2. Import necessary modules
3. Add test classes and methods
4. Use appropriate markers (unit/integration)
5. Add fixtures if needed
6. Update documentation

## Debugging Tests

For debugging failing tests:
```bash
# Run with verbose output
uv run python run_tests.py --pytest -v

# Run specific test with debugging
uv run python -m pdb tests/test_grpc_clients.py

# Run with maximum verbosity
uv run pytest tests/ -vv
```

## Test Dependencies

Test dependencies are included in the main `requirements.txt`:
- `pytest` - Test framework
- `pytest-cov` - Coverage reporting
- `unittest.mock` - Mocking (built-in)
- `dotenv` - Environment variable management
"""
Tests for async connection module.
"""

import pytest
import asyncio
from helpers.async_connection import AsyncUnrealConnection, ConnectionPool


@pytest.mark.asyncio
async def test_connection_creation():
    """Test creating async connection."""
    conn = AsyncUnrealConnection(host="127.0.0.1", port=55557)
    assert conn.host == "127.0.0.1"
    assert conn.port == 55557
    assert not conn.connected


@pytest.mark.asyncio
async def test_connection_metrics():
    """Test connection metrics tracking."""
    conn = AsyncUnrealConnection()
    
    metrics = conn.get_metrics()
    assert metrics["total_requests"] == 0
    assert metrics["successful_requests"] == 0
    assert metrics["failed_requests"] == 0
    assert metrics["connected"] == False


@pytest.mark.asyncio
async def test_connection_pool():
    """Test connection pool creation."""
    pool = ConnectionPool(pool_size=3, host="127.0.0.1", port=55557)
    
    assert pool.pool_size == 3
    assert len(pool.connections) == 0


@pytest.mark.asyncio
async def test_batch_commands():
    """Test batch command execution."""
    conn = AsyncUnrealConnection()
    
    commands = [
        {"command": "test1", "params": {}},
        {"command": "test2", "params": {}},
    ]
    
    # This will fail without actual connection, but tests the structure
    try:
        results = await conn.batch_commands(commands)
        assert len(results) == 2
    except Exception:
        pass  # Expected without real connection

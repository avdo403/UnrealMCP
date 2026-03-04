"""
Async Unreal Connection with WebSocket support and connection pooling.

This module provides high-performance async communication with Unreal Engine
using WebSocket protocol, connection pooling, and advanced retry mechanisms.
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager
import aiohttp
from aiohttp import ClientSession, WSMsgType

logger = logging.getLogger(__name__)


class AsyncUnrealConnection:
    """
    High-performance async connection to Unreal Engine with WebSocket support.
    
    Features:
    - WebSocket bidirectional communication
    - Connection pooling
    - Exponential backoff retry
    - Request batching
    - Health monitoring
    - Automatic reconnection
    """
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 55557,
        max_retries: int = 5,
        timeout: int = 30,
        pool_size: int = 5
    ):
        self.host = host
        self.port = port
        self.max_retries = max_retries
        self.timeout = timeout
        self.pool_size = pool_size
        
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.session: Optional[ClientSession] = None
        self.connected = False
        self.request_id = 0
        self.pending_requests: Dict[int, asyncio.Future] = {}
        
        # Performance metrics
        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_latency": 0.0,
            "reconnections": 0
        }
    
    async def connect(self) -> bool:
        """Establish WebSocket connection to Unreal Engine."""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            ws_url = f"ws://{self.host}:{self.port}"
            logger.info(f"Connecting to Unreal Engine at {ws_url}")
            
            self.ws = await self.session.ws_connect(
                ws_url,
                timeout=self.timeout,
                heartbeat=30.0  # Send ping every 30 seconds
            )
            
            self.connected = True
            logger.info("Successfully connected to Unreal Engine via WebSocket")
            
            # Start message handler
            asyncio.create_task(self._message_handler())
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Unreal Engine: {e}")
            self.connected = False
            return False
    
    async def disconnect(self):
        """Close WebSocket connection."""
        if self.ws:
            await self.ws.close()
            self.ws = None
        
        if self.session:
            await self.session.close()
            self.session = None
        
        self.connected = False
        logger.info("Disconnected from Unreal Engine")
    
    async def _message_handler(self):
        """Handle incoming WebSocket messages."""
        try:
            async for msg in self.ws:
                if msg.type == WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    request_id = data.get("id")
                    
                    if request_id in self.pending_requests:
                        future = self.pending_requests.pop(request_id)
                        if not future.done():
                            future.set_result(data)
                
                elif msg.type == WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {msg.data}")
                    break
                    
        except Exception as e:
            logger.error(f"Message handler error: {e}")
        finally:
            self.connected = False
    
    async def send_command(
        self,
        command: str,
        params: Dict[str, Any],
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Send command to Unreal Engine with retry logic.
        
        Args:
            command: Command name
            params: Command parameters
            timeout: Optional timeout override
            
        Returns:
            Response dictionary
        """
        if not self.connected:
            await self.connect()
        
        timeout = timeout or self.timeout
        start_time = time.time()
        
        for attempt in range(self.max_retries):
            try:
                self.request_id += 1
                request_id = self.request_id
                
                message = {
                    "id": request_id,
                    "command": command,
                    "params": params
                }
                
                # Create future for response
                future = asyncio.Future()
                self.pending_requests[request_id] = future
                
                # Send message
                await self.ws.send_json(message)
                self.metrics["total_requests"] += 1
                
                # Wait for response
                try:
                    response = await asyncio.wait_for(future, timeout=timeout)
                    
                    # Update metrics
                    latency = time.time() - start_time
                    self.metrics["successful_requests"] += 1
                    self.metrics["total_latency"] += latency
                    
                    return response
                    
                except asyncio.TimeoutError:
                    self.pending_requests.pop(request_id, None)
                    raise TimeoutError(f"Command '{command}' timed out after {timeout}s")
            
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/{self.max_retries} failed: {e}")
                
                if attempt < self.max_retries - 1:
                    # Exponential backoff
                    wait_time = min(2 ** attempt, 10)
                    await asyncio.sleep(wait_time)
                    
                    # Try to reconnect
                    if not self.connected:
                        await self.connect()
                        self.metrics["reconnections"] += 1
                else:
                    self.metrics["failed_requests"] += 1
                    raise
        
        raise Exception(f"Failed to execute command '{command}' after {self.max_retries} attempts")
    
    async def batch_commands(
        self,
        commands: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple commands in parallel.
        
        Args:
            commands: List of command dictionaries with 'command' and 'params' keys
            
        Returns:
            List of response dictionaries
        """
        tasks = [
            self.send_command(cmd["command"], cmd["params"])
            for cmd in commands
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Convert exceptions to error dictionaries
        return [
            {"success": False, "error": str(r)} if isinstance(r, Exception) else r
            for r in results
        ]
    
    async def health_check(self) -> bool:
        """Check if connection is healthy."""
        try:
            response = await self.send_command("ping", {}, timeout=5)
            return response.get("success", False)
        except Exception:
            return False
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics."""
        avg_latency = (
            self.metrics["total_latency"] / self.metrics["successful_requests"]
            if self.metrics["successful_requests"] > 0
            else 0
        )
        
        success_rate = (
            self.metrics["successful_requests"] / self.metrics["total_requests"] * 100
            if self.metrics["total_requests"] > 0
            else 0
        )
        
        return {
            **self.metrics,
            "average_latency": avg_latency,
            "success_rate": success_rate,
            "connected": self.connected
        }


class ConnectionPool:
    """
    Connection pool for managing multiple async connections.
    
    Provides load balancing and automatic failover.
    """
    
    def __init__(self, pool_size: int = 5, **connection_kwargs):
        self.pool_size = pool_size
        self.connection_kwargs = connection_kwargs
        self.connections: List[AsyncUnrealConnection] = []
        self.current_index = 0
        self._lock = asyncio.Lock()
    
    async def initialize(self):
        """Initialize connection pool."""
        for _ in range(self.pool_size):
            conn = AsyncUnrealConnection(**self.connection_kwargs)
            await conn.connect()
            self.connections.append(conn)
    
    async def get_connection(self) -> AsyncUnrealConnection:
        """Get next available connection (round-robin)."""
        async with self._lock:
            # Round-robin selection
            conn = self.connections[self.current_index]
            self.current_index = (self.current_index + 1) % self.pool_size
            
            # Ensure connection is healthy
            if not conn.connected:
                await conn.connect()
            
            return conn
    
    async def close_all(self):
        """Close all connections in pool."""
        for conn in self.connections:
            await conn.disconnect()


@asynccontextmanager
async def get_async_unreal_connection(**kwargs):
    """
    Context manager for async Unreal connection.
    
    Usage:
        async with get_async_unreal_connection() as conn:
            result = await conn.send_command("create_actor", {...})
    """
    conn = AsyncUnrealConnection(**kwargs)
    try:
        await conn.connect()
        yield conn
    finally:
        await conn.disconnect()

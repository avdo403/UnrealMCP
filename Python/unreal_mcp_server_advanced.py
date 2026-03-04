"""
Unreal Engine Advanced MCP Server

A streamlined MCP server focused on advanced composition tools for Unreal Engine.
Contains only the advanced tools from the expanded MCP tool system to keep tool count manageable.
"""

import logging
import socket
import json
import math
import struct
import time
import threading
import io
import contextlib
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any, Optional, List
from mcp.server.fastmcp import FastMCP

from helpers.infrastructure_creation import (
    _create_street_grid, _create_street_lights, _create_town_vehicles, _create_town_decorations,
    _create_traffic_lights, _create_street_signage, _create_sidewalks_crosswalks, _create_urban_furniture,
    _create_street_utilities, _create_central_plaza
)
from helpers.building_creation import _create_town_building
from helpers.castle_creation import (
    get_castle_size_params, calculate_scaled_dimensions, build_outer_bailey_walls, 
    build_inner_bailey_walls, build_gate_complex, build_corner_towers, 
    build_inner_corner_towers, build_intermediate_towers, build_central_keep, 
    build_courtyard_complex, build_bailey_annexes, build_siege_weapons, 
    build_village_settlement, build_drawbridge_and_moat, add_decorative_flags
)
from helpers.house_construction import build_house

from helpers.mansion_creation import (
    get_mansion_size_params, calculate_mansion_layout, build_mansion_main_structure,
    build_mansion_exterior, add_mansion_interior
)
from helpers.actor_utilities import spawn_blueprint_actor, get_blueprint_material_info
from helpers.actor_name_manager import (
    safe_spawn_actor, safe_delete_actor
)
from helpers.bridge_aqueduct_creation import (
    build_suspension_bridge_structure, build_aqueduct_structure
)

# ============================================================================
# Blueprint Node Graph Tools
# ============================================================================
from helpers.blueprint_graph import node_manager
from helpers.blueprint_graph import variable_manager
from helpers.blueprint_graph import connector_manager
from helpers.blueprint_graph import event_manager
from helpers.blueprint_graph import node_deleter
from helpers.blueprint_graph import node_properties
from helpers.blueprint_graph import function_manager
from helpers.blueprint_graph import function_io

# ============================================================================
# Advanced Helper Imports
# ============================================================================
from helpers.blueprint_analysis import (
    analyze_graph_complexity,
    find_graph_issues,
    trace_execution_path
)
from helpers.wave_function_collapse import (
    generate_dungeon_wfc,
    spawn_wfc_dungeon
)
from helpers.lsystem_generator import (
    generate_tree_lsystem,
    spawn_lsystem_tree
)
from helpers.mcp_resources import (
    get_blueprint_resource,
    get_level_actors_resource,
    get_project_assets_resource
)

# ============================================================================
# Code Execution Tools
# ============================================================================
from helpers.code_execution import (
    execute_python_code,
    create_execution_session,
    reset_execution_session,
    get_session_info
)



# Configure logging with more detailed format
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.FileHandler('unreal_mcp_advanced.log'),
    ]
)
logger = logging.getLogger("UnrealMCP_Advanced")

# Configuration
UNREAL_HOST = "127.0.0.1"
UNREAL_PORT = 55557

class UnrealConnection:
    """
    Robust connection to Unreal Engine with automatic retry and reconnection.
    
    Features:
    - Exponential backoff retry for connection attempts
    - Automatic reconnection on failure
    - Configurable timeouts per command type
    - Thread-safe operations
    - Detailed logging for debugging
    - Message framing protocol (length-prefixed)
    - Connection pooling (persistent connections)
    - Health check mechanism
    - Batch command support
    """
    
    # Configuration constants
    MAX_RETRIES = 3
    BASE_RETRY_DELAY = 0.5  # seconds
    MAX_RETRY_DELAY = 5.0   # seconds
    CONNECT_TIMEOUT = 2     # seconds (Reduced from 10)
    DEFAULT_RECV_TIMEOUT = 2   # seconds (Reduced from 30 to speed up retries)
    LARGE_OP_RECV_TIMEOUT = 300  # seconds for large operations
    BUFFER_SIZE = 8192
    HEALTH_CHECK_INTERVAL = 30  # seconds
    
    # Commands that need longer timeouts
    LARGE_OPERATION_COMMANDS = {
        "get_available_materials",
        "create_town",
        "create_castle_fortress", 
        "construct_mansion",
        "create_suspension_bridge",
        "create_aqueduct",
        "create_maze",
        "generate_dungeon_wfc",
        "spawn_wfc_dungeon",
        "generate_tree_lsystem",
        "spawn_lsystem_tree",
        "generate_vegetation_field",
        "analyze_blueprint_graph",
        "read_blueprint_content"
    }
    
    def __init__(self):
        """Initialize the connection."""
        self.socket = None
        self.connected = False
        self._lock = threading.RLock()  # RLock allows reentrant acquisition for retry logic
        self._last_error = None
        self._last_activity = 0  # Timestamp of last activity
    
    def _create_socket(self) -> socket.socket:
        """Create and configure a new socket."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.CONNECT_TIMEOUT)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 131072)  # 128KB
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 131072)  # 128KB
        
        # Set linger to ensure clean socket closure (l_onoff=1, l_linger=0)
        # struct linger is two 16-bit integers: l_onoff and l_linger
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('hh', 1, 0))
        except OSError:
            pass
        
        return sock
    
    def _ensure_connected(self) -> bool:
        """
        Ensure we have a valid connection to Unreal Engine.
        
        Returns:
            True if connected successfully, False otherwise
        """
        with self._lock:
            # If we're already connected, do a quick health check
            if self.connected and self.socket:
                if time.time() - self._last_activity > self.HEALTH_CHECK_INTERVAL:
                    if not self._health_check_unsafe():
                        logger.warning("Health check failed, reconnecting...")
                        self._close_socket_unsafe()
                        self.connected = False
            
            # If we're still connected, we're done
            if self.connected:
                return True
                
            # Otherwise, establish a new connection
            return self.connect()
    
    def _health_check_unsafe(self) -> bool:
        """
        Perform a health check without locking (internal use only).
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            # Send a ping command
            ping_command = {"type": "ping", "params": {}}
            ping_json = json.dumps(ping_command, separators=(',', ':')).encode('utf-8')
            
            # Send with length prefix
            message_length = len(ping_json)
            length_header = struct.pack('>I', message_length)
            
            self.socket.settimeout(5)  # 5 second timeout for health check
            self.socket.sendall(length_header)
            self.socket.sendall(ping_json)
            
            # Receive response with framing
            response_data = self._receive_response("ping")
            response = json.loads(response_data.decode('utf-8'))
            
            # Check if response is pong
            if response.get("result", {}).get("message") == "pong":
                self._last_activity = time.time()
                return True
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
        
        return False
    
    def connect(self) -> bool:
        """
        Connect to Unreal Engine with retry logic.
        
        Uses exponential backoff for retries. Sleep occurs outside the lock
        to avoid blocking other threads during retry delays.
            
        Returns:
            True if connected successfully, False otherwise
        """
        for attempt in range(self.MAX_RETRIES + 1):
            # Hold lock only during connection attempt, not during sleep
            with self._lock:
                # Clean up any existing connection
                self._close_socket_unsafe()
                
                try:
                    logger.info(f"Connecting to Unreal at {UNREAL_HOST}:{UNREAL_PORT} (attempt {attempt + 1}/{self.MAX_RETRIES + 1})...")
                    
                    self.socket = self._create_socket()
                    self.socket.connect((UNREAL_HOST, UNREAL_PORT))
                    self.connected = True
                    self._last_error = None
                    
                    logger.info("Successfully connected to Unreal Engine")
                    return True
                    
                except socket.timeout as e:
                    self._last_error = f"Connection timeout: {e}"
                    logger.warning(f"Connection timeout (attempt {attempt + 1})")
                except ConnectionRefusedError as e:
                    self._last_error = f"Connection refused: {e}"
                    logger.warning(f"Connection refused - is Unreal Engine running? (attempt {attempt + 1})")
                except OSError as e:
                    self._last_error = f"OS error: {e}"
                    logger.warning(f"OS error during connection: {e} (attempt {attempt + 1})")
                except Exception as e:
                    self._last_error = f"Unexpected error: {e}"
                    logger.error(f"Unexpected connection error: {e} (attempt {attempt + 1})")
                
                self._close_socket_unsafe()
                self.connected = False
            
            # Sleep OUTSIDE the lock to allow other threads to proceed
            if attempt < self.MAX_RETRIES:
                delay = min(self.BASE_RETRY_DELAY * (2 ** attempt), self.MAX_RETRY_DELAY)
                logger.info(f"Retrying connection in {delay:.1f}s...")
                time.sleep(delay)
        
        logger.error(f"Failed to connect after {self.MAX_RETRIES + 1} attempts. Last error: {self._last_error}")
        return False
    
    def _close_socket_unsafe(self):
        """Close socket without lock (internal use only)."""
        if self.socket:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except:
                pass
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        self.connected = False
    
    def disconnect(self):
        """Safely disconnect from Unreal Engine."""
        with self._lock:
            self._close_socket_unsafe()
            logger.debug("Disconnected from Unreal Engine")

    def _get_timeout_for_command(self, command_type: str) -> int:
        """Get appropriate timeout for command type."""
        if any(large_cmd in command_type for large_cmd in self.LARGE_OPERATION_COMMANDS):
            return self.LARGE_OP_RECV_TIMEOUT
        return self.DEFAULT_RECV_TIMEOUT

    def _receive_response(self, command_type: str) -> bytes:
        """
        Receive complete JSON response from Unreal with message framing.
        
        Args:
            command_type: Type of command (used for timeout selection)
            
        Returns:
            Raw response bytes
            
        Raises:
            Exception: On timeout or connection error
        """
        timeout = self._get_timeout_for_command(command_type)
        self.socket.settimeout(timeout)
        
        # First, read the 4-byte message length
        length_bytes = self._recv_exact(4)
        message_length = struct.unpack('>I', length_bytes)[0]  # Big-endian unsigned int
        logger.debug(f"Expecting message of length {message_length} bytes")
        
        # Validate message length to prevent excessive memory allocation
        if message_length <= 0 or message_length > 1024 * 1024 * 10:  # Max 10MB message
            raise ValueError(f"Invalid message length: {message_length}")
        
        # Read the complete message
        message_data = self._recv_exact(message_length)
        self._last_activity = time.time()
        
        logger.info(f"Received complete response ({len(message_data)} bytes) for {command_type}")
        return message_data
    
    def _recv_exact(self, num_bytes: int) -> bytes:
        """
        Receive exactly num_bytes from the socket.
        
        Args:
            num_bytes: Number of bytes to receive
            
        Returns:
            Received bytes
            
        Raises:
            ConnectionError: If connection is closed before receiving all bytes
        """
        chunks = []
        bytes_received = 0
        
        while bytes_received < num_bytes:
            try:
                chunk = self.socket.recv(num_bytes - bytes_received)
            except socket.timeout:
                raise TimeoutError(f"Timeout while receiving data ({bytes_received}/{num_bytes} bytes)")
            
            if not chunk:
                raise ConnectionError(f"Connection closed while receiving data ({bytes_received}/{num_bytes} bytes)")
            
            chunks.append(chunk)
            bytes_received += len(chunk)
        
        return b''.join(chunks)

    def send_command(self, command: str, params: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """
        Send a command to Unreal Engine with automatic retry.
        
        Args:
            command: Command type string
            params: Command parameters dictionary
            
        Returns:
            Response dictionary or error dictionary
        """
        last_error = None
        
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                return self._send_command_once(command, params, attempt)
            except (ConnectionError, TimeoutError, socket.error, OSError) as e:
                last_error = str(e)
                logger.warning(f"Command failed (attempt {attempt + 1}/{self.MAX_RETRIES + 1}): {e}")
                
                # Clean up and prepare for retry
                self.disconnect()
                
                if attempt < self.MAX_RETRIES:
                    delay = min(self.BASE_RETRY_DELAY * (2 ** attempt), self.MAX_RETRY_DELAY)
                    logger.info(f"Retrying command in {delay:.1f}s...")
                    time.sleep(delay)
            except Exception as e:
                # Unexpected error - don't retry
                logger.error(f"Unexpected error sending command: {e}")
                self.disconnect()
                return {"status": "error", "error": str(e)}
        
        return {"status": "error", "error": f"Command failed after {self.MAX_RETRIES + 1} attempts: {last_error}"}
    
    def send_batch_commands(self, commands: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        """
        Send multiple commands in a single request.
        
        Args:
            commands: List of command dictionaries with 'type' and 'params' keys
            
        Returns:
            List of response dictionaries or None on failure
        """
        batch_command = {
            "type": "batch",
            "params": {
                "commands": commands
            }
        }
        
        response = self.send_command("batch", {"commands": commands})
        if response and response.get("status") == "success":
            return response.get("result", [])
        return None
    
    def health_check(self) -> bool:
        """
        Perform a health check of the connection.
        
        Returns:
            True if healthy, False otherwise
        """
        with self._lock:
            if not self.connected or not self.socket:
                return False
            return self._health_check_unsafe()

    def _send_command_once(self, command: str, params: Dict[str, Any], attempt: int) -> Dict[str, Any]:
        """
        Send command once (internal method).
        
        Args:
            command: Command type
            params: Command parameters
            attempt: Current attempt number
            
        Returns:
            Response dictionary
            
        Raises:
            Various exceptions on failure
        """
        # Hold lock for entire send-receive cycle to prevent race conditions
        # where another thread could close/reconnect the socket mid-operation.
        # RLock allows nested acquisition from connect()/disconnect() calls.
        with self._lock:
            # Ensure we have a connection (with health check)
            if not self._ensure_connected():
                raise ConnectionError(f"Failed to connect to Unreal Engine: {self._last_error}")
            
            try:
                # Build and send command with message framing
                command_obj = {
                    "type": command,
                    "params": params or {}
                }
                command_json = json.dumps(command_obj, separators=(',', ':'))
                command_bytes = command_json.encode('utf-8')
                
                logger.info(f"Sending command (attempt {attempt + 1}): {command}")
                logger.debug(f"Command payload: {command_json[:500]}...")
                
                # Send with length prefix
                message_length = len(command_bytes)
                length_header = struct.pack('>I', message_length)
                
                self.socket.settimeout(10)  # 10 second send timeout
                self.socket.sendall(length_header)
                self.socket.sendall(command_bytes)
                self._last_activity = time.time()
                
                # Receive response with framing
                response_data = self._receive_response(command)
                
                # Parse response
                try:
                    response = json.loads(response_data.decode('utf-8'))
                    # Add a small delay to prevent overwhelming Unreal's socket server
                    time.sleep(0.05)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                    logger.debug(f"Raw response: {response_data[:500]}")
                    raise ValueError(f"Invalid JSON response: {e}")
                
                logger.info(f"Command {command} completed successfully")
                
                # Normalize error responses
                if response.get("status") == "error":
                    error_msg = response.get("error") or response.get("message", "Unknown error")
                    logger.warning(f"Unreal returned error: {error_msg}")
                elif response.get("success") is False:
                    error_msg = response.get("error") or response.get("message", "Unknown error")
                    response = {"status": "error", "error": error_msg}
                    logger.warning(f"Unreal returned failure: {error_msg}")
                
                return response
                
            except Exception:
                # On error, close connection so next command will reconnect
                self._close_socket_unsafe()
                raise
            # Note: We don't close the socket here anymore to enable connection pooling
            # The socket stays open for future commands

# Global connection instance (singleton pattern)
_unreal_connection: Optional[UnrealConnection] = None
_connection_lock = threading.Lock()

def get_unreal_connection() -> UnrealConnection:
    """
    Get the global Unreal connection instance.
    
    Uses lazy initialization - connection is created on first access.
    The connection handles its own retry logic, so we don't need to
    pre-connect here.
    
    Returns:
        UnrealConnection instance (always returns an instance, never None)
    """
    global _unreal_connection
    
    with _connection_lock:
        if _unreal_connection is None:
            logger.info("Creating new UnrealConnection instance")
            _unreal_connection = UnrealConnection()
        return _unreal_connection


def reset_unreal_connection():
    """Reset the global connection (useful for error recovery)."""
    global _unreal_connection
    
    with _connection_lock:
        if _unreal_connection:
            _unreal_connection.disconnect()
            _unreal_connection = None
        logger.info("Unreal connection reset")

def resolve_actor_name(unreal, name: str) -> str:
    """
    Resolve a potentially short actor name to its full name in the level.
    Unreal often adds suffixes like _UAID_... to actor names.
    This helper tries an exact match first, then a prefix match.
    """
    if not unreal:
        return name
        
    try:
        # 1. Try exact match first (using find_actors_by_name with precise pattern)
        response = unreal.send_command("find_actors_by_name", {"pattern": name})
        if response and response.get("status") == "success":
            actors = response.get("actors", [])
            # Search for exact match in results
            for actor in actors:
                if actor.get("name") == name:
                    return name
            
            # 2. If no exact match, try prefix match (name + "_")
            # Usually Unreal suffixes look like: Name_UAID_... or Name_C_...
            for actor in actors:
                actor_full_name = actor.get("name", "")
                if actor_full_name.startswith(name):
                    logger.info(f"Resolved short name '{name}' to full name '{actor_full_name}'")
                    return actor_full_name
                    
        return name # Return original if not found
    except Exception as e:
        logger.warning(f"Error resolving actor name '{name}': {e}")
        return name

@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    """Handle server startup and shutdown."""
    logger.info("UnrealMCP Advanced server starting up")
    logger.info("Connection will be established lazily on first tool call")

    try:
        yield {}
    finally:
        reset_unreal_connection()
        logger.info("Unreal MCP Advanced server shut down")

# Initialize server
mcp = FastMCP(
    "UnrealMCP_Advanced",
    lifespan=server_lifespan
)

# Essential Actor Management Tools
@mcp.tool()
def get_actors_in_level(random_string: str = "") -> Dict[str, Any]:
    """Get a list of all actors in the current level."""
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        response = unreal.send_command("get_actors_in_level", {})
        return response or {"success": False, "message": "No response from Unreal"}
    except Exception as e:
        logger.error(f"get_actors_in_level error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def find_actors_by_name(pattern: str) -> Dict[str, Any]:
    """Find actors by name pattern."""
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        response = unreal.send_command("find_actors_by_name", {"pattern": pattern})
        return response or {"success": False, "message": "No response from Unreal"}
    except Exception as e:
        logger.error(f"find_actors_by_name error: {e}")
        return {"success": False, "message": str(e)}



@mcp.tool()
def delete_actor(name: str) -> Dict[str, Any]:
    """Delete an actor by name."""
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        # Resolve actor name first
        name = resolve_actor_name(unreal, name)
        
        # Use the safe delete function to update tracking
        response = safe_delete_actor(unreal, name)
        return response
    except Exception as e:
        logger.error(f"delete_actor error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def set_actor_transform(
    name: str,
    location: List[float] = None,
    rotation: List[float] = None,
    scale: List[float] = None
) -> Dict[str, Any]:
    """Set the transform of an actor."""
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        # Resolve actor name first
        name = resolve_actor_name(unreal, name)
        
        params = {"name": name}
        if location is not None:
            params["location"] = location
        if rotation is not None:
            params["rotation"] = rotation
        if scale is not None:
            params["scale"] = scale
            
        response = unreal.send_command("set_actor_transform", params)
        return response or {"success": False, "message": "No response from Unreal"}
    except Exception as e:
        logger.error(f"set_actor_transform error: {e}")
        return {"success": False, "message": str(e)}

# Essential Blueprint Tools for Physics Actors
@mcp.tool()
def create_blueprint(name: str, parent_class: str) -> Dict[str, Any]:
    """Create a new Blueprint class."""
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        params = {
            "name": name,
            "parent_class": parent_class
        }
        response = unreal.send_command("create_blueprint", params)
        
        # Persistence: Try to save the asset immediately after creation
        if response and response.get("status") == "success":
            logger.info(f"Blueprint '{name}' created, attempting to save asset...")
            unreal.send_command("save_asset", {"path": f"/Game/Blueprints/{name}"})
            
        return response or {"success": False, "message": "No response from Unreal"}
    except Exception as e:
        logger.error(f"create_blueprint error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def add_component_to_blueprint(
    blueprint_name: str,
    component_type: str,
    component_name: str,
    location: List[float] = [],
    rotation: List[float] = [],
    scale: List[float] = [],
    component_properties: Dict[str, Any] = {}
) -> Dict[str, Any]:
    """Add a component to a Blueprint."""
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        params = {
            "blueprint_name": blueprint_name,
            "component_type": component_type,
            "component_name": component_name,
            "location": location,
            "rotation": rotation,
            "scale": scale,
            "component_properties": component_properties
        }
        response = unreal.send_command("add_component_to_blueprint", params)
        
        # Persistence
        if response and response.get("status") == "success":
            logger.info(f"Component added to '{blueprint_name}', attempting to save asset...")
            unreal.send_command("save_asset", {"path": f"/Game/Blueprints/{blueprint_name}"})
            
        return response or {"success": False, "message": "No response from Unreal"}
    except Exception as e:
        logger.error(f"add_component_to_blueprint error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def set_static_mesh_properties(
    blueprint_name: str,
    component_name: str,
    static_mesh: str = "/Engine/BasicShapes/Cube.Cube"
) -> Dict[str, Any]:
    """Set static mesh properties on a StaticMeshComponent."""
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        params = {
            "blueprint_name": blueprint_name,
            "component_name": component_name,
            "static_mesh": static_mesh
        }
        response = unreal.send_command("set_static_mesh_properties", params)
        return response or {"success": False, "message": "No response from Unreal"}
    except Exception as e:
        logger.error(f"set_static_mesh_properties error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def set_physics_properties(
    blueprint_name: str,
    component_name: str,
    simulate_physics: bool = True,
    gravity_enabled: bool = True,
    mass: float = 1,
    linear_damping: float = 0.01,
    angular_damping: float = 0
) -> Dict[str, Any]:
    """Set physics properties on a component."""
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        params = {
            "blueprint_name": blueprint_name,
            "component_name": component_name,
            "simulate_physics": simulate_physics,
            "gravity_enabled": gravity_enabled,
            "mass": mass,
            "linear_damping": linear_damping,
            "angular_damping": angular_damping
        }
        response = unreal.send_command("set_physics_properties", params)
        return response or {"success": False, "message": "No response from Unreal"}
    except Exception as e:
        logger.error(f"set_physics_properties error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def compile_blueprint(blueprint_name: str) -> Dict[str, Any]:
    """Compile a Blueprint."""
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        params = {"blueprint_name": blueprint_name}
        response = unreal.send_command("compile_blueprint", params)
        return response or {"success": False, "message": "No response from Unreal"}
    except Exception as e:
        logger.error(f"compile_blueprint error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def read_blueprint_content(
    blueprint_path: str,
    include_event_graph: bool = True,
    include_functions: bool = True,
    include_variables: bool = True,
    include_components: bool = True,
    include_interfaces: bool = True
) -> Dict[str, Any]:
    """
    Read and analyze the complete content of a Blueprint including event graph, 
    functions, variables, components, and implemented interfaces.
    
    Args:
        blueprint_path: Full path to the Blueprint asset (e.g., "/Game/MyBlueprint.MyBlueprint")
        include_event_graph: Include event graph nodes and connections
        include_functions: Include custom functions and their graphs
        include_variables: Include all Blueprint variables with types and defaults
        include_components: Include component hierarchy and properties
        include_interfaces: Include implemented Blueprint interfaces
    
    Returns:
        Dictionary containing complete Blueprint structure and content
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        params = {
            "blueprint_path": blueprint_path,
            "include_event_graph": include_event_graph,
            "include_functions": include_functions,
            "include_variables": include_variables,
            "include_components": include_components,
            "include_interfaces": include_interfaces
        }
        
        logger.info(f"Reading Blueprint content for: {blueprint_path}")
        response = unreal.send_command("read_blueprint_content", params)
        
        if response and response.get("success", False):
            logger.info(f"Successfully read Blueprint content. Found:")
            if response.get("variables"):
                logger.info(f"  - {len(response['variables'])} variables")
            if response.get("functions"):
                logger.info(f"  - {len(response['functions'])} functions")
            if response.get("event_graph", {}).get("nodes"):
                logger.info(f"  - {len(response['event_graph']['nodes'])} event graph nodes")
            if response.get("components"):
                logger.info(f"  - {len(response['components'])} components")
        
        return response or {"success": False, "message": "No response from Unreal"}
        
    except Exception as e:
        logger.error(f"read_blueprint_content error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def analyze_blueprint_graph(
    blueprint_path: str,
    graph_name: str = "EventGraph",
    include_node_details: bool = True,
    include_pin_connections: bool = True,
    trace_execution_flow: bool = True
) -> Dict[str, Any]:
    """
    Analyze a specific graph within a Blueprint (EventGraph, functions, etc.)
    and provide detailed information about nodes, connections, and execution flow.
    
    Args:
        blueprint_path: Full path to the Blueprint asset
        graph_name: Name of the graph to analyze ("EventGraph", function name, etc.)
        include_node_details: Include detailed node properties and settings
        include_pin_connections: Include all pin-to-pin connections
        trace_execution_flow: Trace the execution flow through the graph
    
    Returns:
        Dictionary with graph analysis including nodes, connections, and flow
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        params = {
            "blueprint_path": blueprint_path,
            "graph_name": graph_name,
            "include_node_details": include_node_details,
            "include_pin_connections": include_pin_connections,
            "trace_execution_flow": trace_execution_flow
        }
        
        logger.info(f"Analyzing Blueprint graph: {blueprint_path} -> {graph_name}")
        response = unreal.send_command("analyze_blueprint_graph", params)
        
        if response and response.get("success", False):
            graph_data = response.get("graph_data", {})
            logger.info(f"Graph analysis complete:")
            logger.info(f"  - Graph: {graph_data.get('graph_name', 'Unknown')}")
            logger.info(f"  - Nodes: {len(graph_data.get('nodes', []))}")
            logger.info(f"  - Connections: {len(graph_data.get('connections', []))}")
            if graph_data.get('execution_paths'):
                logger.info(f"  - Execution paths: {len(graph_data['execution_paths'])}")
        
        return response or {"success": False, "message": "No response from Unreal"}
        
    except Exception as e:
        logger.error(f"analyze_blueprint_graph error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def get_blueprint_variable_details(
    blueprint_path: str,
    variable_name: str = None
) -> Dict[str, Any]:
    """
    Get detailed information about Blueprint variables including type, 
    default values, metadata, and usage within the Blueprint.
    
    Args:
        blueprint_path: Full path to the Blueprint asset
        variable_name: Specific variable name (if None, returns all variables)
    
    Returns:
        Dictionary with variable details including type, defaults, and usage
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        params = {
            "blueprint_path": blueprint_path,
            "variable_name": variable_name
        }
        
        logger.info(f"Getting Blueprint variable details: {blueprint_path}")
        if variable_name:
            logger.info(f"  - Specific variable: {variable_name}")
        
        response = unreal.send_command("get_blueprint_variable_details", params)
        return response or {"success": False, "message": "No response from Unreal"}
        
    except Exception as e:
        logger.error(f"get_blueprint_variable_details error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def get_blueprint_function_details(
    blueprint_path: str,
    function_name: str = None,
    include_graph: bool = True
) -> Dict[str, Any]:
    """
    Get detailed information about Blueprint functions including parameters,
    return values, local variables, and function graph content.
    
    Args:
        blueprint_path: Full path to the Blueprint asset
        function_name: Specific function name (if None, returns all functions)
        include_graph: Include the function's graph nodes and connections
    
    Returns:
        Dictionary with function details including signature and graph content
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        params = {
            "blueprint_path": blueprint_path,
            "function_name": function_name,
            "include_graph": include_graph
        }
        
        logger.info(f"Getting Blueprint function details: {blueprint_path}")
        if function_name:
            logger.info(f"  - Specific function: {function_name}")
        
        response = unreal.send_command("get_blueprint_function_details", params)
        return response or {"success": False, "message": "No response from Unreal"}
        
    except Exception as e:
        logger.error(f"get_blueprint_function_details error: {e}")
        return {"success": False, "message": str(e)}



# Advanced Composition Tools
@mcp.tool()
def create_pyramid(
    base_size: int = 3,
    block_size: float = 100.0,
    location: List[float] = [0.0, 0.0, 0.0],
    name_prefix: str = "PyramidBlock",
    mesh: str = "/Engine/BasicShapes/Cube.Cube"
) -> Dict[str, Any]:
    """Spawn a pyramid made of cube actors."""
    try:
        unreal = get_unreal_connection()
        if not unreal:
            return {"success": False, "message": "Failed to connect to Unreal Engine"}
        spawned = []
        scale = block_size / 100.0
        for level in range(base_size):
            count = base_size - level
            for x in range(count):
                for y in range(count):
                    actor_name = f"{name_prefix}_{level}_{x}_{y}"
                    loc = [
                        location[0] + (x - (count - 1)/2) * block_size,
                        location[1] + (y - (count - 1)/2) * block_size,
                        location[2] + level * block_size
                    ]
                    params = {
                        "name": actor_name,
                        "type": "StaticMeshActor",
                        "location": loc,
                        "scale": [scale, scale, scale],
                        "static_mesh": mesh
                    }
                    resp = safe_spawn_actor(unreal, params)
                    if resp and resp.get("status") == "success":
                        spawned.append(resp)
        return {"success": True, "actors": spawned}
    except Exception as e:
        logger.error(f"create_pyramid error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def create_wall(
    length: int = 5,
    height: int = 2,
    block_size: float = 100.0,
    location: List[float] = [0.0, 0.0, 0.0],
    orientation: str = "x",
    name_prefix: str = "WallBlock",
    mesh: str = "/Engine/BasicShapes/Cube.Cube"
) -> Dict[str, Any]:
    """Create a simple wall from cubes."""
    try:
        unreal = get_unreal_connection()
        if not unreal:
            return {"success": False, "message": "Failed to connect to Unreal Engine"}
        spawned = []
        scale = block_size / 100.0
        for h in range(height):
            for i in range(length):
                actor_name = f"{name_prefix}_{h}_{i}"
                if orientation == "x":
                    loc = [location[0] + i * block_size, location[1], location[2] + h * block_size]
                else:
                    loc = [location[0], location[1] + i * block_size, location[2] + h * block_size]
                params = {
                    "name": actor_name,
                    "type": "StaticMeshActor",
                    "location": loc,
                    "scale": [scale, scale, scale],
                    "static_mesh": mesh
                }
                resp = safe_spawn_actor(unreal, params)
                if resp and resp.get("status") == "success":
                    spawned.append(resp)
        return {"success": True, "actors": spawned}
    except Exception as e:
        logger.error(f"create_wall error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def create_tower(
    height: int = 10,
    base_size: int = 4,
    block_size: float = 100.0,
    location: List[float] = [0.0, 0.0, 0.0],
    name_prefix: str = "TowerBlock",
    mesh: str = "/Engine/BasicShapes/Cube.Cube",
    tower_style: str = "cylindrical"  # "cylindrical", "square", "tapered"
) -> Dict[str, Any]:
    """Create a realistic tower with various architectural styles."""
    try:
        unreal = get_unreal_connection()
        if not unreal:
            return {"success": False, "message": "Failed to connect to Unreal Engine"}
        spawned = []
        scale = block_size / 100.0

        for level in range(height):
            level_height = location[2] + level * block_size
            
            if tower_style == "cylindrical":
                # Create circular tower
                radius = (base_size / 2) * block_size  # Convert to world units (centimeters)
                circumference = 2 * math.pi * radius
                num_blocks = max(8, int(circumference / block_size))
                
                for i in range(num_blocks):
                    angle = (2 * math.pi * i) / num_blocks
                    x = location[0] + radius * math.cos(angle)
                    y = location[1] + radius * math.sin(angle)
                    
                    actor_name = f"{name_prefix}_{level}_{i}"
                    params = {
                        "name": actor_name,
                        "type": "StaticMeshActor",
                        "location": [x, y, level_height],
                        "scale": [scale, scale, scale],
                        "static_mesh": mesh
                    }
                    resp = safe_spawn_actor(unreal, params)
                    if resp and resp.get("status") == "success":
                        spawned.append(resp)
                        
            elif tower_style == "tapered":
                # Create tapering square tower
                current_size = max(1, base_size - (level // 2))
                half_size = current_size / 2
                
                # Create walls for current level
                for side in range(4):
                    for i in range(current_size):
                        if side == 0:  # Front wall
                            x = location[0] + (i - half_size + 0.5) * block_size
                            y = location[1] - half_size * block_size
                            actor_name = f"{name_prefix}_{level}_front_{i}"
                        elif side == 1:  # Right wall
                            x = location[0] + half_size * block_size
                            y = location[1] + (i - half_size + 0.5) * block_size
                            actor_name = f"{name_prefix}_{level}_right_{i}"
                        elif side == 2:  # Back wall
                            x = location[0] + (half_size - i - 0.5) * block_size
                            y = location[1] + half_size * block_size
                            actor_name = f"{name_prefix}_{level}_back_{i}"
                        else:  # Left wall
                            x = location[0] - half_size * block_size
                            y = location[1] + (half_size - i - 0.5) * block_size
                            actor_name = f"{name_prefix}_{level}_left_{i}"
                            
                        params = {
                            "name": actor_name,
                            "type": "StaticMeshActor",
                            "location": [x, y, level_height],
                            "scale": [scale, scale, scale],
                            "static_mesh": mesh
                        }
                        resp = unreal.send_command("spawn_actor", params)
                        if resp:
                            spawned.append(resp)
                            
            else:  # square tower
                # Create square tower walls
                half_size = base_size / 2
                
                # Four walls
                for side in range(4):
                    for i in range(base_size):
                        if side == 0:  # Front wall
                            x = location[0] + (i - half_size + 0.5) * block_size
                            y = location[1] - half_size * block_size
                            actor_name = f"{name_prefix}_{level}_front_{i}"
                        elif side == 1:  # Right wall
                            x = location[0] + half_size * block_size
                            y = location[1] + (i - half_size + 0.5) * block_size
                            actor_name = f"{name_prefix}_{level}_right_{i}"
                        elif side == 2:  # Back wall
                            x = location[0] + (half_size - i - 0.5) * block_size
                            y = location[1] + half_size * block_size
                            actor_name = f"{name_prefix}_{level}_back_{i}"
                        else:  # Left wall
                            x = location[0] - half_size * block_size
                            y = location[1] + (half_size - i - 0.5) * block_size
                            actor_name = f"{name_prefix}_{level}_left_{i}"
                            
                        params = {
                            "name": actor_name,
                            "type": "StaticMeshActor",
                            "location": [x, y, level_height],
                            "scale": [scale, scale, scale],
                            "static_mesh": mesh
                        }
                        resp = unreal.send_command("spawn_actor", params)
                        if resp:
                            spawned.append(resp)
                            
            # Add decorative elements every few levels
            if level % 3 == 2 and level < height - 1:
                # Add corner details
                for corner in range(4):
                    angle = corner * math.pi / 2
                    detail_x = location[0] + (base_size/2 + 0.5) * block_size * math.cos(angle)
                    detail_y = location[1] + (base_size/2 + 0.5) * block_size * math.sin(angle)
                    
                    actor_name = f"{name_prefix}_{level}_detail_{corner}"
                    params = {
                        "name": actor_name,
                        "type": "StaticMeshActor",
                        "location": [detail_x, detail_y, level_height],
                        "scale": [scale * 0.7, scale * 0.7, scale * 0.7],
                        "static_mesh": "/Engine/BasicShapes/Cylinder.Cylinder"
                    }
                    resp = safe_spawn_actor(unreal, params)
                    if resp and resp.get("status") == "success":
                        spawned.append(resp)
                        
        return {"success": True, "actors": spawned, "tower_style": tower_style}
    except Exception as e:
        logger.error(f"create_tower error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def create_staircase(
    steps: int = 5,
    step_size: List[float] = [100.0, 100.0, 50.0],
    location: List[float] = [0.0, 0.0, 0.0],
    name_prefix: str = "Stair",
    mesh: str = "/Engine/BasicShapes/Cube.Cube"
) -> Dict[str, Any]:
    """Create a staircase from cubes."""
    try:
        unreal = get_unreal_connection()
        if not unreal:
            return {"success": False, "message": "Failed to connect to Unreal Engine"}
        spawned = []
        sx, sy, sz = step_size
        for i in range(steps):
            actor_name = f"{name_prefix}_{i}"
            loc = [location[0] + i * sx, location[1], location[2] + i * sz]
            scale = [sx/100.0, sy/100.0, sz/100.0]
            params = {
                "name": actor_name,
                "type": "StaticMeshActor",
                "location": loc,
                "scale": scale,
                "static_mesh": mesh
            }
            resp = safe_spawn_actor(unreal, params)
            if resp and resp.get("status") == "success":
                spawned.append(resp)
        return {"success": True, "actors": spawned}
    except Exception as e:
        logger.error(f"create_staircase error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def construct_house(
    width: int = 1200,
    depth: int = 1000,
    height: int = 600,
    location: List[float] = [0.0, 0.0, 0.0],
    name_prefix: str = "House",
    mesh: str = "/Engine/BasicShapes/Cube.Cube",
    house_style: str = "modern"  # "modern", "cottage"
) -> Dict[str, Any]:
    """Construct a realistic house with architectural details and multiple rooms."""
    try:
        unreal = get_unreal_connection()
        if not unreal:
            return {"success": False, "message": "Failed to connect to Unreal Engine"}

        # Use the helper function to build the house
        return build_house(unreal, width, depth, height, location, name_prefix, mesh, house_style)

    except Exception as e:
        logger.error(f"construct_house error: {e}")
        return {"success": False, "message": str(e)}



@mcp.tool()
def construct_mansion(
    mansion_scale: str = "large",  # "small", "large", "epic", "legendary"
    location: List[float] = [0.0, 0.0, 0.0],
    name_prefix: str = "Mansion",
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Construct a magnificent mansion with multiple wings, grand rooms, gardens,
    fountains, and luxury features perfect for dramatic TikTok reveals.
    
    Args:
        mansion_scale: Scale of the mansion
        location: Base location [x, y, z]
        name_prefix: Prefix for actor names
        dry_run: If True, only calculate parameters without spawning
    """
    try:
        unreal = get_unreal_connection()
        if not unreal:
            return {"success": False, "message": "Failed to connect to Unreal Engine"}

        logger.info(f"Creating {mansion_scale} mansion (dry_run={dry_run})")
        
        if dry_run:
            return {
                "success": True,
                "message": f"Dry run: Would construct a {mansion_scale} mansion at {location}."
            }
        all_actors = []

        # Get size parameters and calculate scaled dimensions
        params = get_mansion_size_params(mansion_scale)
        layout = calculate_mansion_layout(params)

        # Build mansion main structure
        build_mansion_main_structure(unreal, name_prefix, location, layout, all_actors)

        # Build mansion exterior
        build_mansion_exterior(unreal, name_prefix, location, layout, all_actors)

        # Add luxurious interior
        add_mansion_interior(unreal, name_prefix, location, layout, all_actors)

        logger.info(f"Mansion construction complete! Created {len(all_actors)} elements")

        return {
            "success": True,
            "message": f"Magnificent {mansion_scale} mansion created with {len(all_actors)} elements!",
            "actors": all_actors,
            "stats": {
                "scale": mansion_scale,
                "wings": layout["wings"],
                "floors": layout["floors"],
                "main_rooms": layout["main_rooms"],
                "bedrooms": layout["bedrooms"],
                "garden_size": layout["garden_size"],
                "fountain_count": layout["fountain_count"],
                "car_count": layout["car_count"],
                "total_actors": len(all_actors)
            }
        }

    except Exception as e:
        logger.error(f"construct_mansion error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def create_arch(
    radius: float = 300.0,
    segments: int = 6,
    location: List[float] = [0.0, 0.0, 0.0],
    name_prefix: str = "ArchBlock",
    mesh: str = "/Engine/BasicShapes/Cube.Cube"
) -> Dict[str, Any]:
    """Create a simple arch using cubes in a semicircle."""
    try:
        unreal = get_unreal_connection()
        if not unreal:
            return {"success": False, "message": "Failed to connect to Unreal Engine"}
        spawned = []
        angle_step = math.pi / segments
        scale = radius / 300.0 / 2
        for i in range(segments + 1):
            theta = angle_step * i
            x = radius * math.cos(theta)
            z = radius * math.sin(theta)
            actor_name = f"{name_prefix}_{i}"
            params = {
                "name": actor_name,
                "type": "StaticMeshActor",
                "location": [location[0] + x, location[1], location[2] + z],
                "scale": [scale, scale, scale],
                "static_mesh": mesh
            }
            resp = safe_spawn_actor(unreal, params)
            if resp and resp.get("status") == "success":
                spawned.append(resp)
        return {"success": True, "actors": spawned}
    except Exception as e:
        logger.error(f"create_arch error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def set_component_property(
    blueprint_name: str,
    component_name: str,
    property_name: str,
    property_value: Any
) -> Dict[str, Any]:
    """
    Set a property on a component within a Blueprint.
    Supports both components added in the Blueprint (SCS) and inherited C++ components.
    
    Args:
        blueprint_name: Name of the Blueprint to modify
        component_name: Name of the component (e.g., 'CameraBoom', 'Mesh')
        property_name: Name of the property to set (e.g., 'TargetArmLength', 'SocketOffset')
        property_value: The value to set (can be number, string, bool, or list for Vector/Rotator)
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        response = unreal.send_command("set_component_property", {
            "blueprint_name": blueprint_name,
            "component_name": component_name,
            "property_name": property_name,
            "property_value": property_value
        })
        return response
    except Exception as e:
        logger.error(f"set_component_property error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def spawn_physics_blueprint_actor (
    name: str,
    mesh_path: str = "/Engine/BasicShapes/Cube.Cube",
    location: List[float] = [0.0, 0.0, 0.0],
    mass: float = 1.0,
    simulate_physics: bool = True,
    gravity_enabled: bool = True,
    color: List[float] = None,  # Optional color parameter [R, G, B] or [R, G, B, A]
    scale: List[float] = [1.0, 1.0, 1.0]  # Default scale
) -> Dict[str, Any]:
    """
    Quickly spawn a single actor with physics, color, and a specific mesh.

    This is the primary function for creating simple objects with physics properties.
    It handles creating a temporary Blueprint, setting up the mesh, color, and physics,
    and then spawns the actor in the world. It's ideal for quickly adding
    dynamic objects to the scene without needing to manually create Blueprints.
    
    Args:
        color: Optional color as [R, G, B] or [R, G, B, A] where values are 0.0-1.0.
               If [R, G, B] is provided, alpha will be set to 1.0 automatically.
    """
    try:
        bp_name = f"{name}_BP"
        create_blueprint(bp_name, "Actor")
        add_component_to_blueprint(bp_name, "StaticMeshComponent", "Mesh", scale=scale)
        set_static_mesh_properties(bp_name, "Mesh", mesh_path)
        set_physics_properties(bp_name, "Mesh", simulate_physics, gravity_enabled, mass)

        # Set color if provided
        if color is not None:
            # Convert 3-value color [R,G,B] to 4-value [R,G,B,A] if needed
            if len(color) == 3:
                color = color + [1.0]  # Add alpha=1.0
            elif len(color) != 4:
                logger.warning(f"Invalid color format: {color}. Expected [R,G,B] or [R,G,B,A]. Skipping color.")
                color = None

            if color is not None:
                color_result = set_mesh_material_color(bp_name, "Mesh", color)
                if not color_result.get("success", False):
                    logger.warning(f"Failed to set color {color} for {bp_name}: {color_result.get('message', 'Unknown error')}")

        compile_blueprint(bp_name)
        # Unreal side usually needs a moment to process the compilation before spawning
        time.sleep(0.5)
        
        # Spawn the blueprint actor using helper function
        unreal = get_unreal_connection()
        result = spawn_blueprint_actor(unreal, bp_name, name, location)

        # Ensure proper scale is set on the spawned actor
        if result.get("success", False):
            spawned_name = result.get("result", {}).get("name", name)
            set_actor_transform(spawned_name, scale=scale)

        return result
    except Exception as e:
        logger.error(f"spawn_physics_blueprint_actor  error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def create_maze(
    rows: int = 8,
    cols: int = 8,
    cell_size: float = 300.0,
    wall_height: int = 3,
    location: List[float] = [0.0, 0.0, 0.0]
) -> Dict[str, Any]:
    """Create a proper solvable maze with entrance, exit, and guaranteed path using recursive backtracking algorithm."""
    try:
        unreal = get_unreal_connection()
        if not unreal:
            return {"success": False, "message": "Failed to connect to Unreal Engine"}
            
        import random
        spawned = []
        
        # Initialize maze grid - True means wall, False means open
        maze = [[True for _ in range(cols * 2 + 1)] for _ in range(rows * 2 + 1)]
        
        # Recursive backtracking maze generation
        def carve_path(row, col):
            # Mark current cell as path
            maze[row * 2 + 1][col * 2 + 1] = False
            
            # Random directions
            directions = [(0, 1), (1, 0), (0, -1), (-1, 0)]
            random.shuffle(directions)
            
            for dr, dc in directions:
                new_row, new_col = row + dr, col + dc
                
                # Check bounds
                if (0 <= new_row < rows and 0 <= new_col < cols and 
                    maze[new_row * 2 + 1][new_col * 2 + 1]):
                    
                    # Carve wall between current and new cell
                    maze[row * 2 + 1 + dr][col * 2 + 1 + dc] = False
                    carve_path(new_row, new_col)
        
        # Start carving from top-left corner
        carve_path(0, 0)
        
        # Create entrance and exit
        maze[1][0] = False  # Entrance on left side
        maze[rows * 2 - 1][cols * 2] = False  # Exit on right side
        
        # Build the actual maze in Unreal
        maze_height = rows * 2 + 1
        maze_width = cols * 2 + 1
        
        for r in range(maze_height):
            for c in range(maze_width):
                if maze[r][c]:  # If this is a wall
                    # Stack blocks to create wall height
                    for h in range(wall_height):
                        x_pos = location[0] + (c - maze_width/2) * cell_size
                        y_pos = location[1] + (r - maze_height/2) * cell_size
                        z_pos = location[2] + h * cell_size
                        
                        actor_name = f"Maze_Wall_{r}_{c}_{h}"
                        params = {
                            "name": actor_name,
                            "type": "StaticMeshActor",
                            "location": [x_pos, y_pos, z_pos],
                            "scale": [cell_size/100.0, cell_size/100.0, cell_size/100.0],
                            "static_mesh": "/Engine/BasicShapes/Cube.Cube"
                        }
                        resp = safe_spawn_actor(unreal, params)
                        if resp and resp.get("status") == "success":
                            spawned.append(resp)
        
        # Add entrance and exit markers
        entrance_marker = safe_spawn_actor(unreal, {
            "name": "Maze_Entrance",
            "type": "StaticMeshActor",
            "location": [location[0] - maze_width/2 * cell_size - cell_size, 
                       location[1] + (-maze_height/2 + 1) * cell_size, 
                       location[2] + cell_size],
            "scale": [0.5, 0.5, 0.5],
            "static_mesh": "/Engine/BasicShapes/Cylinder.Cylinder"
        })
        if entrance_marker and entrance_marker.get("status") == "success":
            spawned.append(entrance_marker)
            
        exit_marker = safe_spawn_actor(unreal, {
            "name": "Maze_Exit",
            "type": "StaticMeshActor", 
            "location": [location[0] + maze_width/2 * cell_size + cell_size,
                       location[1] + (-maze_height/2 + rows * 2 - 1) * cell_size,
                       location[2] + cell_size],
            "scale": [0.5, 0.5, 0.5],
            "static_mesh": "/Engine/BasicShapes/Sphere.Sphere"
        })
        if exit_marker and exit_marker.get("status") == "success":
            spawned.append(exit_marker)
        
        return {
            "success": True, 
            "actors": spawned, 
            "maze_size": f"{rows}x{cols}",
            "wall_count": len([block for block in spawned if "Wall" in block.get("name", "")]),
            "entrance": "Left side (cylinder marker)",
            "exit": "Right side (sphere marker)"
        }
    except Exception as e:
        logger.error(f"create_maze error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def get_available_materials(
    search_path: str = "/Game/",
    include_engine_materials: bool = True
) -> Dict[str, Any]:
    """Get a list of available materials in the project that can be applied to objects."""
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        params = {
            "search_path": search_path,
            "include_engine_materials": include_engine_materials
        }
        response = unreal.send_command("get_available_materials", params)
        return response or {"success": False, "message": "No response from Unreal"}
    except Exception as e:
        logger.error(f"get_available_materials error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def apply_material_to_actor(
    actor_name: str,
    material_path: str,
    material_slot: int = 0
) -> Dict[str, Any]:
    """Apply a specific material to an actor in the level."""
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        # Resolve actor name first
        actor_name = resolve_actor_name(unreal, actor_name)
        
        params = {
            "actor_name": actor_name,
            "material_path": material_path,
            "material_slot": material_slot
        }
        response = unreal.send_command("apply_material_to_actor", params)
        return response or {"success": False, "message": "No response from Unreal"}
    except Exception as e:
        logger.error(f"apply_material_to_actor error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def apply_material_to_blueprint(
    blueprint_name: str,
    component_name: str,
    material_path: str,
    material_slot: int = 0
) -> Dict[str, Any]:
    """Apply a specific material to a component in a Blueprint."""
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        params = {
            "blueprint_name": blueprint_name,
            "component_name": component_name,
            "material_path": material_path,
            "material_slot": material_slot
        }
        response = unreal.send_command("apply_material_to_blueprint", params)
        return response or {"success": False, "message": "No response from Unreal"}
    except Exception as e:
        logger.error(f"apply_material_to_blueprint error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def get_actor_material_info(
    actor_name: str
) -> Dict[str, Any]:
    """Get information about the materials currently applied to an actor."""
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        # Resolve actor name first
        actor_name = resolve_actor_name(unreal, actor_name)
        params = {"actor_name": actor_name}
        response = unreal.send_command("get_actor_material_info", params)
        return response or {"success": False, "message": "No response from Unreal"}
    except Exception as e:
        logger.error(f"get_actor_material_info error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def set_mesh_material_color(
    blueprint_name: str,
    component_name: str,
    color: List[float],
    material_path: str = "/Engine/BasicShapes/BasicShapeMaterial",
    parameter_name: str = "BaseColor",
    material_slot: int = 0
) -> Dict[str, Any]:
    """Set material color on a mesh component using the proven color system."""
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        # Validate color format
        if not isinstance(color, list) or len(color) != 4:
            return {"success": False, "message": "Invalid color format. Must be a list of 4 float values [R, G, B, A]."}
        
        # Ensure all color values are floats between 0 and 1
        color = [float(min(1.0, max(0.0, val))) for val in color]
        
        # Set BaseColor parameter first
        params_base = {
            "blueprint_name": blueprint_name,
            "component_name": component_name,
            "color": color,
            "material_path": material_path,
            "parameter_name": "BaseColor",
            "material_slot": material_slot
        }
        response_base = unreal.send_command("set_mesh_material_color", params_base)
        
        # Set Color parameter second (for maximum compatibility)
        params_color = {
            "blueprint_name": blueprint_name,
            "component_name": component_name,
            "color": color,
            "material_path": material_path,
            "parameter_name": "Color",
            "material_slot": material_slot
        }
        response_color = unreal.send_command("set_mesh_material_color", params_color)
        
        # Return success if either parameter setting worked
        if (response_base and response_base.get("status") == "success") or (response_color and response_color.get("status") == "success"):
            return {
                "success": True, 
                "message": f"Color applied successfully to slot {material_slot}: {color}",
                "base_color_result": response_base,
                "color_result": response_color,
                "material_slot": material_slot
            }
        else:
            return {
                "success": False, 
                "message": f"Failed to set color parameters on slot {material_slot}. BaseColor: {response_base}, Color: {response_color}"
            }
            
    except Exception as e:
        logger.error(f"set_mesh_material_color error: {e}")
        return {"success": False, "message": str(e)}

# Advanced Town Generation System
@mcp.tool()
def create_town(
    town_size: str = "medium",  # "small", "medium", "large", "metropolis"
    building_density: float = 0.7,  # 0.0 to 1.0
    location: List[float] = [0.0, 0.0, 0.0],
    name_prefix: str = "Town",
    include_infrastructure: bool = True,
    architectural_style: str = "mixed",  # "modern", "cottage", "mansion", "mixed", "downtown", "futuristic"
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Create a full dynamic town with buildings, streets, infrastructure, and vehicles.
    
    Args:
        town_size: Size of the town
        building_density: Density of buildings
        location: Base location [x, y, z]
        name_prefix: Prefix for actor names
        include_infrastructure: Whether to include streets, lights, etc.
        architectural_style: Style of buildings
        dry_run: If True, only calculate parameters without spawning (Prevents timeouts)
    """
    try:
        import random
        random.seed()  # Use different seed each time for variety
        
        unreal = get_unreal_connection()
        if not unreal:
            return {"success": False, "message": "Failed to connect to Unreal Engine"}
        
        logger.info(f"Creating {town_size} town at {location} (dry_run={dry_run})")
        
        if dry_run:
            return {
                "success": True,
                "message": f"Dry run: Would create a {town_size} town at {location}."
            }
        
        # Define town parameters based on size
        town_params = {
            "small": {"blocks": 3, "block_size": 1500, "max_building_height": 5, "population": 20, "skyscraper_chance": 0.1},
            "medium": {"blocks": 5, "block_size": 2000, "max_building_height": 10, "population": 50, "skyscraper_chance": 0.3},
            "large": {"blocks": 7, "block_size": 2500, "max_building_height": 20, "population": 100, "skyscraper_chance": 0.5},
            "metropolis": {"blocks": 10, "block_size": 3000, "max_building_height": 40, "population": 200, "skyscraper_chance": 0.7}
        }
        
        params = town_params.get(town_size, town_params["medium"])
        blocks = params["blocks"]
        block_size = params["block_size"]
        max_height = params["max_building_height"]
        target_population = int(params["population"] * building_density)
        skyscraper_chance = params["skyscraper_chance"]
        
        all_spawned = []
        street_width = block_size * 0.3
        building_area = block_size * 0.7
        
        # Create street grid first
        logger.info("Creating street grid...")
        street_results = _create_street_grid(blocks, block_size, street_width, location, name_prefix)
        all_spawned.extend(street_results.get("actors", []))
        
        # Create buildings in each block
        logger.info("Placing buildings...")
        building_count = 0
        for block_x in range(blocks):
            for block_y in range(blocks):
                if building_count >= target_population:
                    break
                    
                # Skip some blocks randomly for variety
                if random.random() > building_density:
                    continue
                
                block_center_x = location[0] + (block_x - blocks/2) * block_size
                block_center_y = location[1] + (block_y - blocks/2) * block_size
                
                # Randomly choose building type based on style and location
                if architectural_style == "downtown" or architectural_style == "futuristic":
                    building_types = ["skyscraper", "office_tower", "apartment_complex", "shopping_mall", "parking_garage", "hotel"]
                elif architectural_style == "mixed":
                    # Central blocks get taller buildings
                    is_central = abs(block_x - blocks//2) <= 1 and abs(block_y - blocks//2) <= 1
                    if is_central and random.random() < skyscraper_chance:
                        building_types = ["skyscraper", "office_tower", "apartment_complex", "hotel", "shopping_mall"]
                    else:
                        building_types = ["house", "tower", "mansion", "commercial", "apartment_building", "restaurant", "store"]
                else:
                    building_types = [architectural_style] * 3 + ["commercial", "restaurant", "store"]
                
                building_type = random.choice(building_types)
                
                # Create building with variety
                building_result = _create_town_building(
                    building_type, 
                    [block_center_x, block_center_y, location[2]],
                    building_area,
                    max_height,
                    f"{name_prefix}_Building_{block_x}_{block_y}",
                    building_count
                )
                
                if building_result.get("status") == "success":
                    all_spawned.extend(building_result.get("actors", []))
                    building_count += 1
        
        # Add infrastructure if requested
        infrastructure_count = 0
        if include_infrastructure:
            logger.info("Adding infrastructure...")
            
            # Street lights
            light_results = _create_street_lights(blocks, block_size, location, name_prefix)
            all_spawned.extend(light_results.get("actors", []))
            infrastructure_count += len(light_results.get("actors", []))
            
            # Vehicles
            vehicle_results = _create_town_vehicles(blocks, block_size, street_width, location, name_prefix, target_population // 3)
            all_spawned.extend(vehicle_results.get("actors", []))
            infrastructure_count += len(vehicle_results.get("actors", []))
            
            # Parks and decorations
            decoration_results = _create_town_decorations(blocks, block_size, location, name_prefix)
            all_spawned.extend(decoration_results.get("actors", []))
            infrastructure_count += len(decoration_results.get("actors", []))
            
            
            # Add advanced infrastructure
            logger.info("Adding advanced infrastructure...")
            
            # Traffic lights at intersections
            traffic_results = _create_traffic_lights(blocks, block_size, location, name_prefix)
            all_spawned.extend(traffic_results.get("actors", []))
            infrastructure_count += len(traffic_results.get("actors", []))
            
            # Street signs and billboards
            signage_results = _create_street_signage(blocks, block_size, location, name_prefix, town_size)
            all_spawned.extend(signage_results.get("actors", []))
            infrastructure_count += len(signage_results.get("actors", []))
            
            # Sidewalks and crosswalks
            sidewalk_results = _create_sidewalks_crosswalks(blocks, block_size, street_width, location, name_prefix)
            all_spawned.extend(sidewalk_results.get("actors", []))
            infrastructure_count += len(sidewalk_results.get("actors", []))
            
            # Urban furniture (benches, trash cans, bus stops)
            furniture_results = _create_urban_furniture(blocks, block_size, location, name_prefix)
            all_spawned.extend(furniture_results.get("actors", []))
            infrastructure_count += len(furniture_results.get("actors", []))
            
            # Parking meters and hydrants
            utility_results = _create_street_utilities(blocks, block_size, location, name_prefix)
            all_spawned.extend(utility_results.get("actors", []))
            infrastructure_count += len(utility_results.get("actors", []))
            
            # Add plaza/square in center for large towns
            if town_size in ["large", "metropolis"]:
                plaza_results = _create_central_plaza(blocks, block_size, location, name_prefix)
                all_spawned.extend(plaza_results.get("actors", []))
                infrastructure_count += len(plaza_results.get("actors", []))
        
        return {
            "success": True,
            "town_stats": {
                "size": town_size,
                "density": building_density,
                "blocks": blocks,
                "buildings": building_count,
                "infrastructure_items": infrastructure_count,
                "total_actors": len(all_spawned),
                "architectural_style": architectural_style
            },
            "actors": all_spawned,
            "message": f"Created {town_size} town with {building_count} buildings and {infrastructure_count} infrastructure items"
        }
        
    except Exception as e:
        logger.error(f"create_town error: {e}")
        return {"success": False, "message": str(e)}


@mcp.tool()
def create_castle_fortress(
    castle_size: str = "large",  # "small", "medium", "large", "epic"
    location: List[float] = [0.0, 0.0, 0.0],
    name_prefix: str = "Castle",
    include_siege_weapons: bool = True,
    include_village: bool = True,
    architectural_style: str = "medieval",  # "medieval", "fantasy", "gothic"
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Create a massive castle fortress with walls, towers, courtyards, throne room,
    and surrounding village. Perfect for dramatic TikTok reveals showing
    the scale and detail of a complete medieval fortress.
    
    Args:
        castle_size: Scale of the fortress
        location: Base location [x, y, z]
        name_prefix: Prefix for actor names
        include_siege_weapons: Whether to spawn siege weapons
        include_village: Whether to spawn a surrounding village
        architectural_style: Style of the castle
        dry_run: If True, only calculate parameters without spawning
    """
    try:
        unreal = get_unreal_connection()
        if not unreal:
            return {"success": False, "message": "Failed to connect to Unreal Engine"}
        
        logger.info(f"Creating {castle_size} {architectural_style} castle fortress (dry_run={dry_run})")
        
        if dry_run:
            return {
                "success": True,
                "message": f"Dry run: Would create a {castle_size} castle at {location}."
            }
        all_actors = []
        
        # Get size parameters and calculate scaled dimensions
        params = get_castle_size_params(castle_size)
        dimensions = calculate_scaled_dimensions(params, scale_factor=2.0)
        
        # Build castle components using helper functions
        build_outer_bailey_walls(unreal, name_prefix, location, dimensions, all_actors)
        build_inner_bailey_walls(unreal, name_prefix, location, dimensions, all_actors)
        build_gate_complex(unreal, name_prefix, location, dimensions, all_actors)
        build_corner_towers(unreal, name_prefix, location, dimensions, architectural_style, all_actors)
        build_inner_corner_towers(unreal, name_prefix, location, dimensions, all_actors)
        build_intermediate_towers(unreal, name_prefix, location, dimensions, all_actors)
        build_central_keep(unreal, name_prefix, location, dimensions, all_actors)
        build_courtyard_complex(unreal, name_prefix, location, dimensions, all_actors)
        build_bailey_annexes(unreal, name_prefix, location, dimensions, all_actors)
        
        # Add optional components
        if include_siege_weapons:
            build_siege_weapons(unreal, name_prefix, location, dimensions, all_actors)
        
        if include_village:
            build_village_settlement(unreal, name_prefix, location, dimensions, castle_size, all_actors)
        
        # Add final touches
        build_drawbridge_and_moat(unreal, name_prefix, location, dimensions, all_actors)
        add_decorative_flags(unreal, name_prefix, location, dimensions, all_actors)
        
        logger.info(f"Castle fortress creation complete! Created {len(all_actors)} actors")

        
        return {
            "success": True,
            "message": f"Epic {castle_size} {architectural_style} castle fortress created with {len(all_actors)} elements!",
            "actors": all_actors,
            "stats": {
                "size": castle_size,
                "style": architectural_style,
                "wall_sections": int(dimensions["outer_width"]/200) * 2 + int(dimensions["outer_depth"]/200) * 2,
                "towers": dimensions["tower_count"],
                "has_village": include_village,
                "has_siege_weapons": include_siege_weapons,
                "total_actors": len(all_actors)
            }
        }
        
    except Exception as e:
        logger.error(f"create_castle_fortress error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def create_suspension_bridge(
    span_length: float = 6000.0,
    deck_width: float = 800.0,
    tower_height: float = 4000.0,
    cable_sag_ratio: float = 0.12,
    module_size: float = 200.0,
    location: List[float] = [0.0, 0.0, 0.0],
    orientation: str = "x",
    name_prefix: str = "Bridge",
    deck_mesh: str = "/Engine/BasicShapes/Cube.Cube",
    tower_mesh: str = "/Engine/BasicShapes/Cube.Cube",
    cable_mesh: str = "/Engine/BasicShapes/Cylinder.Cylinder",
    suspender_mesh: str = "/Engine/BasicShapes/Cylinder.Cylinder",
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Build a suspension bridge with towers, deck, cables, and suspenders.
    
    Creates a realistic suspension bridge with parabolic main cables, vertical
    suspenders, twin towers, and a multi-lane deck. Perfect for dramatic reveals
    showing engineering marvels.
    
    Args:
        span_length: Total span between towers
        deck_width: Width of the bridge deck
        tower_height: Height of support towers
        cable_sag_ratio: Sag as fraction of span (0.1-0.15 typical)
        module_size: Resolution for segments (affects actor count)
        location: Center point of the bridge
        orientation: "x" or "y" for bridge direction
        name_prefix: Prefix for all spawned actors
        deck_mesh: Mesh for deck segments
        tower_mesh: Mesh for tower components
        cable_mesh: Mesh for cable segments
        suspender_mesh: Mesh for vertical suspenders
        dry_run: If True, calculate metrics without spawning
    
    Returns:
        Dictionary with success status, spawned actors, and performance metrics
    """
    try:
        import time
        start_time = time.perf_counter()
        
        unreal = get_unreal_connection()
        if not unreal:
            return {"success": False, "message": "Failed to connect to Unreal Engine"}
        
        logger.info(f"Creating suspension bridge: span={span_length}, width={deck_width}, height={tower_height}")
        
        all_actors = []
        
        # Calculate expected actor counts for dry run
        if dry_run:
            expected_towers = 10  # 2 towers with main, base, top, and 2 attachment points each
            expected_deck = max(1, int(span_length / module_size)) * max(1, int(deck_width / module_size))
            expected_cables = 2 * max(1, int(span_length / module_size))  # 2 main cables
            expected_suspenders = 2 * max(1, int(span_length / (module_size * 3)))  # Every 3 modules
            
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            
            return {
                "success": True,
                "dry_run": True,
                "metrics": {
                    "total_actors": expected_towers + expected_deck + expected_cables + expected_suspenders,
                    "deck_segments": expected_deck,
                    "cable_segments": expected_cables,
                    "suspender_count": expected_suspenders,
                    "towers": expected_towers,
                    "span_length": span_length,
                    "deck_width": deck_width,
                    "est_area": span_length * deck_width,
                    "elapsed_ms": elapsed_ms
                }
            }
        
        # Build the bridge structure
        counts = build_suspension_bridge_structure(
            unreal,
            span_length,
            deck_width,
            tower_height,
            cable_sag_ratio,
            module_size,
            location,
            orientation,
            name_prefix,
            deck_mesh,
            tower_mesh,
            cable_mesh,
            suspender_mesh,
            all_actors
        )
        
        # Calculate metrics
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        total_actors = sum(counts.values())
        
        logger.info(f"Bridge construction complete: {total_actors} actors in {elapsed_ms}ms")
        
        return {
            "success": True,
            "message": f"Created suspension bridge with {total_actors} components",
            "actors": all_actors,
            "metrics": {
                "total_actors": total_actors,
                "deck_segments": counts["deck_segments"],
                "cable_segments": counts["cable_segments"],
                "suspender_count": counts["suspenders"],
                "towers": counts["towers"],
                "span_length": span_length,
                "deck_width": deck_width,
                "est_area": span_length * deck_width,
                "elapsed_ms": elapsed_ms
            }
        }
        
    except Exception as e:
        logger.error(f"create_suspension_bridge error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def create_aqueduct(
    arches: int = 18,
    arch_radius: float = 600.0,
    pier_width: float = 200.0,
    tiers: int = 2,
    deck_width: float = 600.0,
    module_size: float = 200.0,
    location: List[float] = [0.0, 0.0, 0.0],
    orientation: str = "x",
    name_prefix: str = "Aqueduct",
    arch_mesh: str = "/Engine/BasicShapes/Cylinder.Cylinder",
    pier_mesh: str = "/Engine/BasicShapes/Cube.Cube",
    deck_mesh: str = "/Engine/BasicShapes/Cube.Cube",
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Build a multi-tier Roman-style aqueduct with arches and water channel.
    
    Creates a majestic aqueduct with repeating arches, support piers, and
    a water channel deck. Each tier has progressively smaller piers for
    realistic tapering. Perfect for showing ancient engineering.
    
    Args:
        arches: Number of arches per tier
        arch_radius: Radius of each arch
        pier_width: Width of support piers
        tiers: Number of vertical tiers (1-3 recommended)
        deck_width: Width of the water channel
        module_size: Resolution for segments (affects actor count)
        location: Starting point of the aqueduct
        orientation: "x" or "y" for aqueduct direction
        name_prefix: Prefix for all spawned actors
        arch_mesh: Mesh for arch segments (cylinder)
        pier_mesh: Mesh for support piers
        deck_mesh: Mesh for deck and walls
        dry_run: If True, calculate metrics without spawning
    
    Returns:
        Dictionary with success status, spawned actors, and performance metrics
    """
    try:
        import time
        start_time = time.perf_counter()
        
        unreal = get_unreal_connection()
        if not unreal:
            return {"success": False, "message": "Failed to connect to Unreal Engine"}
        
        logger.info(f"Creating aqueduct: {arches} arches, {tiers} tiers, radius={arch_radius}")
        
        all_actors = []
        
        # Calculate dimensions
        total_length = arches * (2 * arch_radius + pier_width) + pier_width
        
        # Calculate expected actor counts for dry run
        if dry_run:
            # Arch segments per arch based on semicircle circumference
            arch_circumference = math.pi * arch_radius
            segments_per_arch = max(4, int(arch_circumference / module_size))
            expected_arch_segments = tiers * arches * segments_per_arch
            
            # Piers: (arches + 1) per tier
            expected_piers = tiers * (arches + 1)
            
            # Deck segments including side walls
            deck_length_segments = max(1, int(total_length / module_size))
            deck_width_segments = max(1, int(deck_width / module_size))
            expected_deck = deck_length_segments * deck_width_segments
            expected_deck += 2 * deck_length_segments  # Side walls
            
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            
            return {
                "success": True,
                "dry_run": True,
                "metrics": {
                    "total_actors": expected_arch_segments + expected_piers + expected_deck,
                    "arch_segments": expected_arch_segments,
                    "pier_count": expected_piers,
                    "tiers": tiers,
                    "deck_segments": expected_deck,
                    "total_length": total_length,
                    "est_area": total_length * deck_width,
                    "elapsed_ms": elapsed_ms
                }
            }
        
        # Build the aqueduct structure
        counts = build_aqueduct_structure(
            unreal,
            arches,
            arch_radius,
            pier_width,
            tiers,
            deck_width,
            module_size,
            location,
            orientation,
            name_prefix,
            arch_mesh,
            pier_mesh,
            deck_mesh,
            all_actors
        )
        
        # Calculate metrics
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        total_actors = sum(counts.values())
        
        logger.info(f"Aqueduct construction complete: {total_actors} actors in {elapsed_ms}ms")
        
        return {
            "success": True,
            "message": f"Created {tiers}-tier aqueduct with {arches} arches ({total_actors} components)",
            "actors": all_actors,
            "metrics": {
                "total_actors": total_actors,
                "arch_segments": counts["arch_segments"],
                "pier_count": counts["piers"],
                "tiers": tiers,
                "deck_segments": counts["deck_segments"],
                "total_length": total_length,
                "est_area": total_length * deck_width,
                "elapsed_ms": elapsed_ms
            }
        }
        
    except Exception as e:
        logger.error(f"create_aqueduct error: {e}")
        return {"success": False, "message": str(e)}



# ============================================================================
# Blueprint Node Graph Tool
# ============================================================================

@mcp.tool()
def add_print_node(
    blueprint_name: str,
    message: str = "Hello World",
    pos_x: float = 0,
    pos_y: float = 0
) -> Dict[str, Any]:
    """
    Add a Print String node to a Blueprint.
    
    !!! CRITICAL LAYOUT RULES FOR AI !!!
    - You MUST space out nodes properly to ensure the graph is BEAUTIFUL, CLEAN, and ORGANIZED.
    - NEVER leave multiple nodes at (0,0) or overlapping.
    - Standard spacing: add at least +250 to pos_x for each subsequent logic step.
    - Stack parallel nodes (like events or separate branches) with at least +150 to pos_y.
    - Treat graph organization as a strict requirement. Don't mix them up!
    
    A convenience tool for adding debug print nodes without needing to know
    the underlying node types or complex parameters.
    
    Args:
        blueprint_name: Name of the Blueprint to modify
        message: The text to print to the screen/log
        pos_x: X position in graph
        pos_y: Y position in graph
        
    Returns:
        Dictionary with success status and node_id
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        result = node_manager.add_print_node(
            unreal,
            blueprint_name,
            message,
            pos_x,
            pos_y
        )
        return result
    except Exception as e:
        logger.error(f"add_print_node error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def add_node(
    blueprint_name: str,
    node_type: str,
    pos_x: float = 0,
    pos_y: float = 0,
    message: str = "",
    event_type: str = "BeginPlay",
    variable_name: str = "",
    target_function: str = "",
    target_blueprint: Optional[str] = None,
    function_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Add a node to a Blueprint graph.

    !!! CRITICAL LAYOUT RULES FOR AI !!!
    - You MUST space out nodes properly to ensure the graph is BEAUTIFUL, CLEAN, and ORGANIZED.
    - NEVER leave multiple nodes at (0,0) or overlapping.
    - Standard spacing: add at least +300 to pos_x for each subsequent sequence step.
    - Stack parallel nodes (like events or separate branches) with at least +200 to pos_y.
    - Treat graph organization as a strict requirement. Don't mix them up!

    Create various types of K2Nodes in a Blueprint's event graph or function graph.
    Supports 23 node types organized by category.

    Args:
        blueprint_name: Name of the Blueprint to modify
        node_type: Type of node to create. Supported types (23 total):

            CONTROL FLOW:
                "Branch" - Conditional execution (if/then/else)
                "Comparison" - Arithmetic/logical operators (==, !=, <, >, AND, OR, etc.)
                    ℹ️ Types can be changed via set_node_property with action="set_pin_type"
                "Switch" - Switch on byte/enum value with cases
                    ℹ️ Creates 1 pin at creation; add more via set_node_property with action="add_pin"
                "SwitchEnum" - Switch on enum type (auto-generates pins per enum value)
                    ℹ️ Creates pins based on enum; change enum via set_node_property with action="set_enum_type"
                "SwitchInteger" - Switch on integer value with cases
                    ℹ️ Creates 1 pin at creation; add more via set_node_property with action="add_pin"
                "ExecutionSequence" - Sequential execution with multiple outputs
                    ℹ️ Creates 1 pin at creation; add/remove via set_node_property (add_pin/remove_pin)

            DATA:
                "VariableGet" - Read a variable value (⚠️ variable must exist in Blueprint)
                "VariableSet" - Set a variable value (⚠️ variable must exist and be assignable)
                "MakeArray" - Create array from individual inputs
                    ℹ️ Creates 1 pin at creation; add/remove via set_node_property with action="set_num_elements"

            CASTING:
                "DynamicCast" - Cast object to specific class (⚠️ handle "Cast Failed" output)
                "ClassDynamicCast" - Cast class reference to derived class (⚠️ handle failure cases)
                "CastByteToEnum" - Convert byte value to enum (⚠️ byte must be valid enum range)

            UTILITY:
                "Print" - Debug output to screen/log (configurable duration and color)
                "CallFunction" - Call any blueprint/engine function (⚠️ function must exist)
                "Select" - Choose between two inputs based on boolean condition
                "SpawnActor" - Spawn actor from class (⚠️ class must derive from Actor)

            SPECIALIZED:
                "Timeline" - Animation timeline playback with curve tracks
                    ⚠️ REQUIRES MANUAL IMPLEMENTATION: Animation curves must be added in editor
                "GetDataTableRow" - Query row from data table (⚠️ DataTable must exist)
                "AddComponentByClass" - Dynamically add component to actor
                "Self" - Reference to current actor/object
                "Knot" - Invisible reroute node (wire organization only)

            EVENT:
                "Event" - Blueprint event (specify event_type: BeginPlay, Tick, etc.)
                    ℹ️ Tick events run every frame - be mindful of performance impact

        pos_x: X position in graph (default: 0)
        pos_y: Y position in graph (default: 0)
        message: For Print nodes, the text to print
        event_type: For Event nodes, the event name (BeginPlay, Tick, Destroyed, etc.)
        variable_name: For Variable nodes, the variable name
        target_function: For CallFunction nodes, the function to call
        target_blueprint: For CallFunction nodes, optional path to target Blueprint
        function_name: Optional name of function graph to add node to (if None, uses EventGraph)

    Returns:
        Dictionary with success status, node_id, and position

    Important Notes:
        - Most nodes can have pins modified after creation via set_node_property
        - Dynamic pin management: Switch/SwitchEnum/ExecutionSequence/MakeArray support pin operations
        - Timeline is the ONLY node requiring manual implementation (curves must be added in editor)
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}

    try:
        node_params = {
            "pos_x": pos_x,
            "pos_y": pos_y
        }

        if message:
            node_params["message"] = message
        if event_type:
            node_params["event_type"] = event_type
        if variable_name:
            node_params["variable_name"] = variable_name
        if target_function:
            node_params["target_function"] = target_function
        if target_blueprint:
            node_params["target_blueprint"] = target_blueprint
        if function_name:
            node_params["function_name"] = function_name

        result = node_manager.add_node(
            unreal,
            blueprint_name,
            node_type,
            node_params
        )

        return result

    except Exception as e:
        logger.error(f"add_node error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def connect_nodes(
    blueprint_name: str,
    source_node_id: str,
    source_pin_name: str,
    target_node_id: str,
    target_pin_name: str,
    function_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Connect two nodes in a Blueprint graph.

    Links a source pin to a target pin between existing nodes in a Blueprint's event graph or function graph.

    Args:
        blueprint_name: Name of the Blueprint to modify
        source_node_id: ID of the source node
        source_pin_name: Name of the output pin on the source node
        target_node_id: ID of the target node
        target_pin_name: Name of the input pin on the target node
        function_name: Optional name of function graph (if None, uses EventGraph)

    Returns:
        Dictionary with success status and connection details
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}

    try:
        result = connector_manager.connect_nodes(
            unreal,
            blueprint_name,
            source_node_id,
            source_pin_name,
            target_node_id,
            target_pin_name,
            function_name
        )

        return result
    except Exception as e:
        logger.error(f"connect_nodes error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def create_variable(
    blueprint_name: str,
    variable_name: str,
    variable_type: str,
    default_value: Any = None,
    is_public: bool = False,
    tooltip: str = "",
    category: str = "Default"
) -> Dict[str, Any]:
    """
    Create a variable in a Blueprint.

    Adds a new variable to a Blueprint with specified type, default value, and properties.

    Args:
        blueprint_name: Name of the Blueprint to modify
        variable_name: Name of the variable to create
        variable_type: Type of the variable ("bool", "int", "float", "string", "vector", "rotator")
        default_value: Default value for the variable (optional)
        is_public: Whether the variable should be public/editable (default: False)
        tooltip: Tooltip text for the variable (optional)
        category: Category for organizing variables (default: "Default")

    Returns:
        Dictionary with success status and variable details
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}

    try:
        result = variable_manager.create_variable(
            unreal,
            blueprint_name,
            variable_name,
            variable_type,
            default_value,
            is_public,
            tooltip,
            category
        )

        return result
    except Exception as e:
        logger.error(f"create_variable error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def set_blueprint_variable_properties(
    blueprint_name: str,
    variable_name: str,
    var_name: Optional[str] = None,
    var_type: Optional[str] = None,
    is_blueprint_readable: Optional[bool] = None,
    is_blueprint_writable: Optional[bool] = None,
    is_public: Optional[bool] = None,
    is_editable_in_instance: Optional[bool] = None,
    tooltip: Optional[str] = None,
    category: Optional[str] = None,
    default_value: Any = None,
    expose_on_spawn: Optional[bool] = None,
    expose_to_cinematics: Optional[bool] = None,
    slider_range_min: Optional[str] = None,
    slider_range_max: Optional[str] = None,
    value_range_min: Optional[str] = None,
    value_range_max: Optional[str] = None,
    units: Optional[str] = None,
    bitmask: Optional[bool] = None,
    bitmask_enum: Optional[str] = None,
    replication_enabled: Optional[bool] = None,
    replication_condition: Optional[int] = None,
    is_private: Optional[bool] = None
) -> Dict[str, Any]:
    """
    Modify properties of an existing Blueprint variable without deleting it.

    Preserves all VariableGet and VariableSet nodes connected to this variable.

    Args:
        blueprint_name: Name of the Blueprint to modify
        variable_name: Name of the variable to modify

        var_name: Rename the variable (optional)
            ✅ PASS - VarDesc->VarName works correctly

        var_type: Change variable type (optional)
            ✅ PASS - VarDesc->VarType works correctly (int→float returns "real")

        is_blueprint_readable: Allow reading in Blueprint (VariableGet) (optional)
            ✅ PASS - CPF_BlueprintReadOnly flag (inverted logic)

        is_blueprint_writable: Allow writing in Blueprint (Set) (optional)
            ✅ PASS - CPF_BlueprintReadOnly flag (inverted logic)
            ⚠️ NOT returned by get_variable_details()

        is_public: Visible in Blueprint editor (optional)
            ✅ PASS - Controls variable visibility

        is_editable_in_instance: Modifiable on instances (optional)
            ✅ PASS - CPF_DisableEditOnInstance flag (inverted logic)

        tooltip: Variable description (optional)
            ✅ PASS - Metadata MD_Tooltip works correctly

        category: Variable category (optional)
            ✅ PASS - Direct property Category works

        default_value: New default value (optional)
            ✅ PASS - Works but get_variable_details() returns empty string

        expose_on_spawn: Show in spawn dialog (optional)
            ✅ PASS - Metadata MD_ExposeOnSpawn works
            ⚠️ Requires is_editable_in_instance=true to be visible
            ⚠️ NOT returned by get_variable_details()

        expose_to_cinematics: Expose to cinematics (optional)
            ✅ PASS - CPF_Interp flag works correctly
            ⚠️ NOT returned by get_variable_details()

        slider_range_min: UI slider minimum value (optional)
            ✅ PASS - Metadata MD_UIMin works (string value)
            ⚠️ NOT returned by get_variable_details()

        slider_range_max: UI slider maximum value (optional)
            ✅ PASS - Metadata MD_UIMax works (string value)
            ⚠️ NOT returned by get_variable_details()

        value_range_min: Clamp minimum value (optional)
            ✅ PASS - Metadata MD_ClampMin works (string value)
            ⚠️ NOT returned by get_variable_details()

        value_range_max: Clamp maximum value (optional)
            ✅ PASS - Metadata MD_ClampMax works (string value)
            ⚠️ NOT returned by get_variable_details()

        units: Display units (optional)
            ⚠️ PARTIAL - Metadata MD_Units works for value display (e.g., "0.0 cm")
            ❌ UI dropdown stays at "None" (Unreal Editor limitation - dropdown doesn't sync with metadata)
            ⚠️ Use long format: "Centimeters", "Meters" (not "cm", "m")
            ⚠️ NOT returned by get_variable_details()

        bitmask: Treat as bitmask (optional)
            ✅ PASS - Metadata TEXT("Bitmask") works correctly
            ⚠️ NOT returned by get_variable_details()

        bitmask_enum: Bitmask enum type (optional)
            ✅ PASS - Metadata TEXT("BitmaskEnum") works
            ⚠️ REQUIRES full path format: "/Script/ModuleName.EnumName"
            ❌ Short names generate warning and don't sync dropdown
            ✅ Validated enums (use FULL PATHS):
                - /Script/UniversalObjectLocator.ELocatorResolveFlags
                - /Script/JsonObjectGraph.EJsonStringifyFlags
                - /Script/MediaAssets.EMediaAudioCaptureDeviceFilter
                - /Script/MediaAssets.EMediaVideoCaptureDeviceFilter
                - /Script/MediaAssets.EMediaWebcamCaptureDeviceFilter
                - /Script/Engine.EAnimAssetCurveFlags
                - /Script/Engine.EHardwareDeviceSupportedFeatures
                - /Script/EnhancedInput.EMappingQueryIssue
                - /Script/EnhancedInput.ETriggerEvent
            ⚠️ NOT returned by get_variable_details()

        replication_enabled: Enable network replication (CPF_Net flag) (optional)
            ✅ PASS - CPF_Net flag works - Changes "Replication" dropdown (None ↔ Replicated)
            ⚠️ NOT returned by get_variable_details()

        replication_condition: Network replication condition (ELifetimeCondition 0-7) (optional)
            ✅ PASS - VarDesc->ReplicationCondition works
            ✅ Changes "Replication Condition" dropdown (e.g., None → Initial Only)
            ⚠️ Values: 0=None, 1=InitialOnly, 2=OwnerOnly, 3=SkipOwner, 4=SimulatedOnly, 5=AutonomousOnly, 6=SimulatedOrPhysics, 7=InitialOrOwner
            ✅ Returned by get_variable_details() as "replication"

        is_private: Set variable as private (optional)
            ❌ UNRESOLVED - Property flag/metadata not yet identified
            ⚠️ Attempted CPF_NativeAccessSpecifierPrivate flag and MD_AllowPrivateAccess metadata - neither work
            ⚠️ The property that controls "Privé" (Private) checkbox remains unknown
            ⚠️ Parameter exists but has no effect on UI - do NOT use until resolved

    Returns:
        Dictionary with success status and updated properties
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}

    try:
        result = variable_manager.set_blueprint_variable_properties(
            unreal,
            blueprint_name,
            variable_name,
            var_name,
            var_type,
            is_blueprint_readable,
            is_blueprint_writable,
            is_public,
            is_editable_in_instance,
            tooltip,
            category,
            default_value,
            expose_on_spawn,
            expose_to_cinematics,
            slider_range_min,
            slider_range_max,
            value_range_min,
            value_range_max,
            units,
            bitmask,
            bitmask_enum,
            replication_enabled,
            replication_condition,
            is_private
        )

        return result
    except Exception as e:
        logger.error(f"set_blueprint_variable_properties error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def add_event_node(
    blueprint_name: str,
    event_name: str,
    pos_x: float = 0,
    pos_y: float = 0
) -> Dict[str, Any]:
    """
    Add an event node to a Blueprint graph.

    !!! CRITICAL LAYOUT RULES FOR AI !!!
    - You MUST space out nodes properly to ensure the graph is BEAUTIFUL, CLEAN, and ORGANIZED.
    - NEVER leave multiple nodes at (0,0) or overlapping.
    - Standard spacing: add at least +300 to pos_x for each subsequent logic step.
    - Stack parallel nodes (like events or separate branches) with at least +200 to pos_y.
    - Treat graph organization as a strict requirement. Don't mix them up!

    Create specialized event nodes (ReceiveBeginPlay, ReceiveTick, etc.)
    in a Blueprint's event graph at specified positions.

    Supports keyboard/mouse input keys as well by passing the key name (e.g., "F", "SpaceBar", "LeftMouseButton").

    Args:
        blueprint_name: Name of the Blueprint to modify
        event_name: Name of the event or Input Key (e.g., "ReceiveBeginPlay", "F", "Enter")
        pos_x: X position in graph (default: 0)
        pos_y: Y position in graph (default: 0)

    Returns:
        Dictionary with success status, node_id, event_name, and position
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}

    try:
        result = event_manager.add_event_node(
            unreal,
            blueprint_name,
            event_name,
            pos_x,
            pos_y
        )

        return result
    except Exception as e:
        logger.error(f"add_event_node error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def add_input_key_node(
    blueprint_name: str,
    key_name: str,
    pos_x: float = 0,
    pos_y: float = 0
) -> Dict[str, Any]:
    """
    Add an Input Key node (like 'F' key, 'SpaceBar', etc.) to a Blueprint.

    !!! CRITICAL LAYOUT RULES FOR AI !!!
    - You MUST space out nodes properly to ensure the graph is BEAUTIFUL, CLEAN, and ORGANIZED.
    - NEVER leave multiple nodes at (0,0) or overlapping.
    - Standard spacing: add at least +300 to pos_x for each subsequent logic step.
    - Stack parallel nodes (like events or separate branches) with at least +200 to pos_y.
    - Treat graph organization as a strict requirement. Don't mix them up!

    Args:
        blueprint_name: Name of the Blueprint to modify
        key_name: Name of the key (e.g., "F", "Enter", "SpaceBar", "LeftMouseButton")
        pos_x: X position in graph (default: 0)
        pos_y: Y position in graph (default: 0)

    Returns:
        Dictionary with success status and node_id
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}

    try:
        # Internally uses the same add_event_node command which now handles keys
        result = event_manager.add_event_node(
            unreal,
            blueprint_name,
            key_name,
            pos_x,
            pos_y
        )
        return result
    except Exception as e:
        logger.error(f"add_input_key_node error: {e}")
        return {"success": False, "message": str(e)}


@mcp.tool()
def delete_node(
    blueprint_name: str,
    node_id: str,
    function_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delete a node from a Blueprint graph.

    Removes a node and all its connections from either the EventGraph
    or a specific function graph.

    Args:
        blueprint_name: Name of the Blueprint to modify
        node_id: ID of the node to delete (NodeGuid or node name)
        function_name: Name of function graph (optional, defaults to EventGraph)

    Returns:
        Dictionary with success status and deleted_node_id
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}

    try:
        result = node_deleter.delete_node(
            unreal,
            blueprint_name,
            node_id,
            function_name
        )
        return result
    except Exception as e:
        logger.error(f"delete_node error: {e}")
        return {"success": False, "message": str(e)}


@mcp.tool()
def set_node_property(
    blueprint_name: str,
    node_id: str,
    property_name: str = "",
    property_value: Any = None,
    function_name: Optional[str] = None,
    action: Optional[str] = None,
    pin_type: Optional[str] = None,
    pin_name: Optional[str] = None,
    enum_type: Optional[str] = None,
    new_type: Optional[str] = None,
    target_type: Optional[str] = None,
    target_function: Optional[str] = None,
    target_class: Optional[str] = None,
    event_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Set a property on a Blueprint node or perform semantic node editing.

    This function supports both simple property modifications and advanced semantic
    node editing operations (pin management, type modifications, reference updates).

    Args:
        blueprint_name: Name of the Blueprint to modify
        node_id: ID of the node to modify
        property_name: Name of property to set (legacy mode, used if action not specified)
        property_value: Value to set (legacy mode)
        function_name: Name of function graph (optional, defaults to EventGraph)
        action: Semantic action to perform - can be one of:
            Phase 1 (Pin Management):
                - "add_pin": Add a pin to a node (requires pin_type)
                - "remove_pin": Remove a pin from a node (requires pin_name)
                - "set_enum_type": Set enum type on a node (requires enum_type)
            Phase 2 (Type Modification):
                - "set_pin_type": Change pin type on comparison nodes (requires pin_name, new_type)
                - "set_value_type": Change value type on select nodes (requires new_type)
                - "set_cast_target": Change cast target type (requires target_type)
            Phase 3 (Reference Updates - DESTRUCTIVE):
                - "set_function_call": Change function being called (requires target_function)
                - "set_event_type": Change event type (requires event_type)

    Semantic action parameters:
        pin_type: Type of pin to add ("SwitchCase", "ExecutionOutput", "ArrayElement", "EnumValue")
        pin_name: Name of pin to remove or modify
        enum_type: Full path to enum type (e.g., "/Game/Enums/ECardinalDirection")
        new_type: New type for pin or value ("int", "float", "string", "bool", "vector", etc.)
        target_type: Target class path for casting
        target_function: Name of function to call
        target_class: Optional class containing the function
        event_type: Event type (e.g., "BeginPlay", "Tick", "Destroyed")

    Returns:
        Dictionary with success status and details

    Supported legacy properties by node type:
        - Print nodes: "message", "duration", "text_color"
        - Variable nodes: "variable_name"
        - All nodes: "pos_x", "pos_y", "comment"

    Examples:
        Legacy mode (set simple property):
            set_node_property(
                blueprint_name="MyActorBlueprint",
                node_id="K2Node_1234567890",
                property_name="message",
                property_value="Hello World!"
            )

        Semantic mode (add pin):
            set_node_property(
                blueprint_name="MyActorBlueprint",
                node_id="K2Node_Switch_123",
                action="add_pin",
                pin_type="SwitchCase"
            )

        Semantic mode (set enum type):
            set_node_property(
                blueprint_name="MyActorBlueprint",
                node_id="K2Node_SwitchEnum_456",
                action="set_enum_type",
                enum_type="ECardinalDirection"
            )

        Semantic mode (change function call):
            set_node_property(
                blueprint_name="MyActorBlueprint",
                node_id="K2Node_CallFunction_789",
                action="set_function_call",
                target_function="BeginPlay",
                target_class="APawn"
            )
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}

    try:
        # Build kwargs for semantic actions
        kwargs = {}
        if action is not None:
            if pin_type is not None:
                kwargs["pin_type"] = pin_type
            if pin_name is not None:
                kwargs["pin_name"] = pin_name
            if enum_type is not None:
                kwargs["enum_type"] = enum_type
            if new_type is not None:
                kwargs["new_type"] = new_type
            if target_type is not None:
                kwargs["target_type"] = target_type
            if target_function is not None:
                kwargs["target_function"] = target_function
            if target_class is not None:
                kwargs["target_class"] = target_class
            if event_type is not None:
                kwargs["event_type"] = event_type

        result = node_properties.set_node_property(
            unreal,
            blueprint_name,
            node_id,
            property_name,
            property_value,
            function_name,
            action,
            **kwargs
        )
        return result
    except Exception as e:
        logger.error(f"set_node_property error: {e}", exc_info=True)
        return {"success": False, "message": str(e)}


@mcp.tool()
def create_function(
    blueprint_name: str,
    function_name: str,
    return_type: str = "void"
) -> Dict[str, Any]:
    """
    Create a new function in a Blueprint.

    Args:
        blueprint_name: Name of the Blueprint to modify
        function_name: Name for the new function
        return_type: Return type of the function (default: "void")

    Returns:
        Dictionary with function_name, graph_id or error
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}

    try:
        result = function_manager.create_function_handler(
            unreal,
            blueprint_name,
            function_name,
            return_type
        )
        return result
    except Exception as e:
        logger.error(f"create_function error: {e}")
        return {"success": False, "message": str(e)}


@mcp.tool()
def add_function_input(
    blueprint_name: str,
    function_name: str,
    param_name: str,
    param_type: str,
    is_array: bool = False
) -> Dict[str, Any]:
    """
    Add an input parameter to a Blueprint function.

    Args:
        blueprint_name: Name of the Blueprint to modify
        function_name: Name of the function
        param_name: Name of the input parameter
        param_type: Type of the parameter (bool, int, float, string, vector, etc.)
        is_array: Whether the parameter is an array (default: False)

    Returns:
        Dictionary with param_name, param_type, and direction or error
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}

    try:
        result = function_io.add_function_input_handler(
            unreal,
            blueprint_name,
            function_name,
            param_name,
            param_type,
            is_array
        )
        return result
    except Exception as e:
        logger.error(f"add_function_input error: {e}")
        return {"success": False, "message": str(e)}


@mcp.tool()
def add_function_output(
    blueprint_name: str,
    function_name: str,
    param_name: str,
    param_type: str,
    is_array: bool = False
) -> Dict[str, Any]:
    """
    Add an output parameter to a Blueprint function.

    Args:
        blueprint_name: Name of the Blueprint to modify
        function_name: Name of the function
        param_name: Name of the output parameter
        param_type: Type of the parameter (bool, int, float, string, vector, etc.)
        is_array: Whether the parameter is an array (default: False)

    Returns:
        Dictionary with param_name, param_type, and direction or error
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}

    try:
        result = function_io.add_function_output_handler(
            unreal,
            blueprint_name,
            function_name,
            param_name,
            param_type,
            is_array
        )
        return result
    except Exception as e:
        logger.error(f"add_function_output error: {e}")
        return {"success": False, "message": str(e)}


@mcp.tool()
def delete_function(
    blueprint_name: str,
    function_name: str
) -> Dict[str, Any]:
    """
    Delete a function from a Blueprint.

    Args:
        blueprint_name: Name of the Blueprint to modify
        function_name: Name of the function to delete

    Returns:
        Dictionary with deleted_function_name or error
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}

    try:
        result = function_manager.delete_function_handler(
            unreal,
            blueprint_name,
            function_name
        )
        return result
    except Exception as e:
        logger.error(f"delete_function error: {e}")
        return {"success": False, "message": str(e)}


@mcp.tool()
def rename_function(
    blueprint_name: str,
    old_function_name: str,
    new_function_name: str
) -> Dict[str, Any]:
    """
    Rename a function in a Blueprint.

    Args:
        blueprint_name: Name of the Blueprint to modify
        old_function_name: Current name of the function
        new_function_name: New name for the function

    Returns:
        Dictionary with new_function_name or error
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}

    try:
        result = function_manager.rename_function_handler(
            unreal,
            blueprint_name,
            old_function_name,
            new_function_name
        )
        return result
    except Exception as e:
        logger.error(f"rename_function error: {e}")
        return {"success": False, "message": str(e)}


# Run the server




# ============================================================================
# CODE EXECUTION TOOLS
# ============================================================================

@mcp.tool()
def execute_code(
    code: str,
    session_id: Optional[str] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Execute Python code in a secure sandboxed environment.
    
    This tool allows AI agents to write and execute Python code dynamically,
    enabling complex operations, calculations, and iterations that would be
    difficult with individual tool calls.
    
    Features:
    - Secure Docker-based sandboxing
    - Stateful sessions (variables persist across executions)
    - Resource limits (CPU, memory, timeout)
    - No network access
    - Read-only filesystem
    
    Args:
        code: Python code to execute
        session_id: Optional session ID for stateful execution (creates new if None)
        timeout: Maximum execution time in seconds (default: 30)
    
    Returns:
        Dictionary with execution results including stdout, stderr, and session_id
    
    Example:
        # Create 100 buildings in a loop
        execute_code('''
import unreal_mcp_server_advanced as server

for i in range(100):
    x = i * 500
    server.construct_house(
        location_x=x,
        location_y=0,
        location_z=0,
        house_type="modern",
        num_floors=2
    )
print(f"Created 100 houses")
        ''')
    """
    try:
        result = execute_python_code(code, session_id, timeout)
        return result
    except Exception as e:
        logger.error(f"execute_code error: {e}")
        return {
            "success": False,
            "error": str(e),
            "stdout": "",
            "stderr": str(e)
        }


@mcp.tool()
def execute_client_script(code: str) -> Dict[str, Any]:
    """
    Execute Python code on the MCP server with direct access to Unreal Engine commands.
    
    This tool allows running scripts that can send commands to Unreal via 'send_command(cmd, params)'.
    This is useful for complex logic that requires multiple steps or conditional execution based on Unreal's state,
    without creating temporary files.
    
    Args:
        code: Python code to execute. Use 'send_command(command_name, params)' to talk to Unreal.
        
    Returns:
        Dictionary with execution results (stdout, stderr).
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
        
    # Define the helper function to be available in the script
    def send_command(command: str, params: Dict[str, Any] = None):
        return unreal.send_command(command, params)
        
    # Capture stdout/stderr
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    try:
        with contextlib.redirect_stdout(stdout_capture), \
             contextlib.redirect_stderr(stderr_capture):
            
            # Execute with a single scope so functions can access helpers
            # We provide full builtins to allow imports and standard library usage
            scope = {
                "send_command": send_command,
                "print": print,
                "__builtins__": __builtins__
            }
            
            exec(code, scope)
            
        return {
            "success": True,
            "stdout": stdout_capture.getvalue(),
            "stderr": stderr_capture.getvalue()
        }
    except Exception as e:
        logger.error(f"execute_client_script error: {e}")
        return {
            "success": False,
            "error": str(e),
            "stdout": stdout_capture.getvalue(),
            "stderr": stderr_capture.getvalue() + f"\nError: {str(e)}"
        }

@mcp.tool()
def execute_unreal_python(code: str) -> Dict[str, Any]:
    """
    Execute Python code directly inside the Unreal Engine Editor process.
    
    This tool provides full access to the 'unreal' API, allowing for 
    modification of assets, blueprints, actor properties, and editor states.
    
    Args:
        code: The Python code to execute in Unreal Editor.
        
    Returns:
        Dictionary with success status and any result from Unreal.
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        # Use the 'execute_python' command supported by the C++ bridge
        response = unreal.send_command("execute_python", {"code": code})
        return response
    except Exception as e:
        logger.error(f"execute_unreal_python error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def create_code_session() -> Dict[str, Any]:
    """
    Create a new code execution session.
    
    Sessions allow variables and state to persist across multiple
    code executions, enabling iterative and stateful workflows.
    
    Returns:
        Dictionary with session_id
    """
    try:
        session_id = create_execution_session()
        return {
            "success": True,
            "session_id": session_id
        }
    except Exception as e:
        logger.error(f"create_code_session error: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
def reset_code_session(session_id: str) -> Dict[str, Any]:
    """
    Reset a code execution session (clear all variables and history).
    
    Args:
        session_id: Session ID to reset
    
    Returns:
        Dictionary with success status
    """
    try:
        success = reset_execution_session(session_id)
        return {
            "success": success,
            "message": "Session reset successfully" if success else "Session not found"
        }
    except Exception as e:
        logger.error(f"reset_code_session error: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
def get_code_session_info(session_id: str) -> Dict[str, Any]:
    """
    Get information about a code execution session.
    
    Args:
        session_id: Session ID to query
    
    Returns:
        Dictionary with session information
    """
    try:
        info = get_session_info(session_id)
        if info:
            return {
                "success": True,
                **info
            }
        else:
            return {
                "success": False,
                "message": "Session not found"
            }
    except Exception as e:
        logger.error(f"get_code_session_info error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


from helpers.agent_memory import save_note, get_notes, search_notes

# ============================================================================
# AGENT MEMORY TOOLS
# ============================================================================

@mcp.tool()
def add_agent_note(title: str, content: str, category: str = "general") -> Dict[str, Any]:
    """
    Save a persistent note about the project, blueprints, or tasks.
    Useful for maintaining context across sessions.
    """
    success = save_note(title, content, category)
    return {"success": success, "message": "Note saved" if success else "Failed to save note"}

@mcp.tool()
def search_agent_notes(query: str) -> Dict[str, Any]:
    """Search through persistent agent notes."""
    results = search_notes(query)
    return {"success": True, "count": len(results), "notes": results}

@mcp.tool()
def list_agent_notes() -> Dict[str, Any]:
    """List all persistent agent notes."""
    results = get_notes()
    return {"success": True, "count": len(results), "notes": results}

# ============================================================================
# BLUEPRINT ANALYSIS TOOLS
# ============================================================================

@mcp.tool()
def import_blueprint_t3d_tool(
    blueprint_name: str,
    t3d_content: str,
    pos_x: float = 0,
    pos_y: float = 0,
    graph_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Import Blueprint nodes from T3D (Textual Unreal Data) format.
    This allows importing a cluster of nodes copied from the Unreal Editor.
    
    Args:
        blueprint_name: Name of the target Blueprint
        t3d_content: The T3D text content (usually starts with 'Begin Object')
        pos_x, pos_y: Offset to apply to imported nodes
        graph_name: Optional name of the graph (defaults to EventGraph)
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        response = unreal.send_command("import_nodes_from_t3d", {
            "blueprint_name": blueprint_name,
            "t3d_content": t3d_content,
            "pos_x": pos_x,
            "pos_y": pos_y,
            "graph_name": graph_name
        })
        return response
    except Exception as e:
        logger.error(f"import_blueprint_t3d_tool error: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
def analyze_blueprint_complexity_tool(blueprint_name: str) -> Dict[str, Any]:
    """
    Analyze the complexity of a Blueprint graph.
    
    Provides metrics including:
    - Node count
    - Connection count
    - Cyclomatic complexity
    - Max depth
    - Branch points
    - Dead code detection
    - Node type distribution
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        response = unreal.send_command("analyze_blueprint_graph", {
            "blueprint_path": blueprint_name,
            "graph_name": "EventGraph",
            "include_node_details": True,
            "include_pin_connections": True
        })
        
        # C++ backend returns {"status": "success", "result": {...}}
        # NOT {"success": True} — check both for compatibility
        is_ok = (
            response and
            (response.get("status") == "success" or response.get("success") is True)
        )
        if not is_ok:
            error = response.get("error") or response.get("message", "Unknown error") if response else "No response"
            return {"success": False, "message": f"Failed to analyze Blueprint: {error}"}
        
        # Graph data may be nested under "result" or directly in response
        result = response.get("result", response)
        graph_data = result.get("graph_data") or result.get("graph") or result
        complexity = analyze_graph_complexity(graph_data)
        
        return {
            "success": True,
            "blueprint_name": blueprint_name,
            **complexity
        }
    except Exception as e:
        logger.error(f"analyze_blueprint_complexity_tool error: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
def find_blueprint_issues_tool(blueprint_name: str) -> Dict[str, Any]:
    """Find potential issues in a Blueprint graph (dead code, infinite loops, etc.)."""
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        response = unreal.send_command("analyze_blueprint_graph", {
            "blueprint_path": blueprint_name,
            "graph_name": "EventGraph",
            "include_node_details": True,
            "include_pin_connections": True
        })
        
        is_ok = (
            response and
            (response.get("status") == "success" or response.get("success") is True)
        )
        if not is_ok:
            error = response.get("error") or response.get("message", "Unknown error") if response else "No response"
            return {"success": False, "message": f"Failed to analyze Blueprint: {error}"}
        
        result = response.get("result", response)
        graph_data = result.get("graph_data") or result.get("graph") or result
        issues = find_graph_issues(graph_data)
        
        return {
            "success": True,
            "blueprint_name": blueprint_name,
            "issue_count": len(issues),
            "issues": issues
        }
    except Exception as e:
        logger.error(f"find_blueprint_issues_tool error: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
def visualize_blueprint_graph_tool(
    blueprint_name: str,
    graph_name: str = "EventGraph"
) -> Dict[str, Any]:
    """Generate a Mermaid diagram visualization of a Blueprint graph."""
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        from helpers.mcp_resources import get_blueprint_graph_visualization
        diagram = get_blueprint_graph_visualization(unreal, blueprint_name, graph_name)
        
        return {
            "success": True,
            "blueprint_name": blueprint_name,
            "graph_name": graph_name,
            "diagram": diagram
        }
    except Exception as e:
        logger.error(f"visualize_blueprint_graph_tool error: {e}")
        return {"success": False, "error": str(e)}

# ============================================================================
# PROCEDURAL GENERATION TOOLS
# ============================================================================

@mcp.tool()
def generate_dungeon_wfc_tool(
    width: int,
    height: int,
    tile_size: float = 400.0,
    location_x: float = 0,
    location_y: float = 0,
    location_z: float = 0,
    name_prefix: str = "WFC_Dungeon",
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Generate a procedural dungeon using Wave Function Collapse algorithm.
    
    Args:
        width, height: dimensions of the dungeon grid
        tile_size: size of each tile
        dry_run: If True, only calculate metrics (Prevents timeouts)
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        if dry_run:
            return {
                "success": True,
                "message": f"Dry run: Would generate {width}x{height} dungeon with {width*height} tiles."
            }
            
        dungeon_data = generate_dungeon_wfc(
            width, height, tile_size,
            location_x, location_y, location_z
        )
        if not dungeon_data.get("success"):
            return dungeon_data
        
        result = spawn_wfc_dungeon(unreal, dungeon_data, name_prefix)
        return result
    except Exception as e:
        logger.error(f"generate_dungeon_wfc_tool error: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
def generate_tree_lsystem_tool(
    tree_type: str = "basic",
    iterations: int = 4,
    segment_length: float = 100.0,
    location_x: float = 0,
    location_y: float = 0,
    location_z: float = 0,
    name_prefix: str = "LSystem_Tree",
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Generate a procedural tree using L-Systems.
    
    Args:
        tree_type: Style of tree
        dry_run: If True, only calculate metrics (Prevents timeouts)
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        if dry_run:
            return {
                "success": True,
                "message": f"Dry run: Would generate {tree_type} tree with {iterations} iterations."
            }
            
        tree_data = generate_tree_lsystem(
            tree_type, iterations, segment_length,
            location_x, location_y, location_z
        )
        if not tree_data.get("success"):
            return tree_data
        
        result = spawn_lsystem_tree(unreal, tree_data, name_prefix)
        return result
    except Exception as e:
        logger.error(f"generate_tree_lsystem_tool error: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
def generate_vegetation_field_tool(
    center_x: float,
    center_y: float,
    size: float,
    density: int = 20,
    tree_type: str = "basic",
    location_z: float = 0,
    name_prefix: str = "Vegetation",
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Generate a field of vegetation (trees/plants) using L-Systems.
    
    Args:
        center_x, center_y: Area center
        size: Radius of area
        density: Number of trees
        dry_run: If True, only calculate metrics (Prevents timeouts)
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        if dry_run:
            return {
                "success": True,
                "message": f"Dry run: Would generate field of {density} {tree_type} trees."
            }
            
        import random
        import math
        trees_created = []
        for i in range(density):
            angle = random.uniform(0, 2 * math.pi)
            distance = random.uniform(0, size)
            tree_x = center_x + distance * math.cos(angle)
            tree_y = center_y + distance * math.sin(angle)
            iterations = random.randint(3, 5)
            segment_length = random.uniform(80, 120)
            
            tree_data = generate_tree_lsystem(
                tree_type, iterations, segment_length,
                tree_x, tree_y, location_z
            )
            if tree_data.get("success"):
                result = spawn_lsystem_tree(unreal, tree_data, f"{name_prefix}_Tree_{i}")
                if result.get("success"):
                    trees_created.append({"location": [tree_x, tree_y, location_z]})
                    
        return {"success": True, "tree_count": len(trees_created)}
    except Exception as e:
        logger.error(f"generate_vegetation_field_tool error: {e}")
        return {"success": False, "error": str(e)}

# ============================================================================
# AI & PERCEPTION TOOLS
# ============================================================================

@mcp.tool()
def ai_move_to(
    pawn_name: str,
    target_actor: str = None,
    location: List[float] = None,
    acceptance_radius: float = 5.0,
    stop_on_overlap: bool = True
) -> Dict[str, Any]:
    """
    Move an AI pawn to a specific location or actor.
    
    Args:
        pawn_name: Name of the pawn to move
        target_actor: Optional name of the actor to move towards
        location: Optional [x, y, z] coordinates to move towards
        acceptance_radius: How close to get to the target
        stop_on_overlap: Whether to stop when overlapping the target
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        pawn_name = resolve_actor_name(unreal, pawn_name)
        params = {
            "pawn_name": pawn_name,
            "acceptance_radius": acceptance_radius,
            "stop_on_overlap": stop_on_overlap
        }
        
        if target_actor:
            params["target_actor"] = resolve_actor_name(unreal, target_actor)
        elif location:
            params["location"] = location
        else:
            return {"success": False, "message": "Must provide either target_actor or location"}
            
        return unreal.send_command("ai_move_to", params)
    except Exception as e:
        logger.error(f"ai_move_to error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def run_behavior_tree(actor_name: str, bt_path: str) -> Dict[str, Any]:
    """
    Run a behavior tree on an AI character.
    
    Args:
        actor_name: Name of the actor (Pawn or AI Controller)
        bt_path: Path to the Behavior Tree asset (e.g., "/Game/AI/BT_Enemy")
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        actor_name = resolve_actor_name(unreal, actor_name)
        return unreal.send_command("run_behavior_tree", {
            "actor_name": actor_name,
            "bt_path": bt_path
        })
    except Exception as e:
        logger.error(f"run_behavior_tree error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def set_blackboard_value(
    actor_name: str,
    key_name: str,
    value: Any
) -> Dict[str, Any]:
    """
    Set a value in an AI's Blackboard.
    
    Args:
        actor_name: Name of the AI actor
        key_name: Name of the blackboard key
        value: Value to set (automatically detects type: bool, float, int, string, list for vector, str for actor name)
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        actor_name = resolve_actor_name(unreal, actor_name)
        params = {
            "actor_name": actor_name,
            "key_name": key_name
        }
        
        if isinstance(value, bool):
            params["value_bool"] = value
        elif isinstance(value, (int, float)):
            if isinstance(value, int):
                params["value_int"] = value
            else:
                params["value_float"] = value
        elif isinstance(value, str):
            # Check if it might be an actor name
            # Note: We use a separate field for object so the C++ side knows to resolve it
            params["value_object"] = value 
        elif isinstance(value, list) and len(value) == 3:
            params["value_vector"] = value
        else:
            return {"success": False, "message": "Unsupported value type for blackboard"}
            
        return unreal.send_command("set_blackboard_value", params)
    except Exception as e:
        logger.error(f"set_blackboard_value error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def get_ai_perception(actor_name: str) -> Dict[str, Any]:
    """
    Get information about what an AI currently perceives (sees/hears).
    
    Args:
        actor_name: Name of the AI actor
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        actor_name = resolve_actor_name(unreal, actor_name)
        return unreal.send_command("get_perception_info", {"actor_name": actor_name})
    except Exception as e:
        logger.error(f"get_ai_perception error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def register_perception_source(actor_name: str) -> Dict[str, Any]:
    """
    Register an actor as a source for AI perception (e.g., make it 'visible' to AI).
    
    Args:
        actor_name: Name of the actor to register
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        actor_name = resolve_actor_name(unreal, actor_name)
        return unreal.send_command("register_perception_source", {"actor_name": actor_name})
    except Exception as e:
        logger.error(f"register_perception_source error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def get_ai_status(actor_name: str) -> Dict[str, Any]:
    """
    Get the current status of an AI (is it moving? what is it doing?).
    
    Args:
        actor_name: Name of the AI actor
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        actor_name = resolve_actor_name(unreal, actor_name)
        return unreal.send_command("get_ai_status", {"actor_name": actor_name})
    except Exception as e:
        logger.error(f"get_ai_status error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def stop_ai_movement(actor_name: str) -> Dict[str, Any]:
    """
    Stop current AI movement.
    
    Args:
        actor_name: Name of the AI actor to stop
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        actor_name = resolve_actor_name(unreal, actor_name)
        return unreal.send_command("stop_ai_movement", {"actor_name": actor_name})
    except Exception as e:
        logger.error(f"stop_ai_movement error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def get_random_reachable_point(
    origin: List[float] = None,
    actor_name: str = None,
    radius: float = 1000.0
) -> Dict[str, Any]:
    """
    Get a random reachable point on the NavMesh.
    
    Args:
        origin: Optional center point [x, y, z]
        actor_name: Optional actor to use as center point
        radius: Search radius
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        params = {"radius": radius}
        if origin:
            params["origin"] = origin
        elif actor_name:
            params["actor_name"] = resolve_actor_name(unreal, actor_name)
            
        return unreal.send_command("get_random_reachable_point", params)
    except Exception as e:
        logger.error(f"get_random_reachable_point error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def run_eqs_query(
    query_path: str,
    querier_name: str = None
) -> Dict[str, Any]:
    """
    Execute an Environment Query System (EQS) query.
    
    Args:
        query_path: Path to the EQS Query asset
        querier_name: Optional actor performing the query
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        params = {"query_path": query_path}
        if querier_name:
            params["querier_name"] = resolve_actor_name(unreal, querier_name)
            
        return unreal.send_command("run_eqs_query", params)
    except Exception as e:
        logger.error(f"run_eqs_query error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def run_state_tree(actor_name: str, state_tree_path: str) -> Dict[str, Any]:
    """
    Run a StateTree on an actor.
    
    Args:
        actor_name: Name of the actor
        state_tree_path: Path to the StateTree asset (e.g., "/Game/AI/ST_Enemy")
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        actor_name = resolve_actor_name(unreal, actor_name)
        return unreal.send_command("run_state_tree", {
            "actor_name": actor_name,
            "state_tree_path": state_tree_path
        })
    except Exception as e:
        logger.error(f"run_state_tree error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def send_state_tree_event(actor_name: str, event_name: str) -> Dict[str, Any]:
    """
    Send an event to a running StateTree.
    
    Args:
        actor_name: Name of the actor
        event_name: Name of the event (Gameplay Tag)
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        actor_name = resolve_actor_name(unreal, actor_name)
        return unreal.send_command("send_state_tree_event", {
            "actor_name": actor_name,
            "event_name": event_name
        })
    except Exception as e:
        logger.error(f"send_state_tree_event error: {e}")
        return {"success": False, "message": str(e)}

@mcp.tool()
def spawn_mass_crowd(
    config_path: str,
    count: int = 100,
    center: List[float] = [0, 0, 0],
    radius: float = 1000.0
) -> Dict[str, Any]:
    """
    Spawn a crowd of Mass entities.
    
    Args:
        config_path: Path to the Mass Entity Config asset
        count: Number of entities to spawn
        center: Center point [x, y, z]
        radius: Radius for random placement
    """
    unreal = get_unreal_connection()
    if not unreal:
        return {"success": False, "message": "Failed to connect to Unreal Engine"}
    
    try:
        return unreal.send_command("spawn_mass_crowd", {
            "config_path": config_path,
            "count": count,
            "center": center,
            "radius": radius
        })
    except Exception as e:
        logger.error(f"spawn_mass_crowd error: {e}")
        return {"success": False, "message": str(e)}

# ML Bridge Internal States
ml_agents = {}

def initialize_ml_agent(model_class: str, model_path: str = None) -> Any:
    """Internal helper called by C++ ML Bridge."""
    logger.info(f"Initializing ML Agent: {model_class}")
    # In a real implementation, this would import the class and instantiate it
    # For now, we'll use a mock agent that mimics a model's behavior
    class MockMLAgent:
        def __init__(self, name):
            self.name = name
        def predict(self, observations):
            # Deterministic pseudo-random based on observations sum
            import math
            seed = sum(observations)
            return [math.sin(seed + i) for i in range(4)]
    
    agent = MockMLAgent(model_class)
    ml_agents[model_class] = agent
    return agent

def predict_ml_action(model_name: str, observations: List[float]) -> List[float]:
    """Internal helper called by C++ ML Bridge."""
    if model_name in ml_agents:
        return ml_agents[model_name].predict(observations)
    return [0.0] * 4

def save_ml_model(model_name: str, path: str) -> bool:
    """Internal helper called by C++ ML Bridge."""
    logger.info(f"Saving ML model {model_name} to {path}")
    return True

def load_ml_model(model_name: str, path: str) -> bool:
    """Internal helper called by C++ ML Bridge."""
    logger.info(f"Loading ML model {model_name} from {path}")
    return True

@mcp.tool()
def init_ml_model(model_path: str, model_class: str) -> Dict[str, Any]:
    """
    Initialize an ML model for AI agents.
    
    Args:
        model_path: Path to the model file (.py or checkpoint)
        model_class: Name of the Python class to instantiate
    """
    initialize_ml_agent(model_class, model_path)
    return {"success": True, "message": f"ML Model {model_class} initialized in Python"}

# ============================================================================
# MCP RESOURCES
# ============================================================================

@mcp.resource("blueprint://{blueprint_name}")
def blueprint_resource(blueprint_name: str) -> str:
    """Get Blueprint as a resource for AI context."""
    unreal = get_unreal_connection()
    return get_blueprint_resource(unreal, blueprint_name)

@mcp.resource("level://current/actors")
def level_actors_resource() -> str:
    """Get all actors in the current level as a resource."""
    unreal = get_unreal_connection()
    return get_level_actors_resource(unreal)

@mcp.resource("project://assets/{asset_type}")
def project_assets_resource(asset_type: str) -> str:
    """Get project assets by type as a resource."""
    unreal = get_unreal_connection()
    return get_project_assets_resource(unreal, asset_type)


# Run the server
if __name__ == "__main__":
    logger.info("Starting Unreal MCP Advanced Server...")
    logger.info("Server includes:")
    logger.info("  - Blueprint Visual Scripting Tools")
    logger.info("  - World Building & Architecture Tools")
    logger.info("  - Code Execution (Sandboxed Python)")
    logger.info("  - Actor Management Tools")

    mcp.run(transport='stdio') 
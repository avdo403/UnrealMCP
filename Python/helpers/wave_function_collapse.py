"""
Wave Function Collapse (WFC) Algorithm for Procedural Generation
Generates dungeons, mazes, and other grid-based structures
"""

import logging
import random
from typing import Dict, Any, List, Optional, Set, Tuple
from collections import deque

logger = logging.getLogger(__name__)


class WFCTile:
    """Represents a tile in the WFC algorithm"""
    
    def __init__(self, tile_id: str, mesh_path: str, sockets: Dict[str, str]):
        """
        Initialize a tile
        
        Args:
            tile_id: Unique identifier for this tile type
            mesh_path: Path to the Unreal mesh asset
            sockets: Dictionary mapping direction to socket type
                    e.g., {"north": "wall", "south": "wall", "east": "door", "west": "wall"}
        """
        self.tile_id = tile_id
        self.mesh_path = mesh_path
        self.sockets = sockets
    
    def can_connect(self, other: 'WFCTile', direction: str) -> bool:
        """Check if this tile can connect to another in a given direction"""
        opposite = {
            "north": "south",
            "south": "north",
            "east": "west",
            "west": "east"
        }
        
        my_socket = self.sockets.get(direction)
        other_socket = other.sockets.get(opposite.get(direction))
        
        return my_socket == other_socket


class WFCGenerator:
    """Wave Function Collapse generator for grid-based structures"""
    
    def __init__(self, width: int, height: int, tile_set: List[WFCTile]):
        """
        Initialize WFC generator
        
        Args:
            width: Grid width
            height: Grid height
            tile_set: List of available tiles
        """
        self.width = width
        self.height = height
        self.tile_set = tile_set
        self.grid = [[None for _ in range(width)] for _ in range(height)]
        self.possibilities = [[set(range(len(tile_set))) for _ in range(width)] 
                             for _ in range(height)]
    
    def generate(self) -> List[List[Optional[WFCTile]]]:
        """
        Generate a grid using WFC algorithm
        
        Returns:
            2D grid of tiles
        """
        while not self._is_complete():
            # Find cell with minimum entropy (fewest possibilities)
            min_cell = self._find_min_entropy_cell()
            if min_cell is None:
                break
            
            y, x = min_cell
            
            # Collapse the cell (choose a random tile from possibilities)
            if self.possibilities[y][x]:
                tile_idx = random.choice(list(self.possibilities[y][x]))
                self.grid[y][x] = self.tile_set[tile_idx]
                self.possibilities[y][x] = {tile_idx}
                
                # Propagate constraints
                self._propagate(x, y)
            else:
                # No valid tiles - backtrack or restart
                logger.warning(f"No valid tiles for cell ({x}, {y}) - restarting")
                return self.generate()  # Simple restart strategy
        
        return self.grid
    
    def _is_complete(self) -> bool:
        """Check if all cells have been collapsed"""
        for row in self.grid:
            for cell in row:
                if cell is None:
                    return False
        return True
    
    def _find_min_entropy_cell(self) -> Optional[Tuple[int, int]]:
        """Find the cell with minimum entropy (fewest possibilities)"""
        min_entropy = float('inf')
        min_cell = None
        
        for y in range(self.height):
            for x in range(self.width):
                if self.grid[y][x] is None:
                    entropy = len(self.possibilities[y][x])
                    if entropy > 0 and entropy < min_entropy:
                        min_entropy = entropy
                        min_cell = (y, x)
        
        return min_cell
    
    def _propagate(self, x: int, y: int):
        """Propagate constraints from a collapsed cell"""
        queue = deque([(x, y)])
        
        while queue:
            cx, cy = queue.popleft()
            
            # Check all neighbors
            neighbors = [
                (cx, cy - 1, "north"),
                (cx, cy + 1, "south"),
                (cx + 1, cy, "east"),
                (cx - 1, cy, "west")
            ]
            
            for nx, ny, direction in neighbors:
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    if self.grid[ny][nx] is None:
                        # Update possibilities for neighbor
                        old_possibilities = self.possibilities[ny][nx].copy()
                        new_possibilities = set()
                        
                        for tile_idx in self.possibilities[ny][nx]:
                            neighbor_tile = self.tile_set[tile_idx]
                            
                            # Check if this tile can connect to any collapsed neighbor
                            can_place = True
                            if self.grid[cy][cx] is not None:
                                current_tile = self.grid[cy][cx]
                                if not current_tile.can_connect(neighbor_tile, direction):
                                    can_place = False
                            
                            if can_place:
                                new_possibilities.add(tile_idx)
                        
                        self.possibilities[ny][nx] = new_possibilities
                        
                        # If possibilities changed, add to queue
                        if new_possibilities != old_possibilities:
                            queue.append((nx, ny))


def create_dungeon_tileset() -> List[WFCTile]:
    """
    Create a basic dungeon tileset
    
    Returns:
        List of WFC tiles for dungeon generation
    """
    tiles = [
        # Floor tiles
        WFCTile("floor", "/Engine/BasicShapes/Cube", {
            "north": "open", "south": "open", "east": "open", "west": "open"
        }),
        
        # Wall tiles
        WFCTile("wall_north", "/Engine/BasicShapes/Cube", {
            "north": "wall", "south": "open", "east": "open", "west": "open"
        }),
        WFCTile("wall_south", "/Engine/BasicShapes/Cube", {
            "north": "open", "south": "wall", "east": "open", "west": "open"
        }),
        WFCTile("wall_east", "/Engine/BasicShapes/Cube", {
            "north": "open", "south": "open", "east": "wall", "west": "open"
        }),
        WFCTile("wall_west", "/Engine/BasicShapes/Cube", {
            "north": "open", "south": "open", "east": "open", "west": "wall"
        }),
        
        # Corner tiles
        WFCTile("corner_ne", "/Engine/BasicShapes/Cube", {
            "north": "wall", "south": "open", "east": "wall", "west": "open"
        }),
        WFCTile("corner_nw", "/Engine/BasicShapes/Cube", {
            "north": "wall", "south": "open", "east": "open", "west": "wall"
        }),
        WFCTile("corner_se", "/Engine/BasicShapes/Cube", {
            "north": "open", "south": "wall", "east": "wall", "west": "open"
        }),
        WFCTile("corner_sw", "/Engine/BasicShapes/Cube", {
            "north": "open", "south": "wall", "east": "open", "west": "wall"
        }),
        
        # Corridor tiles
        WFCTile("corridor_ns", "/Engine/BasicShapes/Cube", {
            "north": "open", "south": "open", "east": "wall", "west": "wall"
        }),
        WFCTile("corridor_ew", "/Engine/BasicShapes/Cube", {
            "north": "wall", "south": "wall", "east": "open", "west": "open"
        }),
    ]
    
    return tiles


def generate_dungeon_wfc(
    width: int,
    height: int,
    tile_size: float = 400.0,
    location_x: float = 0,
    location_y: float = 0,
    location_z: float = 0
) -> Dict[str, Any]:
    """
    Generate a dungeon using Wave Function Collapse
    
    Args:
        width: Dungeon width in tiles
        height: Dungeon height in tiles
        tile_size: Size of each tile in Unreal units
        location_x: Starting X location
        location_y: Starting Y location
        location_z: Starting Z location
        
    Returns:
        Dictionary with generation result and actor list
    """
    try:
        # Create tileset
        tileset = create_dungeon_tileset()
        
        # Generate grid
        generator = WFCGenerator(width, height, tileset)
        grid = generator.generate()
        
        # Convert grid to Unreal actors
        actors = []
        
        for y in range(height):
            for x in range(width):
                tile = grid[y][x]
                if tile:
                    actor_x = location_x + x * tile_size
                    actor_y = location_y + y * tile_size
                    
                    actors.append({
                        "tile_id": tile.tile_id,
                        "mesh_path": tile.mesh_path,
                        "location": [actor_x, actor_y, location_z],
                        "grid_position": [x, y]
                    })
        
        return {
            "success": True,
            "width": width,
            "height": height,
            "tile_count": len(actors),
            "actors": actors
        }
        
    except Exception as e:
        logger.error(f"generate_dungeon_wfc error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def spawn_wfc_dungeon(unreal_connection, dungeon_data: Dict[str, Any], 
                     name_prefix: str = "WFC_Dungeon") -> Dict[str, Any]:
    """
    Spawn a WFC-generated dungeon in Unreal Engine
    
    Args:
        unreal_connection: Unreal connection instance
        dungeon_data: Data from generate_dungeon_wfc
        name_prefix: Prefix for actor names
        
    Returns:
        Dictionary with spawn result
    """
    if not dungeon_data.get("success"):
        return dungeon_data
    
    try:
        spawned_actors = []
        
        for i, actor_data in enumerate(dungeon_data["actors"]):
            actor_name = f"{name_prefix}_{actor_data['tile_id']}_{i}"
            
            result = unreal_connection.send_command("spawn_actor", {
                "name": actor_name,
                "type": "StaticMeshActor",
                "location": actor_data["location"],
                "static_mesh": actor_data["mesh_path"]
            })
            
            if result and result.get("status") == "success":
                spawned_actors.append(actor_name)
        
        return {
            "success": True,
            "spawned_count": len(spawned_actors),
            "actors": spawned_actors
        }
        
    except Exception as e:
        logger.error(f"spawn_wfc_dungeon error: {e}")
        return {
            "success": False,
            "error": str(e)
        }

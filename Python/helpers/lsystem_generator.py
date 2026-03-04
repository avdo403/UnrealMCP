"""
L-System Generator for Procedural Vegetation
Generates trees, plants, and other organic structures using L-Systems
"""

import logging
import math
import random
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger(__name__)


class LSystemRule:
    """Represents an L-System production rule"""
    
    def __init__(self, predecessor: str, successor: str, probability: float = 1.0):
        """
        Initialize an L-System rule
        
        Args:
            predecessor: Symbol to replace
            successor: Replacement string
            probability: Probability of applying this rule (for stochastic L-Systems)
        """
        self.predecessor = predecessor
        self.successor = successor
        self.probability = probability


class LSystem:
    """L-System generator"""
    
    def __init__(self, axiom: str, rules: List[LSystemRule], angle: float = 25.0):
        """
        Initialize L-System
        
        Args:
            axiom: Starting string
            rules: List of production rules
            angle: Rotation angle in degrees
        """
        self.axiom = axiom
        self.rules = {rule.predecessor: rule for rule in rules}
        self.angle = angle
    
    def generate(self, iterations: int) -> str:
        """
        Generate L-System string
        
        Args:
            iterations: Number of iterations to apply
            
        Returns:
            Generated string
        """
        current = self.axiom
        
        for _ in range(iterations):
            next_string = ""
            for char in current:
                if char in self.rules:
                    rule = self.rules[char]
                    if random.random() < rule.probability:
                        next_string += rule.successor
                    else:
                        next_string += char
                else:
                    next_string += char
            current = next_string
        
        return current
    
    def interpret_to_3d(self, lstring: str, 
                       segment_length: float = 100.0,
                       start_pos: Tuple[float, float, float] = (0, 0, 0)) -> List[Dict[str, Any]]:
        """
        Interpret L-System string to 3D geometry
        
        Symbols:
        - F: Move forward and draw
        - f: Move forward without drawing
        - +: Turn right
        - -: Turn left
        - &: Pitch down
        - ^: Pitch up
        - \\: Roll left
        - /: Roll right
        - [: Push state
        - ]: Pop state
        
        Args:
            lstring: L-System string to interpret
            segment_length: Length of each segment
            start_pos: Starting position (x, y, z)
            
        Returns:
            List of segments with positions and rotations
        """
        segments = []
        stack = []
        
        # Current state: position, heading, up vector
        pos = list(start_pos)
        heading = [0, 0, 1]  # Forward direction
        left = [-1, 0, 0]    # Left direction
        up = [0, 1, 0]       # Up direction
        
        for char in lstring:
            if char == 'F':
                # Move forward and draw
                new_pos = [
                    pos[0] + heading[0] * segment_length,
                    pos[1] + heading[1] * segment_length,
                    pos[2] + heading[2] * segment_length
                ]
                
                segments.append({
                    "start": pos.copy(),
                    "end": new_pos.copy(),
                    "type": "branch"
                })
                
                pos = new_pos
            
            elif char == 'f':
                # Move forward without drawing
                pos = [
                    pos[0] + heading[0] * segment_length,
                    pos[1] + heading[1] * segment_length,
                    pos[2] + heading[2] * segment_length
                ]
            
            elif char == '+':
                # Turn right (rotate around up vector)
                heading, left = self._rotate_vectors(heading, left, up, -self.angle)
            
            elif char == '-':
                # Turn left (rotate around up vector)
                heading, left = self._rotate_vectors(heading, left, up, self.angle)
            
            elif char == '&':
                # Pitch down (rotate around left vector)
                heading, up = self._rotate_vectors(heading, up, left, -self.angle)
            
            elif char == '^':
                # Pitch up (rotate around left vector)
                heading, up = self._rotate_vectors(heading, up, left, self.angle)
            
            elif char == '\\':
                # Roll left (rotate around heading vector)
                left, up = self._rotate_vectors(left, up, heading, -self.angle)
            
            elif char == '/':
                # Roll right (rotate around heading vector)
                left, up = self._rotate_vectors(left, up, heading, self.angle)
            
            elif char == '[':
                # Push state
                stack.append({
                    "pos": pos.copy(),
                    "heading": heading.copy(),
                    "left": left.copy(),
                    "up": up.copy()
                })
            
            elif char == ']':
                # Pop state
                if stack:
                    state = stack.pop()
                    pos = state["pos"]
                    heading = state["heading"]
                    left = state["left"]
                    up = state["up"]
        
        return segments
    
    def _rotate_vectors(self, v1: List[float], v2: List[float], 
                       axis: List[float], angle_deg: float) -> Tuple[List[float], List[float]]:
        """Rotate two vectors around an axis"""
        angle_rad = math.radians(angle_deg)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        
        # Rodrigues' rotation formula
        def rotate(v):
            return [
                v[0] * cos_a + (axis[1] * v[2] - axis[2] * v[1]) * sin_a + axis[0] * (axis[0] * v[0] + axis[1] * v[1] + axis[2] * v[2]) * (1 - cos_a),
                v[1] * cos_a + (axis[2] * v[0] - axis[0] * v[2]) * sin_a + axis[1] * (axis[0] * v[0] + axis[1] * v[1] + axis[2] * v[2]) * (1 - cos_a),
                v[2] * cos_a + (axis[0] * v[1] - axis[1] * v[0]) * sin_a + axis[2] * (axis[0] * v[0] + axis[1] * v[1] + axis[2] * v[2]) * (1 - cos_a)
            ]
        
        return rotate(v1), rotate(v2)


def create_tree_lsystem(tree_type: str = "basic") -> LSystem:
    """
    Create an L-System for tree generation
    
    Args:
        tree_type: Type of tree (basic, bushy, pine, etc.)
        
    Returns:
        LSystem instance
    """
    if tree_type == "basic":
        # Simple binary tree
        return LSystem(
            axiom="F",
            rules=[
                LSystemRule("F", "F[+F]F[-F]F")
            ],
            angle=25.7
        )
    
    elif tree_type == "bushy":
        # Bushy tree with more branches
        return LSystem(
            axiom="F",
            rules=[
                LSystemRule("F", "FF+[+F-F-F]-[-F+F+F]")
            ],
            angle=22.5
        )
    
    elif tree_type == "pine":
        # Pine tree shape
        return LSystem(
            axiom="F",
            rules=[
                LSystemRule("F", "F[+F][−F]F")
            ],
            angle=35.0
        )
    
    else:
        # Default to basic
        return create_tree_lsystem("basic")


def generate_tree_lsystem(
    tree_type: str = "basic",
    iterations: int = 4,
    segment_length: float = 100.0,
    location_x: float = 0,
    location_y: float = 0,
    location_z: float = 0
) -> Dict[str, Any]:
    """
    Generate a tree using L-Systems
    
    Args:
        tree_type: Type of tree
        iterations: Number of L-System iterations
        segment_length: Length of each branch segment
        location_x: Tree location X
        location_y: Tree location Y
        location_z: Tree location Z
        
    Returns:
        Dictionary with tree data
    """
    try:
        # Create L-System
        lsystem = create_tree_lsystem(tree_type)
        
        # Generate string
        lstring = lsystem.generate(iterations)
        
        # Interpret to 3D
        segments = lsystem.interpret_to_3d(
            lstring,
            segment_length,
            (location_x, location_y, location_z)
        )
        
        return {
            "success": True,
            "tree_type": tree_type,
            "iterations": iterations,
            "segment_count": len(segments),
            "segments": segments,
            "lstring": lstring[:100] + "..." if len(lstring) > 100 else lstring
        }
        
    except Exception as e:
        logger.error(f"generate_tree_lsystem error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def spawn_lsystem_tree(unreal_connection, tree_data: Dict[str, Any],
                      name_prefix: str = "LSystem_Tree") -> Dict[str, Any]:
    """
    Spawn an L-System tree in Unreal Engine
    
    Args:
        unreal_connection: Unreal connection instance
        tree_data: Data from generate_tree_lsystem
        name_prefix: Prefix for actor names
        
    Returns:
        Dictionary with spawn result
    """
    if not tree_data.get("success"):
        return tree_data
    
    try:
        spawned_actors = []
        
        for i, segment in enumerate(tree_data["segments"]):
            # Create a cylinder for each branch segment
            start = segment["start"]
            end = segment["end"]
            
            # Calculate midpoint and length
            mid_x = (start[0] + end[0]) / 2
            mid_y = (start[1] + end[1]) / 2
            mid_z = (start[2] + end[2]) / 2
            
            length = math.sqrt(
                (end[0] - start[0])**2 +
                (end[1] - start[1])**2 +
                (end[2] - start[2])**2
            )
            
            # Calculate rotation
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            dz = end[2] - start[2]
            
            pitch = math.degrees(math.atan2(dz, math.sqrt(dx**2 + dy**2)))
            yaw = math.degrees(math.atan2(dy, dx))
            
            actor_name = f"{name_prefix}_Branch_{i}"
            
            result = unreal_connection.send_command("spawn_actor", {
                "name": actor_name,
                "type": "StaticMeshActor",
                "location": [mid_x, mid_y, mid_z],
                "rotation": [pitch, yaw, 0],
                "scale": [0.1, 0.1, length / 100.0],
                "static_mesh": "/Engine/BasicShapes/Cylinder"
            })
            
            if result and result.get("status") == "success":
                spawned_actors.append(actor_name)
        
        return {
            "success": True,
            "spawned_count": len(spawned_actors),
            "actors": spawned_actors
        }
        
    except Exception as e:
        logger.error(f"spawn_lsystem_tree error: {e}")
        return {
            "success": False,
            "error": str(e)
        }

"""
MCP Resources Module
Provides context resources for AI agents including blueprints, levels, and assets
"""

import logging
import json
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


def get_blueprint_resource(unreal_connection, blueprint_name: str) -> str:
    """
    Get Blueprint as a resource (JSON format)
    
    Returns complete Blueprint structure including:
    - Nodes and connections
    - Variables with types and defaults
    - Functions with parameters
    - Components hierarchy
    
    Args:
        unreal_connection: Unreal connection instance
        blueprint_name: Name of the Blueprint
        
    Returns:
        JSON string with Blueprint data
    """
    try:
        # Get Blueprint content
        response = unreal_connection.send_command("read_blueprint_content", {
            "blueprint_path": blueprint_name,
            "include_event_graph": True,
            "include_functions": True,
            "include_variables": True,
            "include_components": True
        })
        
        is_ok = response and (response.get("status") == "success" or response.get("success") is True)
        if not is_ok:
            return json.dumps({
                "error": "Failed to read Blueprint",
                "blueprint_name": blueprint_name
            }, indent=2)
        
        # Format as resource
        resource_data = {
            "resource_type": "blueprint",
            "blueprint_name": blueprint_name,
            "variables": response.get("variables", []),
            "functions": response.get("functions", []),
            "event_graph": response.get("event_graph", {}),
            "components": response.get("components", []),
            "metadata": {
                "parent_class": response.get("parent_class"),
                "interfaces": response.get("interfaces", [])
            }
        }
        
        return json.dumps(resource_data, indent=2)
        
    except Exception as e:
        logger.error(f"get_blueprint_resource error: {e}")
        return json.dumps({
            "error": str(e),
            "blueprint_name": blueprint_name
        }, indent=2)


def get_level_actors_resource(unreal_connection) -> str:
    """
    Get all actors in the current level as a resource
    
    Returns:
        JSON string with actor list
    """
    try:
        response = unreal_connection.send_command("get_actors_in_level", {})
        
        is_ok = response and (response.get("status") == "success" or response.get("success") is True)
        if not is_ok:
            return json.dumps({
                "error": "Failed to get actors"
            }, indent=2)
        
        resource_data = {
            "resource_type": "level_actors",
            "actors": response.get("actors", []),
            "count": len(response.get("actors", []))
        }
        
        return json.dumps(resource_data, indent=2)
        
    except Exception as e:
        logger.error(f"get_level_actors_resource error: {e}")
        return json.dumps({
            "error": str(e)
        }, indent=2)


def get_project_assets_resource(unreal_connection, asset_type: str) -> str:
    """
    Get project assets by type as a resource
    
    Args:
        unreal_connection: Unreal connection instance
        asset_type: Type of asset (StaticMesh, Material, Texture, Blueprint, etc.)
        
    Returns:
        JSON string with asset list
    """
    try:
        # Note: This requires implementing get_project_assets command in Unreal
        response = unreal_connection.send_command("get_project_assets", {
            "asset_type": asset_type
        })
        
        is_ok = response and (response.get("status") == "success" or response.get("success") is True)
        if not is_ok:
            return json.dumps({
                "error": "Failed to get assets",
                "asset_type": asset_type
            }, indent=2)
        
        resource_data = {
            "resource_type": "project_assets",
            "asset_type": asset_type,
            "assets": response.get("assets", []),
            "count": len(response.get("assets", []))
        }
        
        return json.dumps(resource_data, indent=2)
        
    except Exception as e:
        logger.error(f"get_project_assets_resource error: {e}")
        return json.dumps({
            "error": str(e),
            "asset_type": asset_type
        }, indent=2)


def get_blueprint_graph_visualization(unreal_connection, blueprint_name: str, 
                                     graph_name: str = "EventGraph") -> str:
    """
    Get Blueprint graph as Mermaid diagram for visualization
    
    Args:
        unreal_connection: Unreal connection instance
        blueprint_name: Name of the Blueprint
        graph_name: Name of the graph (EventGraph, function name, etc.)
        
    Returns:
        Mermaid diagram string
    """
    try:
        # Get graph analysis
        response = unreal_connection.send_command("analyze_blueprint_graph", {
            "blueprint_path": blueprint_name,
            "graph_name": graph_name,
            "include_node_details": True,
            "include_pin_connections": True
        })
        
        is_ok = response and (response.get("status") == "success" or response.get("success") is True)
        if not is_ok:
            return f"```mermaid\ngraph TD\n    Error[\"Failed to analyze graph\"]\n```"
        
        # Extract graph data from wherever the API put it
        result = response.get("result", response)
        graph_data = result.get("graph_data") or result.get("graph") or result

        # Normalize to handle both key formats:
        #   analyze_blueprint_graph: {name, class, ...}
        #   legacy:                  {id, type, ...}
        from helpers.blueprint_analysis import normalize_graph_data
        normalized = normalize_graph_data(graph_data)
        nodes = normalized["nodes"]
        connections = normalized["connections"]
        
        # Generate Mermaid diagram
        lines = ["```mermaid", "graph TD"]
        
        # Add nodes — use safe Mermaid ID (replace spaces and special chars)
        for node in nodes:
            raw_id  = node.get("id", "unknown")
            node_id = raw_id.replace(" ", "_").replace("-", "_")[:40]
            node_type = node.get("type", "Unknown")
            title = node.get("title") or node_type
            label = f"{node_type}: {title}" if title != node_type else node_type
            # Escape double-quotes in labels
            label = label.replace('"', "'")
            lines.append(f'    {node_id}["{label}"]')
        
        # Add connections (deduplicated by normalize_graph_data)
        for conn in connections:
            source = (conn.get("source_node") or "").replace(" ", "_").replace("-", "_")[:40]
            target = (conn.get("target_node") or "").replace(" ", "_").replace("-", "_")[:40]
            pin_name = conn.get("source_pin", "")
            if source and target:
                lines.append(f"    {source} -->|{pin_name}| {target}")
        
        lines.append("```")
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"get_blueprint_graph_visualization error: {e}")
        return f"```mermaid\ngraph TD\n    Error[\"{str(e)}\"]\n```"

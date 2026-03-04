"""
Blueprint Graph Analysis Module
Provides advanced analysis and metrics for Blueprint graphs.

FIX LOG (2026-02-22):
  BUG #1 - Key name mismatch: analyze_blueprint_graph returns nodes with "name" key
            and connections with "from_node"/"to_node" keys, but this module was
            reading "id", "source_node", "target_node" — causing all analyses to fail.
  FIX     - normalize_graph_data() maps all variants to a canonical format before analysis.

  BUG #2 - Duplicate connections: analyze_blueprint_graph returns each connection twice
            (A→B and B→A) causing inflated metrics and false cycle detection.
  FIX     - deduplicate_connections() removes exact bidirectional duplicates.

  BUG #3 - One failing metric crashes the whole analysis.
  FIX     - Every metric is wrapped in try/except with graceful fallback.
"""

import logging
from typing import Dict, Any, List, Optional, Set, Tuple

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False

logger = logging.getLogger(__name__)


# =============================================================================
# DATA NORMALIZATION (fixes key mismatch bug)
# =============================================================================

def normalize_graph_data(graph_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize graph data to a canonical format regardless of which API returned it.

    analyze_blueprint_graph returns:
       nodes:       [{name, class, title, pos_x, pos_y, pins:[...]}, ...]
       connections: [{from_node, from_pin, to_node, to_pin}, ...]

    This function normalizes to:
       nodes:       [{id, type, title, ...}, ...]
       connections: [{source_node, source_pin, target_node, target_pin}, ...]
    """
    raw_nodes = graph_data.get("nodes", [])
    raw_conns = graph_data.get("connections", [])

    normalized_nodes = []
    for node in raw_nodes:
        normalized_nodes.append({
            # Support both "name" (from analyze_blueprint_graph) and "id" (legacy)
            "id":    node.get("name") or node.get("id") or "",
            # Support both "class" (from analyze_blueprint_graph) and "type" (legacy)
            "type":  node.get("class") or node.get("type") or "Unknown",
            "title": node.get("title", ""),
            "pins":  node.get("pins", []),
        })

    normalized_conns = []
    seen = set()
    for conn in raw_conns:
        # Support both key formats
        src  = conn.get("from_node")  or conn.get("source_node")  or ""
        dst  = conn.get("to_node")    or conn.get("target_node")   or ""
        sp   = conn.get("from_pin")   or conn.get("source_pin")    or ""
        tp   = conn.get("to_pin")     or conn.get("target_pin")    or ""

        if not src or not dst:
            continue

        # Deduplicate: skip if we already have the canonical A→B direction.
        # analyze_blueprint_graph returns every connection as BOTH A→B and B→A.
        canonical_key = (min(src, dst), max(src, dst), min(sp, tp), max(sp, tp))
        if canonical_key in seen:
            continue
        seen.add(canonical_key)

        normalized_conns.append({
            "source_node": src,
            "source_pin":  sp,
            "target_node": dst,
            "target_pin":  tp,
        })

    return {
        "nodes":       normalized_nodes,
        "connections": normalized_conns,
    }


# =============================================================================
# MAIN ANALYSIS FUNCTION
# =============================================================================

def analyze_graph_complexity(graph_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze the complexity of a Blueprint graph.
    Accepts the raw output of analyze_blueprint_graph (handles key normalization internally).
    """
    # Normalize data first to fix key mismatches
    data = normalize_graph_data(graph_data)
    nodes       = data["nodes"]
    connections = data["connections"]

    node_count       = len(nodes)
    connection_count = len(connections)

    # -------------------------------------------------------------------------
    # NetworkX metrics (optional — gracefully skipped if not installed)
    # -------------------------------------------------------------------------
    bottlenecks          = []
    connected_components = 1
    max_depth            = 0

    if HAS_NETWORKX:
        try:
            dg = nx.DiGraph()
            ug = nx.Graph()

            for node in nodes:
                node_id = node["id"]
                dg.add_node(node_id, type=node["type"])
                ug.add_node(node_id)

            for conn in connections:
                src = conn["source_node"]
                dst = conn["target_node"]
                if src and dst:
                    dg.add_edge(src, dst)
                    ug.add_edge(src, dst)

            connected_components = nx.number_connected_components(ug) if ug.number_of_nodes() > 0 else 1

            try:
                centrality  = nx.betweenness_centrality(dg)
                bottlenecks = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:5]
            except Exception:
                bottlenecks = []

            try:
                if nx.is_directed_acyclic_graph(dg):
                    max_depth = nx.dag_longest_path_length(dg)
                else:
                    adjacency = {n: list(dg.successors(n)) for n in dg.nodes()}
                    max_depth = _calculate_max_depth(nodes, adjacency)
            except Exception:
                max_depth = 0

        except Exception as e:
            logger.warning(f"NetworkX analysis failed: {e}")

    # -------------------------------------------------------------------------
    # Pure-Python metrics (always run)
    # -------------------------------------------------------------------------
    # Cyclomatic complexity: E - N + 2P
    cyclomatic_complexity = max(0, connection_count - node_count + 2 * connected_components)

    dead_nodes = []
    try:
        dead_nodes = _find_dead_nodes(nodes, connections)
    except Exception as e:
        logger.warning(f"Dead-node detection failed: {e}")

    node_types: Dict[str, int] = {}
    for node in nodes:
        t = node.get("type", "Unknown")
        node_types[t] = node_types.get(t, 0) + 1

    branch_points = sum(
        1 for node in nodes
        if any(kw in node.get("type", "") for kw in ("Branch", "IfThenElse", "Switch", "Select"))
    )

    return {
        "node_count":            node_count,
        "connection_count":      connection_count,
        "cyclomatic_complexity": cyclomatic_complexity,
        "max_depth":             max_depth,
        "branch_points":         branch_points,
        "bottlenecks":           [{"node_id": k, "score": round(v, 3)} for k, v in bottlenecks if v > 0],
        "dead_nodes":            len(dead_nodes),
        "dead_node_ids":         dead_nodes,
        "connected_components":  connected_components,
        "node_type_distribution": node_types,
        "complexity_rating":     _rate_complexity(cyclomatic_complexity, node_count),
    }


# =============================================================================
# ISSUE DETECTION
# =============================================================================

def find_graph_issues(graph_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Find potential issues in a Blueprint graph.
    Accepts raw analyze_blueprint_graph output (handles key normalization).

    Issues detected:
    - Dead code (unreachable nodes)
    - Cycles / infinite loops
    - Missing execution connections
    - Performance warnings (EventTick, large graphs)
    """
    data        = normalize_graph_data(graph_data)
    nodes       = data["nodes"]
    connections = data["connections"]
    issues      = []

    # Dead code
    try:
        dead_nodes = _find_dead_nodes(nodes, connections)
        if dead_nodes:
            issues.append({
                "severity":    "warning",
                "type":        "dead_code",
                "description": f"Found {len(dead_nodes)} unreachable node(s) — possible dead code",
                "node_ids":    dead_nodes,
            })
    except Exception as e:
        logger.warning(f"Dead-node detection error: {e}")

    # Infinite loop detection
    try:
        loops = _detect_cycles(nodes, connections)
        if loops:
            issues.append({
                "severity":    "error",
                "type":        "infinite_loop",
                "description": f"Detected {len(loops)} potential infinite loop(s)",
                "loops":       loops,
            })
    except Exception as e:
        logger.warning(f"Cycle detection error: {e}")

    # Missing execution connections
    try:
        missing_exec = _find_missing_execution_connections(nodes, connections)
        if missing_exec:
            issues.append({
                "severity":    "warning",
                "type":        "missing_connection",
                "description": f"Found {len(missing_exec)} node(s) with missing execution connections",
                "node_ids":    missing_exec,
            })
    except Exception as e:
        logger.warning(f"Missing-connection check error: {e}")

    # Performance warnings
    try:
        perf = _check_performance_issues(nodes, connections)
        issues.extend(perf)
    except Exception as e:
        logger.warning(f"Performance check error: {e}")

    return issues


# =============================================================================
# EXECUTION PATH TRACING
# =============================================================================

def trace_execution_path(graph_data: Dict[str, Any], start_node: str) -> List[List[str]]:
    """
    Trace all possible execution paths from a starting node.
    Accepts raw analyze_blueprint_graph output.
    """
    data        = normalize_graph_data(graph_data)
    connections = data["connections"]

    # Build exec-only adjacency (exec pins carry exec type or named "then"/"execute")
    adjacency: Dict[str, List[str]] = {}
    for conn in connections:
        sp  = conn.get("source_pin", "").lower()
        tp  = conn.get("target_pin", "").lower()
        src = conn["source_node"]
        dst = conn["target_node"]
        if any(kw in sp for kw in ("exec", "then", "else", "execute")):
            adjacency.setdefault(src, []).append(dst)

    paths: List[List[str]] = []

    def dfs(node: str, current_path: List[str], visited: Set[str]):
        if node in visited:
            paths.append(current_path + [f"{node} (cycle)"])
            return
        visited = visited | {node}
        current_path = current_path + [node]
        if node not in adjacency or not adjacency[node]:
            paths.append(current_path)
        else:
            for nxt in adjacency[node]:
                dfs(nxt, current_path, visited)

    dfs(start_node, [], set())
    return paths


# =============================================================================
# PRIVATE HELPERS
# =============================================================================

def _calculate_max_depth(nodes: List[Dict], adjacency: Dict[str, List[str]]) -> int:
    """Calculate maximum depth of the graph (fallback when NetworkX unavailable)."""
    if not nodes:
        return 0

    all_ids   = {n["id"] for n in nodes}
    targeted  = {dst for targets in adjacency.values() for dst in targets}
    roots     = all_ids - targeted or ({nodes[0]["id"]} if nodes else set())
    max_depth = 0

    def dfs(node: str, depth: int, visited: Set[str]):
        nonlocal max_depth
        max_depth = max(max_depth, depth)
        for nxt in adjacency.get(node, []):
            if nxt not in visited:
                dfs(nxt, depth + 1, visited | {nxt})

    for root in roots:
        dfs(root, 0, {root})

    return max_depth


def _find_dead_nodes(nodes: List[Dict], connections: List[Dict]) -> List[str]:
    """Find unreachable nodes (dead code)."""
    if not nodes:
        return []

    adjacency: Dict[str, List[str]] = {}
    for conn in connections:
        src = conn["source_node"]
        dst = conn["target_node"]
        adjacency.setdefault(src, []).append(dst)

    entry_points = [
        n["id"] for n in nodes
        if any(kw in n.get("type", "") for kw in ("K2Node_Event", "Event"))
    ]
    if not entry_points:
        entry_points = [nodes[0]["id"]]

    reachable: Set[str] = set()
    queue = list(entry_points)
    while queue:
        node = queue.pop(0)
        if node in reachable:
            continue
        reachable.add(node)
        queue.extend(adjacency.get(node, []))

    all_ids = {n["id"] for n in nodes}
    return [nid for nid in (all_ids - reachable) if nid]


def _detect_cycles(nodes: List[Dict], connections: List[Dict]) -> List[List[str]]:
    """Detect cycles (potential infinite loops)."""
    adjacency: Dict[str, List[str]] = {}
    for conn in connections:
        adjacency.setdefault(conn["source_node"], []).append(conn["target_node"])

    cycles: List[List[str]] = []
    visited:   Set[str] = set()
    rec_stack: Set[str] = set()

    def dfs(node: str, path: List[str]):
        visited.add(node)
        rec_stack.add(node)
        path = path + [node]

        for neighbor in adjacency.get(node, []):
            if neighbor not in visited:
                dfs(neighbor, path)
            elif neighbor in rec_stack:
                cycle_start = path.index(neighbor)
                cycles.append(path[cycle_start:] + [neighbor])

        rec_stack.discard(node)

    for node_id in (n["id"] for n in nodes):
        if node_id not in visited:
            dfs(node_id, [])

    return cycles


def _find_missing_execution_connections(
    nodes: List[Dict], connections: List[Dict]
) -> List[str]:
    """Find nodes that should have execution connections but don't."""
    exec_node_keywords = {"Branch", "IfThenElse", "ForLoop", "WhileLoop", "Sequence", "DoOnce"}

    nodes_with_exec_out: Set[str] = set()
    for conn in connections:
        sp = conn.get("source_pin", "").lower()
        if any(kw in sp for kw in ("then", "else", "exec")):
            nodes_with_exec_out.add(conn["source_node"])

    return [
        n["id"] for n in nodes
        if any(kw in n.get("type", "") for kw in exec_node_keywords)
        and n["id"] not in nodes_with_exec_out
    ]


def _check_performance_issues(
    nodes: List[Dict], connections: List[Dict]
) -> List[Dict[str, Any]]:
    """Check for performance issues."""
    issues = []

    for node in nodes:
        node_type = node.get("type", "")
        if "Tick" in node_type or "ReceiveTick" in node_type:
            issues.append({
                "severity":    "info",
                "type":        "performance",
                "description": "EventTick detected — ensure no expensive operations run every frame",
                "node_id":     node["id"],
            })

    if len(nodes) > 100:
        issues.append({
            "severity":    "warning",
            "type":        "performance",
            "description": f"Graph has {len(nodes)} nodes — consider refactoring into functions",
        })

    return issues


def _rate_complexity(cyclomatic_complexity: int, node_count: int) -> str:
    """Rate the overall complexity level."""
    if cyclomatic_complexity <= 5:
        return "trivial"
    elif cyclomatic_complexity <= 10:
        return "simple"
    elif cyclomatic_complexity <= 20:
        return "moderate"
    elif cyclomatic_complexity <= 50:
        return "complex"
    else:
        return "very_complex"

"""
MCP Machine Learning Module

This module provides ML capabilities for the UnrealMCP plugin.

Components:
- mcp_rl_agent: Reinforcement Learning agent (DQN)
- neural_networks: Neural network architectures
- training_utils: Training utilities and helpers

Example:
    from ml.mcp_rl_agent import MCPRLAgent
    
    agent = MCPRLAgent({'state_size': 10, 'action_size': 4})
    action = agent.act(state)
"""

__version__ = '1.0.0'
__all__ = ['MCPRLAgent']

from .mcp_rl_agent import MCPRLAgent

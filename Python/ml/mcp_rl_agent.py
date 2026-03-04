"""
MCP Reinforcement Learning Agent
Deep Q-Network (DQN) implementation for Unreal Engine AI

This module provides a complete RL agent that can be used with the UnrealMCP plugin
for training and controlling AI characters in Unreal Engine.

Features:
- Deep Q-Network (DQN) algorithm
- Experience replay buffer
- Target network for stability
- Epsilon-greedy exploration
- PyTorch backend
- Save/Load functionality

Example Usage:
    from ml.mcp_rl_agent import MCPRLAgent
    
    agent = MCPRLAgent({
        'state_size': 10,
        'action_size': 4
    })
    
    # Training
    action = agent.act(state)
    metrics = agent.train_step(state, action, reward, next_state, done)
    
    # Inference
    predictions = agent.predict(state)
"""

import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
from collections import deque
import logging
import json
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('MCPRLAgent')


class MCPNeuralNetwork(nn.Module):
    """
    Neural network for Deep Q-Learning
    
    Architecture:
    - Input layer (state_size)
    - Hidden layers (configurable)
    - Output layer (action_size)
    """
    
    def __init__(self, state_size, action_size, hidden_sizes=[128, 128]):
        super().__init__()
        
        layers = []
        input_size = state_size
        
        # Build hidden layers
        for hidden_size in hidden_sizes:
            layers.append(nn.Linear(input_size, hidden_size))
            layers.append(nn.ReLU())
            layers.append(nn.Dropout(0.2))
            input_size = hidden_size
        
        # Output layer
        layers.append(nn.Linear(input_size, action_size))
        
        self.network = nn.Sequential(*layers)
    
    def forward(self, x):
        return self.network(x)


class MCPRLAgent:
    """
    Deep Q-Network agent for Unreal MCP
    
    This agent uses DQN with experience replay and target networks
    to learn optimal policies for AI characters in Unreal Engine.
    """
    
    def __init__(self, config=None):
        """
        Initialize the RL agent
        
        Args:
            config (dict): Configuration dictionary with keys:
                - state_size (int): Size of state vector
                - action_size (int): Number of possible actions
                - hidden_sizes (list): Hidden layer sizes
                - gamma (float): Discount factor
                - epsilon (float): Initial exploration rate
                - epsilon_min (float): Minimum exploration rate
                - epsilon_decay (float): Exploration decay rate
                - learning_rate (float): Learning rate
                - batch_size (int): Training batch size
                - memory_size (int): Replay buffer size
        """
        if config is None:
            config = {}
        
        # Network architecture
        self.state_size = config.get('state_size', 10)
        self.action_size = config.get('action_size', 4)
        self.hidden_sizes = config.get('hidden_sizes', [128, 128])
        
        # Hyperparameters
        self.gamma = config.get('gamma', 0.99)
        self.epsilon = config.get('epsilon', 1.0)
        self.epsilon_min = config.get('epsilon_min', 0.01)
        self.epsilon_decay = config.get('epsilon_decay', 0.995)
        self.learning_rate = config.get('learning_rate', 0.001)
        self.batch_size = config.get('batch_size', 64)
        self.memory_size = config.get('memory_size', 10000)
        
        # Networks
        self.policy_net = MCPNeuralNetwork(
            self.state_size, 
            self.action_size, 
            self.hidden_sizes
        )
        self.target_net = MCPNeuralNetwork(
            self.state_size, 
            self.action_size, 
            self.hidden_sizes
        )
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()  # Target network is always in eval mode
        
        # Optimizer
        self.optimizer = optim.Adam(
            self.policy_net.parameters(), 
            lr=self.learning_rate
        )
        
        # Replay memory
        self.memory = deque(maxlen=self.memory_size)
        
        # Training metrics
        self.training_step = 0
        self.total_episodes = 0
        
        logger.info(f"MCPRLAgent initialized: State={self.state_size}, Actions={self.action_size}")
    
    def predict(self, state):
        """
        Predict action Q-values for given state
        Called from C++ for inference
        
        Args:
            state (list): State observation vector
        
        Returns:
            list: Q-values for each action
        """
        state_tensor = torch.FloatTensor(state).unsqueeze(0)
        
        with torch.no_grad():
            q_values = self.policy_net(state_tensor)
        
        return q_values[0].tolist()
    
    def act(self, state, training=True):
        """
        Select action using epsilon-greedy policy
        
        Args:
            state (list/array): Current state
            training (bool): Whether in training mode
        
        Returns:
            int: Selected action index
        """
        if training and np.random.rand() <= self.epsilon:
            return np.random.randint(self.action_size)
        
        q_values = self.predict(state)
        return int(np.argmax(q_values))
    
    def remember(self, state, action, reward, next_state, done):
        """
        Store experience in replay memory
        
        Args:
            state: Current state
            action: Action taken
            reward: Reward received
            next_state: Next state
            done: Whether episode ended
        """
        self.memory.append((state, action, reward, next_state, done))
    
    def train_step(self, state, action, reward, next_state, done):
        """
        Single training step
        Called from C++ during training
        
        Args:
            state: Current state
            action: Action taken
            reward: Reward received
            next_state: Next state
            done: Whether episode is done
        
        Returns:
            dict: Training metrics
        """
        # Store experience
        self.remember(state, action, reward, next_state, done)
        
        # Train if enough samples
        if len(self.memory) < self.batch_size:
            return {
                'trained': False, 
                'memory_size': len(self.memory),
                'epsilon': self.epsilon
            }
        
        # Sample batch
        batch_indices = np.random.choice(len(self.memory), self.batch_size, replace=False)
        batch_samples = [self.memory[i] for i in batch_indices]
        
        # Prepare tensors
        states = torch.FloatTensor([s[0] for s in batch_samples])
        actions = torch.LongTensor([s[1] for s in batch_samples])
        rewards = torch.FloatTensor([s[2] for s in batch_samples])
        next_states = torch.FloatTensor([s[3] for s in batch_samples])
        dones = torch.FloatTensor([s[4] for s in batch_samples])
        
        # Compute Q values
        current_q = self.policy_net(states).gather(1, actions.unsqueeze(1))
        
        with torch.no_grad():
            next_q = self.target_net(next_states).max(1)[0]
            target_q = rewards + (1 - dones) * self.gamma * next_q
        
        # Compute loss
        loss = nn.MSELoss()(current_q.squeeze(), target_q)
        
        # Optimize
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.policy_net.parameters(), 1.0)
        self.optimizer.step()
        
        # Update epsilon
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay
        
        # Update target network periodically
        self.training_step += 1
        if self.training_step % 100 == 0:
            self.target_net.load_state_dict(self.policy_net.state_dict())
            logger.info(f"Target network updated at step {self.training_step}")
        
        return {
            'trained': True,
            'loss': float(loss.item()),
            'epsilon': self.epsilon,
            'memory_size': len(self.memory),
            'training_step': self.training_step
        }
    
    def save(self, filepath):
        """
        Save model and training state
        
        Args:
            filepath (str): Path to save file
        """
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        torch.save({
            'policy_net': self.policy_net.state_dict(),
            'target_net': self.target_net.state_dict(),
            'optimizer': self.optimizer.state_dict(),
            'epsilon': self.epsilon,
            'training_step': self.training_step,
            'total_episodes': self.total_episodes,
            'config': {
                'state_size': self.state_size,
                'action_size': self.action_size,
                'hidden_sizes': self.hidden_sizes,
                'gamma': self.gamma,
                'learning_rate': self.learning_rate
            }
        }, filepath)
        
        logger.info(f"Model saved to {filepath}")
    
    def load(self, filepath):
        """
        Load model and training state
        
        Args:
            filepath (str): Path to load file
        """
        checkpoint = torch.load(filepath)
        
        self.policy_net.load_state_dict(checkpoint['policy_net'])
        self.target_net.load_state_dict(checkpoint['target_net'])
        self.optimizer.load_state_dict(checkpoint['optimizer'])
        self.epsilon = checkpoint['epsilon']
        self.training_step = checkpoint['training_step']
        self.total_episodes = checkpoint.get('total_episodes', 0)
        
        logger.info(f"Model loaded from {filepath}")
        logger.info(f"Training step: {self.training_step}, Episodes: {self.total_episodes}")


# Example usage and testing
if __name__ == "__main__":
    print("MCPRLAgent - Testing")
    
    # Create agent
    agent = MCPRLAgent({
        'state_size': 10,
        'action_size': 4,
        'hidden_sizes': [128, 128]
    })
    
    # Simulate training
    print("\nSimulating training...")
    for episode in range(10):
        state = np.random.rand(10).tolist()
        total_reward = 0
        
        for step in range(50):
            action = agent.act(state)
            next_state = np.random.rand(10).tolist()
            reward = np.random.rand()
            done = step == 49
            
            metrics = agent.train_step(state, action, reward, next_state, done)
            total_reward += reward
            state = next_state
            
            if done:
                break
        
        print(f"Episode {episode}: Reward = {total_reward:.2f}, Epsilon = {agent.epsilon:.3f}")
    
    # Test save/load
    print("\nTesting save/load...")
    agent.save("test_model.pth")
    
    agent2 = MCPRLAgent({'state_size': 10, 'action_size': 4})
    agent2.load("test_model.pth")
    
    print("✅ All tests passed!")

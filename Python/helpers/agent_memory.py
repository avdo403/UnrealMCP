"""
Agentic Memory Module
Provides persistent storage for AI agent notes, session data, and project context.
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

MEMORY_DIR = ".agent_memory"

class AgentMemory:
    def __init__(self):
        if not os.path.exists(MEMORY_DIR):
            os.makedirs(MEMORY_DIR)
        self.notes_file = os.path.join(MEMORY_DIR, "notes.json")
        self.sessions_file = os.path.join(MEMORY_DIR, "sessions.json")
        
    def save_note(self, title: str, content: str, category: str = "general") -> bool:
        notes = self.load_notes()
        notes.append({
            "title": title,
            "content": content,
            "category": category,
            "timestamp": datetime.now().isoformat()
        })
        try:
            with open(self.notes_file, 'w') as f:
                json.dump(notes, f, indent=4)
            return True
        except Exception as e:
            logger.error(f"Failed to save note: {e}")
            return False
            
    def load_notes(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.notes_file):
            return []
        try:
            with open(self.notes_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []
            
    def search_notes(self, query: str) -> List[Dict[str, Any]]:
        notes = self.load_notes()
        return [n for n in notes if query.lower() in n['title'].lower() or query.lower() in n['content'].lower()]

    def save_session_state(self, session_id: str, state: Dict[str, Any]) -> bool:
        sessions = self.load_sessions()
        sessions[session_id] = {
            "state": state,
            "last_updated": datetime.now().isoformat()
        }
        try:
            with open(self.sessions_file, 'w') as f:
                json.dump(sessions, f, indent=4)
            return True
        except Exception as e:
            logger.error(f"Failed to save session: {e}")
            return False
            
    def load_sessions(self) -> Dict[str, Any]:
        if not os.path.exists(self.sessions_file):
            return {}
        try:
            with open(self.sessions_file, 'r') as f:
                return json.load(f)
        except Exception:
            return {}

# Global instance
_memory = AgentMemory()

def save_note(title: str, content: str, category: str = "general") -> bool:
    return _memory.save_note(title, content, category)

def get_notes() -> List[Dict[str, Any]]:
    return _memory.load_notes()

def search_notes(query: str) -> List[Dict[str, Any]]:
    return _memory.search_notes(query)

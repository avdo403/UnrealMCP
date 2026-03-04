"""
Code Execution Module for Unreal MCP Server
Provides secure sandboxed Python code execution for AI agents
"""

import logging
import json
import uuid
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Session storage
_active_sessions: Dict[str, Dict[str, Any]] = {}
_session_timeout = timedelta(hours=1)


class CodeExecutor:
    """
    Secure code execution using Docker containers
    Supports stateful sessions for iterative code execution
    """
    
    def __init__(self, use_docker: bool = True):
        """
        Initialize code executor
        
        Args:
            use_docker: Whether to use Docker for isolation (recommended)
        """
        self.use_docker = use_docker
        self.docker_client = None
        
        if use_docker:
            try:
                import docker
                self.docker_client = docker.from_env()
                logger.info("Docker client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Docker: {e}")
                logger.warning("Falling back to local execution (UNSAFE)")
                self.use_docker = False
    
    def create_session(self, session_id: Optional[str] = None) -> str:
        """
        Create a new execution session
        
        Args:
            session_id: Optional custom session ID
            
        Returns:
            Session ID
        """
        if session_id is None:
            session_id = str(uuid.uuid4())
        
        _active_sessions[session_id] = {
            "created_at": datetime.now(),
            "last_used": datetime.now(),
            "variables": {},
            "history": []
        }
        
        logger.info(f"Created session: {session_id}")
        return session_id
    
    def execute_code(
        self,
        code: str,
        session_id: Optional[str] = None,
        timeout: int = 30,
        resource_limits: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute Python code in a sandboxed environment
        
        Args:
            code: Python code to execute
            session_id: Optional session ID for stateful execution
            timeout: Execution timeout in seconds
            resource_limits: Optional resource limits (cpu, memory)
            
        Returns:
            Execution result with stdout, stderr, and return value
        """
        # Create session if needed
        if session_id is None:
            session_id = self.create_session()
        elif session_id not in _active_sessions:
            self.create_session(session_id)
        
        # Update last used time
        _active_sessions[session_id]["last_used"] = datetime.now()
        
        # Set default resource limits
        if resource_limits is None:
            resource_limits = {
                "cpu": "1.0",
                "memory": "512Mi"
            }
        
        try:
            if self.use_docker:
                result = self._execute_in_docker(
                    code, session_id, timeout, resource_limits
                )
            else:
                result = self._execute_local(code, session_id, timeout)
            
            # Store in history
            _active_sessions[session_id]["history"].append({
                "code": code,
                "result": result,
                "timestamp": datetime.now().isoformat()
            })
            
            return {
                "success": True,
                "session_id": session_id,
                **result
            }
            
        except Exception as e:
            logger.error(f"Code execution error: {e}")
            return {
                "success": False,
                "session_id": session_id,
                "error": str(e),
                "stdout": "",
                "stderr": str(e)
            }
    
    def _execute_in_docker(
        self,
        code: str,
        session_id: str,
        timeout: int,
        resource_limits: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute code in Docker container"""
        if not self.docker_client:
            raise RuntimeError("Docker client not initialized")
        
        # Create container with resource limits
        container = self.docker_client.containers.run(
            image="python:3.12-slim",
            command=["python", "-c", code],
            detach=True,
            remove=True,
            mem_limit=resource_limits.get("memory", "512m"),
            cpu_quota=int(float(resource_limits.get("cpu", "1.0")) * 100000),
            network_disabled=True,  # No network access
            read_only=True,  # Read-only filesystem
            security_opt=["no-new-privileges"],
            cap_drop=["ALL"]
        )
        
        # Wait for completion
        try:
            exit_code = container.wait(timeout=timeout)
            stdout = container.logs(stdout=True, stderr=False).decode('utf-8')
            stderr = container.logs(stdout=False, stderr=True).decode('utf-8')
            
            return {
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code.get("StatusCode", -1),
                "execution_time": None  # TODO: measure execution time
            }
        except Exception as e:
            container.kill()
            raise RuntimeError(f"Container execution failed: {e}")
    
    def _execute_local(
        self,
        code: str,
        session_id: str,
        timeout: int
    ) -> Dict[str, Any]:
        """
        Execute code locally (UNSAFE - for development only)
        WARNING: This does not provide isolation!
        """
        import io
        import sys
        import contextlib
        
        # Capture stdout/stderr
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        # Get session variables
        session_vars = _active_sessions[session_id].get("variables", {})
        
        try:
            with contextlib.redirect_stdout(stdout_capture), \
                 contextlib.redirect_stderr(stderr_capture):
                
                # Execute code with session variables
                exec(code, session_vars)
            
            # Update session variables
            _active_sessions[session_id]["variables"] = session_vars
            
            return {
                "stdout": stdout_capture.getvalue(),
                "stderr": stderr_capture.getvalue(),
                "exit_code": 0,
                "execution_time": None
            }
            
        except Exception as e:
            return {
                "stdout": stdout_capture.getvalue(),
                "stderr": stderr_capture.getvalue() + f"\n{str(e)}",
                "exit_code": 1,
                "execution_time": None
            }
    
    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a session"""
        session = _active_sessions.get(session_id)
        if not session:
            return None
        
        return {
            "session_id": session_id,
            "created_at": session["created_at"].isoformat(),
            "last_used": session["last_used"].isoformat(),
            "history_count": len(session["history"]),
            "variable_count": len(session.get("variables", {}))
        }
    
    def reset_session(self, session_id: str) -> bool:
        """Reset a session (clear variables and history)"""
        if session_id not in _active_sessions:
            return False
        
        _active_sessions[session_id]["variables"] = {}
        _active_sessions[session_id]["history"] = []
        _active_sessions[session_id]["last_used"] = datetime.now()
        
        logger.info(f"Reset session: {session_id}")
        return True
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session"""
        if session_id in _active_sessions:
            del _active_sessions[session_id]
            logger.info(f"Deleted session: {session_id}")
            return True
        return False
    
    def cleanup_old_sessions(self):
        """Remove sessions that haven't been used recently"""
        now = datetime.now()
        to_delete = []
        
        for session_id, session in _active_sessions.items():
            if now - session["last_used"] > _session_timeout:
                to_delete.append(session_id)
        
        for session_id in to_delete:
            self.delete_session(session_id)
        
        if to_delete:
            logger.info(f"Cleaned up {len(to_delete)} old sessions")


# Global executor instance
_executor: Optional[CodeExecutor] = None


def get_executor() -> CodeExecutor:
    """Get or create the global code executor"""
    global _executor
    if _executor is None:
        _executor = CodeExecutor(use_docker=True)
    return _executor


def execute_python_code(
    code: str,
    session_id: Optional[str] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Execute Python code in a secure sandbox
    
    Args:
        code: Python code to execute
        session_id: Optional session ID for stateful execution
        timeout: Execution timeout in seconds
        
    Returns:
        Execution result
    """
    executor = get_executor()
    return executor.execute_code(code, session_id, timeout)


def create_execution_session() -> str:
    """Create a new execution session"""
    executor = get_executor()
    return executor.create_session()


def reset_execution_session(session_id: str) -> bool:
    """Reset an execution session"""
    executor = get_executor()
    return executor.reset_session(session_id)


def get_session_info(session_id: str) -> Optional[Dict[str, Any]]:
    """Get session information"""
    executor = get_executor()
    return executor.get_session_info(session_id)

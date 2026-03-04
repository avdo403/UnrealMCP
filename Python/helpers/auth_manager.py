"""
Authentication and Authorization for Unreal MCP Server.

Provides OAuth2, JWT, and API key authentication with role-based access control.
"""

import logging
import secrets
import hashlib
import time
from typing import Optional, Dict, Any, List, Set
from dataclasses import dataclass
from enum import Enum
import jwt
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class Permission(Enum):
    """Available permissions."""
    # Blueprint permissions
    CREATE_BLUEPRINT = "create_blueprint"
    MODIFY_BLUEPRINT = "modify_blueprint"
    DELETE_BLUEPRINT = "delete_blueprint"
    READ_BLUEPRINT = "read_blueprint"
    
    # Actor permissions
    SPAWN_ACTOR = "spawn_actor"
    DELETE_ACTOR = "delete_actor"
    MODIFY_ACTOR = "modify_actor"
    
    # Code execution
    EXECUTE_CODE = "execute_code"
    
    # Procedural generation
    GENERATE_CONTENT = "generate_content"
    
    # Admin
    ADMIN = "admin"


class Role(Enum):
    """Predefined roles with permission sets."""
    VIEWER = "viewer"
    DEVELOPER = "developer"
    ADMIN = "admin"
    GUEST = "guest"


# Role to permissions mapping
ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
    Role.GUEST: {
        Permission.READ_BLUEPRINT,
    },
    Role.VIEWER: {
        Permission.READ_BLUEPRINT,
    },
    Role.DEVELOPER: {
        Permission.CREATE_BLUEPRINT,
        Permission.MODIFY_BLUEPRINT,
        Permission.READ_BLUEPRINT,
        Permission.SPAWN_ACTOR,
        Permission.DELETE_ACTOR,
        Permission.MODIFY_ACTOR,
        Permission.EXECUTE_CODE,
        Permission.GENERATE_CONTENT,
    },
    Role.ADMIN: set(Permission),  # All permissions
}


@dataclass
class User:
    """User model."""
    user_id: str
    username: str
    email: Optional[str] = None
    roles: List[Role] = None
    api_key: Optional[str] = None
    created_at: float = None
    
    def __post_init__(self):
        if self.roles is None:
            self.roles = [Role.GUEST]
        if self.created_at is None:
            self.created_at = time.time()
    
    def has_permission(self, permission: Permission) -> bool:
        """Check if user has specific permission."""
        for role in self.roles:
            if permission in ROLE_PERMISSIONS.get(role, set()):
                return True
        return False
    
    def has_role(self, role: Role) -> bool:
        """Check if user has specific role."""
        return role in self.roles
    
    def get_permissions(self) -> Set[Permission]:
        """Get all permissions for user."""
        permissions = set()
        for role in self.roles:
            permissions.update(ROLE_PERMISSIONS.get(role, set()))
        return permissions


class AuthManager:
    """
    Authentication and authorization manager.
    
    Features:
    - JWT token generation and validation
    - API key management
    - Role-based access control
    - Session management
    - Rate limiting
    """
    
    def __init__(
        self,
        secret_key: Optional[str] = None,
        token_expiry: int = 3600,
        algorithm: str = "HS256"
    ):
        self.secret_key = secret_key or secrets.token_urlsafe(32)
        self.token_expiry = token_expiry
        self.algorithm = algorithm
        
        # In-memory user store (replace with database in production)
        self.users: Dict[str, User] = {}
        self.api_keys: Dict[str, str] = {}  # api_key -> user_id
        self.sessions: Dict[str, Dict[str, Any]] = {}
        
        # Rate limiting
        self.rate_limits: Dict[str, List[float]] = {}
    
    def create_user(
        self,
        username: str,
        email: Optional[str] = None,
        roles: Optional[List[Role]] = None
    ) -> User:
        """Create new user."""
        user_id = secrets.token_urlsafe(16)
        
        user = User(
            user_id=user_id,
            username=username,
            email=email,
            roles=roles or [Role.DEVELOPER]
        )
        
        self.users[user_id] = user
        logger.info(f"Created user: {username} ({user_id})")
        
        return user
    
    def generate_api_key(self, user_id: str) -> Optional[str]:
        """Generate API key for user."""
        if user_id not in self.users:
            return None
        
        api_key = f"umcp_{secrets.token_urlsafe(32)}"
        self.api_keys[api_key] = user_id
        self.users[user_id].api_key = api_key
        
        logger.info(f"Generated API key for user {user_id}")
        return api_key
    
    def validate_api_key(self, api_key: str) -> Optional[User]:
        """Validate API key and return user."""
        user_id = self.api_keys.get(api_key)
        if user_id:
            return self.users.get(user_id)
        return None
    
    def create_token(self, user_id: str) -> Optional[str]:
        """Create JWT token for user."""
        user = self.users.get(user_id)
        if not user:
            return None
        
        payload = {
            "user_id": user.user_id,
            "username": user.username,
            "roles": [role.value for role in user.roles],
            "exp": datetime.utcnow() + timedelta(seconds=self.token_expiry),
            "iat": datetime.utcnow()
        }
        
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        logger.info(f"Created token for user {user.username}")
        
        return token
    
    def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate JWT token and return payload."""
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
    
    def get_user_from_token(self, token: str) -> Optional[User]:
        """Get user from JWT token."""
        payload = self.validate_token(token)
        if payload:
            user_id = payload.get("user_id")
            return self.users.get(user_id)
        return None
    
    def check_permission(
        self,
        user: User,
        permission: Permission
    ) -> bool:
        """Check if user has permission."""
        return user.has_permission(permission)
    
    def check_rate_limit(
        self,
        user_id: str,
        max_requests: int = 100,
        window: int = 60
    ) -> bool:
        """
        Check if user is within rate limit.
        
        Args:
            user_id: User ID
            max_requests: Maximum requests per window
            window: Time window in seconds
            
        Returns:
            True if within limit, False otherwise
        """
        now = time.time()
        
        # Initialize if not exists
        if user_id not in self.rate_limits:
            self.rate_limits[user_id] = []
        
        # Remove old requests
        self.rate_limits[user_id] = [
            req_time for req_time in self.rate_limits[user_id]
            if now - req_time < window
        ]
        
        # Check limit
        if len(self.rate_limits[user_id]) >= max_requests:
            logger.warning(f"Rate limit exceeded for user {user_id}")
            return False
        
        # Add current request
        self.rate_limits[user_id].append(now)
        return True
    
    def create_session(self, user_id: str) -> str:
        """Create session for user."""
        session_id = secrets.token_urlsafe(32)
        
        self.sessions[session_id] = {
            "user_id": user_id,
            "created_at": time.time(),
            "last_activity": time.time()
        }
        
        return session_id
    
    def validate_session(self, session_id: str, max_age: int = 3600) -> Optional[str]:
        """Validate session and return user_id."""
        session = self.sessions.get(session_id)
        if not session:
            return None
        
        # Check expiry
        if time.time() - session["last_activity"] > max_age:
            del self.sessions[session_id]
            return None
        
        # Update last activity
        session["last_activity"] = time.time()
        
        return session["user_id"]
    
    def revoke_session(self, session_id: str):
        """Revoke session."""
        self.sessions.pop(session_id, None)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get authentication statistics."""
        return {
            "total_users": len(self.users),
            "active_sessions": len(self.sessions),
            "total_api_keys": len(self.api_keys),
            "roles_distribution": {
                role.value: sum(
                    1 for user in self.users.values()
                    if role in user.roles
                )
                for role in Role
            }
        }


# Global auth manager
_auth_manager: Optional[AuthManager] = None


def get_auth_manager() -> AuthManager:
    """Get global auth manager instance."""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    return _auth_manager


def require_permission(permission: Permission):
    """
    Decorator to require specific permission.
    
    Example:
        @require_permission(Permission.CREATE_BLUEPRINT)
        def create_blueprint(user: User, name: str):
            # Only users with CREATE_BLUEPRINT permission can call this
            pass
    """
    def decorator(func):
        def wrapper(user: User, *args, **kwargs):
            if not user.has_permission(permission):
                raise PermissionError(
                    f"User {user.username} does not have permission {permission.value}"
                )
            return func(user, *args, **kwargs)
        return wrapper
    return decorator


def require_role(role: Role):
    """
    Decorator to require specific role.
    
    Example:
        @require_role(Role.ADMIN)
        def delete_all_blueprints(user: User):
            # Only admins can call this
            pass
    """
    def decorator(func):
        def wrapper(user: User, *args, **kwargs):
            if not user.has_role(role):
                raise PermissionError(
                    f"User {user.username} does not have role {role.value}"
                )
            return func(user, *args, **kwargs)
        return wrapper
    return decorator

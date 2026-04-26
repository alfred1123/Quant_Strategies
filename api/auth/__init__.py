"""Authentication module — login, logout, JWT cookie session, require_user dependency.

See docs/design/login.md.
"""

from api.auth.dependencies import require_user
from api.auth.models import CurrentUser
from api.auth.service import AuthService

__all__ = ["AuthService", "CurrentUser", "require_user"]

"""Authentication module — login, logout, JWT cookie session, require_user dependency.

See docs/design/login.md.
"""

from quant.api.auth.dependencies import require_user
from quant.api.auth.models import CurrentUser
from quant.api.auth.service import AuthService

__all__ = ["AuthService", "CurrentUser", "require_user"]

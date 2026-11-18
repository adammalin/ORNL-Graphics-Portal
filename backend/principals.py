"""Server-side identity snapshots. No browser, MCP or model credentials."""
from dataclasses import dataclass


@dataclass
class Actor:
    """Verified upstream identity retained by the private browser session."""
    user_id: str
    email: str
    name: str
    identities: frozenset
    invite_email: str
    role: str


@dataclass(frozen=True)
class Principal:
    """Immutable authority snapshot, created after runtime session validation.

    This is not an authentication credential. JobService accepts only an opaque
    session handle and resolves it itself; callers cannot supply this as identity.
    Future agent grants require a separate verifier, not a caller-selected role.
    """
    user_id: str
    email: str
    name: str
    identities: frozenset
    role: str
    expires_at: float
    client_id: str = 'portal-browser'
    execution_origin: str = 'browser'

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def can_coordinate(self):
        return self.role in ('admin','coordinator')

    @classmethod
    def from_session(cls, session):
        actor = session.actor
        return cls(actor.user_id, actor.email, actor.name,
                   frozenset(actor.identities), actor.role, session.expires)

    def public_identity(self):
        return {'id': self.email, 'name': self.name, 'role': self.role}

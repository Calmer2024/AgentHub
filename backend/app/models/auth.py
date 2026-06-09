from sqlalchemy import Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from ..core.timezone import china_now
from ..database import Base


def _utcnow():
    return china_now()


class AuthIdentity(Base):
    __tablename__ = "auth_identities"
    __table_args__ = (UniqueConstraint("provider", "subject", name="uq_auth_identity_provider_subject"),)

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    provider = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    email = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    last_login_at = Column(DateTime, nullable=True)

    user = relationship("User")


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    refresh_token_hash = Column(Text, nullable=False)
    user_agent = Column(Text, nullable=True)
    ip_hash = Column(Text, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    user = relationship("User")

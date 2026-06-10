from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.orm import relationship

from ..core.timezone import china_now
from ..database import Base


def _utcnow():
    return china_now()


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String, nullable=False, unique=True)
    username = Column(String, nullable=True, unique=True)
    display_name = Column(String, nullable=False)
    avatar_url = Column(Text, nullable=True)
    password_hash = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="active")
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    memberships = relationship("TeamMember", back_populates="user")

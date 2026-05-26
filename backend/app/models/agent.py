from sqlalchemy import Column, String, Boolean

from ..database import Base


class Agent(Base):
    __tablename__ = "agents"

    name = Column(String, primary_key=True)
    display_name = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)

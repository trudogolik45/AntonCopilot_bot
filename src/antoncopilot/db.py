from sqlalchemy import BigInteger, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_connection_id: Mapped[str] = mapped_column(String(64))
    owner_id: Mapped[int] = mapped_column(BigInteger)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")


class ChatMessage(Base):
    """Сообщение из истории чата Владельца с Собеседником."""

    __tablename__ = "chat_messages"
    __table_args__ = (UniqueConstraint("owner_id", "chat_id", "message_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(BigInteger)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)
    from_owner: Mapped[bool]
    text: Mapped[str] = mapped_column(Text)

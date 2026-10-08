import os
from collections.abc import AsyncGenerator, AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import GetBusinessConnection, SendMessage, TelegramMethod
from aiogram.types import BusinessConnection, Chat, Message, User
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from antoncopilot.db import Base

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://antoncopilot:antoncopilot@127.0.0.1:5433/antoncopilot",
)

OWNER = User(id=100, is_bot=False, first_name="Антон")
OWNER_BOT_CHAT_ID = 100
STRANGER = User(id=300, is_bot=False, first_name="Чужой")
INTERLOCUTOR = User(id=200, is_bot=False, first_name="Иван")
CONNECTION_ID = "conn-1"


class FakeSession(BaseSession):
    """Подменяет Telegram Bot API: запоминает вызовы и отвечает правдоподобно."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []
        self._message_id = 1000

    async def make_request(
        self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None
    ) -> Any:
        self.calls.append(method)
        if isinstance(method, GetBusinessConnection):
            return BusinessConnection(
                id=method.business_connection_id,
                user=OWNER,
                user_chat_id=OWNER_BOT_CHAT_ID,
                date=datetime.now(UTC),
                is_enabled=True,
            )
        if isinstance(method, SendMessage):
            self._message_id += 1
            return Message(
                message_id=self._message_id,
                date=datetime.now(UTC),
                chat=Chat(id=int(method.chat_id), type="private"),
                text=method.text,
            )
        return True

    def sent(self) -> list[SendMessage]:
        return [c for c in self.calls if isinstance(c, SendMessage)]

    async def close(self) -> None:
        pass

    async def stream_content(self, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes, None]:
        yield b""


class FakeWriter:
    def __init__(self, reply: str = "Здравствуйте! Пришлите детали — посчитаю.") -> None:
        self.reply = reply
        self.incoming: list[str] = []

    async def write(self, incoming: str) -> str:
        self.incoming.append(incoming)
        return self.reply


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(TEST_DATABASE_URL)
    yield engine
    await engine.dispose()


@pytest.fixture
async def sessionmaker(engine: AsyncEngine) -> async_sessionmaker[Any]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def session() -> FakeSession:
    return FakeSession()


@pytest.fixture
def bot(session: FakeSession) -> Bot:
    return Bot(token="42:TEST", session=session)


@pytest.fixture
def writer() -> FakeWriter:
    return FakeWriter()

import logging
from typing import Protocol

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    BusinessConnection,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from antoncopilot.db import Draft

log = logging.getLogger(__name__)

SEND_PREFIX = "send:"


class DraftWriter(Protocol):
    async def write(self, incoming: str) -> str: ...


def send_keyboard(draft: Draft) -> InlineKeyboardMarkup:
    button = InlineKeyboardButton(text="Отправить", callback_data=f"{SEND_PREFIX}{draft.id}")
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


def render_draft(message: Message, incoming: str, draft: Draft) -> str:
    name = message.from_user.full_name if message.from_user else "Без имени"
    return f"{name}: {incoming}\n\nЧерновик:\n{draft.text}"


def is_from_owner(message: Message, connection: BusinessConnection) -> bool:
    return message.from_user is not None and message.from_user.id == connection.user.id


def build_dispatcher(
    sessionmaker: async_sessionmaker[AsyncSession], writer: DraftWriter
) -> Dispatcher:
    router = Router()

    async def save(draft: Draft) -> Draft:
        async with sessionmaker() as db, db.begin():
            db.add(draft)
        return draft

    async def take_for_sending(draft_id: int, presser_id: int) -> Draft | None:
        """Переводит Черновик в «отправлен» ровно один раз; повторное нажатие получит None."""
        async with sessionmaker() as db, db.begin():
            return await db.scalar(
                update(Draft)
                .where(Draft.id == draft_id, Draft.owner_id == presser_id)
                .where(Draft.status == "pending")
                .values(status="sent")
                .returning(Draft)
            )

    @router.business_message(F.business_connection_id, F.text | (F.photo & F.caption))
    async def on_incoming(message: Message, bot: Bot) -> None:
        connection = await bot.get_business_connection(message.business_connection_id or "")
        if is_from_owner(message, connection):
            log.info("owner_outgoing_seen", extra={"chat_id": message.chat.id})
            return
        incoming = message.text or message.caption or ""
        draft = await save(
            Draft(
                business_connection_id=connection.id,
                owner_id=connection.user.id,
                chat_id=message.chat.id,
                text=await writer.write(incoming),
            )
        )
        await bot.send_message(
            connection.user_chat_id,
            render_draft(message, incoming, draft),
            reply_markup=send_keyboard(draft),
        )

    @router.callback_query(F.data.regexp(rf"^{SEND_PREFIX}\d+$"))
    async def on_send(callback: CallbackQuery, bot: Bot) -> None:
        await callback.answer()
        draft_id = int((callback.data or "").removeprefix(SEND_PREFIX))
        draft = await take_for_sending(draft_id, callback.from_user.id)
        if draft is None:
            return
        await bot.send_message(
            draft.chat_id, draft.text, business_connection_id=draft.business_connection_id
        )
        if isinstance(callback.message, Message):
            await callback.message.edit_reply_markup(reply_markup=None)

    dp = Dispatcher()
    dp.include_router(router)
    return dp

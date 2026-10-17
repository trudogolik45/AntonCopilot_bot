import logging
from collections.abc import Sequence
from typing import Protocol

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    BusinessConnection,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from antoncopilot.db import ChatMessage, Draft

log = logging.getLogger(__name__)

SEND_PREFIX = "send:"
HISTORY_LIMIT = 20
ATTACHMENT_LABELS = {
    "voice": "[голосовое]",
    "video_note": "[видеосообщение]",
    "sticker": "[стикер]",
    "photo": "[фото]",
    "video": "[видео]",
    "document": "[файл]",
}


class DraftWriter(Protocol):
    async def write(self, history: Sequence[ChatMessage]) -> str: ...


def send_keyboard(draft: Draft) -> InlineKeyboardMarkup:
    button = InlineKeyboardButton(text="Отправить", callback_data=f"{SEND_PREFIX}{draft.id}")
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


def render_draft(message: Message, incoming: str, draft: Draft) -> str:
    name = message.from_user.full_name if message.from_user else "Без имени"
    return f"{name}: {incoming}\n\nЧерновик:\n{draft.text}"


def draft_source(message: Message) -> str | None:
    """Текст, на который пишется Черновик: сам текст или подпись к фото."""
    if message.photo:
        return message.caption
    return message.text


def history_text(message: Message) -> str:
    """Как сообщение выглядит в Истории чата: текст или метка вложения с подписью."""
    if text := draft_source(message):
        return text
    label = next(
        (label for kind, label in ATTACHMENT_LABELS.items() if getattr(message, kind)),
        "[вложение]",
    )
    return " ".join(filter(None, [label, message.caption]))


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

    async def remember(
        owner_id: int, chat_id: int, message_id: int, from_owner: bool, text: str
    ) -> list[ChatMessage]:
        """Добавляет сообщение в историю чата и возвращает её последние HISTORY_LIMIT сообщений."""
        in_chat = (ChatMessage.owner_id == owner_id, ChatMessage.chat_id == chat_id)
        recent_ids = (
            select(ChatMessage.id)
            .where(*in_chat)
            .order_by(ChatMessage.id.desc())
            .limit(HISTORY_LIMIT)
        )
        async with sessionmaker() as db, db.begin():
            await db.execute(
                insert(ChatMessage)
                .values(
                    owner_id=owner_id,
                    chat_id=chat_id,
                    message_id=message_id,
                    from_owner=from_owner,
                    text=text,
                )
                .on_conflict_do_nothing()
            )
            await db.execute(delete(ChatMessage).where(*in_chat, ChatMessage.id.not_in(recent_ids)))
            history = await db.scalars(select(ChatMessage).where(*in_chat).order_by(ChatMessage.id))
            return list(history)

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

    @router.business_message(F.business_connection_id)
    async def on_incoming(message: Message, bot: Bot) -> None:
        connection = await bot.get_business_connection(message.business_connection_id or "")
        from_owner = is_from_owner(message, connection)
        incoming = history_text(message)
        history = await remember(
            connection.user.id, message.chat.id, message.message_id, from_owner, incoming
        )
        if from_owner:
            log.info("owner_outgoing_seen", extra={"chat_id": message.chat.id})
            return
        if not draft_source(message):
            return
        draft = await save(
            Draft(
                business_connection_id=connection.id,
                owner_id=connection.user.id,
                chat_id=message.chat.id,
                text=await writer.write(history),
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
        sent = await bot.send_message(
            draft.chat_id, draft.text, business_connection_id=draft.business_connection_id
        )
        await remember(draft.owner_id, draft.chat_id, sent.message_id, True, draft.text)
        if isinstance(callback.message, Message):
            await callback.message.edit_reply_markup(reply_markup=None)

    dp = Dispatcher()
    dp.include_router(router)
    return dp

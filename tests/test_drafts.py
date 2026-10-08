import logging
from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram import Bot
from aiogram.methods import SendMessage
from aiogram.types import (
    CallbackQuery,
    Chat,
    Document,
    InlineKeyboardMarkup,
    PhotoSize,
    Update,
    User,
    Voice,
)
from aiogram.types import Message as TgMessage

from antoncopilot.app import build_dispatcher
from tests.conftest import (
    CONNECTION_ID,
    INTERLOCUTOR,
    OWNER,
    OWNER_BOT_CHAT_ID,
    STRANGER,
    FakeSession,
    FakeWriter,
)

_update_id = 0


def business_message(text: str | None = None, sender: User = INTERLOCUTOR, **extra: Any) -> Update:
    global _update_id
    _update_id += 1
    message = TgMessage(
        message_id=_update_id,
        date=datetime.now(UTC),
        chat=Chat(id=INTERLOCUTOR.id, type="private", first_name=INTERLOCUTOR.first_name),
        from_user=sender,
        business_connection_id=CONNECTION_ID,
        text=text,
        **extra,
    )
    return Update(update_id=_update_id, business_message=message)


async def test_incoming_message_brings_draft_to_owner_with_send_button(
    bot: Bot, session: FakeSession, writer: FakeWriter, sessionmaker: Any
) -> None:
    dp = build_dispatcher(sessionmaker, writer)

    await dp.feed_update(bot, business_message("Сколько стоит лендинг?"))

    [draft] = session.sent()
    assert draft.chat_id == OWNER_BOT_CHAT_ID
    assert "Иван" in draft.text
    assert "Сколько стоит лендинг?" in draft.text
    assert "Здравствуйте! Пришлите детали — посчитаю." in draft.text
    send_button_data(draft)


def send_button_data(draft: SendMessage) -> str:
    assert isinstance(draft.reply_markup, InlineKeyboardMarkup)
    [[button]] = draft.reply_markup.inline_keyboard
    assert button.text == "Отправить"
    assert isinstance(button.callback_data, str)
    return button.callback_data


def press(button_data: str, user: User) -> Update:
    global _update_id
    _update_id += 1
    return Update(
        update_id=_update_id,
        callback_query=CallbackQuery(
            id=str(_update_id),
            from_user=user,
            chat_instance="ci",
            data=button_data,
            message=TgMessage(
                message_id=1,
                date=datetime.now(UTC),
                chat=Chat(id=OWNER_BOT_CHAT_ID, type="private"),
                text="Черновик",
            ),
        ),
    )


async def test_owner_send_delivers_draft_to_interlocutor_on_owners_behalf(
    bot: Bot, session: FakeSession, writer: FakeWriter, sessionmaker: Any
) -> None:
    dp = build_dispatcher(sessionmaker, writer)
    await dp.feed_update(bot, business_message("Сколько стоит лендинг?"))
    [draft] = session.sent()

    await dp.feed_update(bot, press(send_button_data(draft), OWNER))

    reply = session.sent()[-1]
    assert reply.chat_id == INTERLOCUTOR.id
    assert reply.business_connection_id == CONNECTION_ID
    assert reply.text == "Здравствуйте! Пришлите детали — посчитаю."


async def test_send_pressed_by_someone_else_sends_nothing(
    bot: Bot, session: FakeSession, writer: FakeWriter, sessionmaker: Any
) -> None:
    dp = build_dispatcher(sessionmaker, writer)
    await dp.feed_update(bot, business_message("Сколько стоит лендинг?"))
    [draft] = session.sent()

    await dp.feed_update(bot, press(send_button_data(draft), STRANGER))

    assert session.sent() == [draft]


async def test_voice_message_brings_no_draft(
    bot: Bot, session: FakeSession, writer: FakeWriter, sessionmaker: Any
) -> None:
    dp = build_dispatcher(sessionmaker, writer)

    await dp.feed_update(
        bot, business_message(voice=Voice(file_id="v", file_unique_id="v", duration=3))
    )

    assert session.sent() == []


async def test_photo_caption_brings_draft(
    bot: Bot, session: FakeSession, writer: FakeWriter, sessionmaker: Any
) -> None:
    dp = build_dispatcher(sessionmaker, writer)
    photo = [PhotoSize(file_id="p", file_unique_id="p", width=10, height=10)]

    await dp.feed_update(bot, business_message(photo=photo, caption="Вот макет, что скажете?"))

    [draft] = session.sent()
    assert "Вот макет, что скажете?" in draft.text
    assert writer.incoming == ["Вот макет, что скажете?"]


async def test_owners_own_message_brings_no_draft_and_is_logged(
    bot: Bot,
    session: FakeSession,
    writer: FakeWriter,
    sessionmaker: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    dp = build_dispatcher(sessionmaker, writer)
    update = business_message("Да, сейчас пришлю", sender=OWNER)

    with caplog.at_level(logging.INFO):
        await dp.feed_update(bot, update)

    assert session.sent() == []
    assert "owner_outgoing_seen" in caplog.text


async def test_second_send_press_does_not_send_again(
    bot: Bot, session: FakeSession, writer: FakeWriter, sessionmaker: Any
) -> None:
    dp = build_dispatcher(sessionmaker, writer)
    await dp.feed_update(bot, business_message("Сколько стоит лендинг?"))
    [draft] = session.sent()
    button_data = send_button_data(draft)
    await dp.feed_update(bot, press(button_data, OWNER))

    await dp.feed_update(bot, press(button_data, OWNER))

    replies = [m for m in session.sent() if m.chat_id == INTERLOCUTOR.id]
    assert len(replies) == 1


async def test_document_with_caption_brings_no_draft(
    bot: Bot, session: FakeSession, writer: FakeWriter, sessionmaker: Any
) -> None:
    dp = build_dispatcher(sessionmaker, writer)
    document = Document(file_id="d", file_unique_id="d")

    await dp.feed_update(bot, business_message(document=document, caption="Договор во вложении"))

    assert session.sent() == []

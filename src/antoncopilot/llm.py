from collections.abc import Sequence

import httpx

from antoncopilot.db import ChatMessage

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

INSTRUCTIONS = (
    "Ты пишешь ответ в Telegram от имени Владельца аккаунта. "
    "Тебе дана переписка: user — Собеседник, assistant — Владелец. "
    "Напиши следующую реплику Владельца с учётом всей беседы. "
    "Верни только текст ответа Собеседнику, без пояснений. "
    "Стиль Владельца:\n\n"
)


class OpenRouterWriter:
    def __init__(self, http: httpx.AsyncClient, api_key: str, model: str, style: str) -> None:
        self._http = http
        self._api_key = api_key
        self._model = model
        self._style = style

    async def write(self, history: Sequence[ChatMessage]) -> str:
        response = await self._http.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": INSTRUCTIONS + self._style},
                    *(as_chat_turn(m) for m in history),
                ],
            },
        )
        response.raise_for_status()
        content: str = response.json()["choices"][0]["message"]["content"]
        return content.strip()


def as_chat_turn(message: ChatMessage) -> dict[str, str]:
    return {"role": "assistant" if message.from_owner else "user", "content": message.text}

import json

import httpx
import respx

from antoncopilot.llm import OpenRouterWriter

URL = "https://openrouter.ai/api/v1/chat/completions"


@respx.mock
async def test_writer_sends_model_style_and_message_and_returns_reply() -> None:
    route = respx.post(URL).respond(
        json={"choices": [{"message": {"role": "assistant", "content": "Давайте. Во сколько?"}}]}
    )
    async with httpx.AsyncClient() as http:
        writer = OpenRouterWriter(
            http, api_key="sk-test", model="anthropic/claude-haiku-5.5", style="Пишу коротко."
        )

        reply = await writer.write("Можем созвониться завтра?")

    assert reply == "Давайте. Во сколько?"
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer sk-test"
    body = json.loads(request.content)
    assert body["model"] == "anthropic/claude-haiku-5.5"
    assert "Пишу коротко." in json.dumps(body["messages"], ensure_ascii=False)
    assert body["messages"][-1] == {"role": "user", "content": "Можем созвониться завтра?"}

import os

import ollama
import pytest


@pytest.mark.skipif(
    os.getenv("RUN_OLLAMA_TESTS") != "1",
    reason="Set RUN_OLLAMA_TESTS=1 to run tests that require a local Ollama server.",
)
def test_ollama_chat_returns_response():
    response = ollama.chat(
        model=os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b"),
        messages=[{"role": "user", "content": "Say hello in Spanish"}],
    )

    assert response["message"]["content"].strip()
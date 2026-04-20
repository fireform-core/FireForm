import pytest


def test_ollama_chat_smoke():
    ollama = pytest.importorskip("ollama")
    response = ollama.chat(
        model="mistral",
        messages=[{"role": "user", "content": "Say hello in Spanish"}],
    )
    assert "message" in response
    assert "content" in response["message"]
    assert response["message"]["content"]
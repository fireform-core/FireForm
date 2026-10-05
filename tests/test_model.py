# test_ollama.py
import os

import ollama

response = ollama.chat(
    model=os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b"),
    messages=[
        {"role": "user", "content": "Say hello in Spanish"}
    ],
)
print("Success! Response:", response["message"]["content"])

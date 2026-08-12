import hashlib
import json
import os

import requests

from benchmark.evaluators.accuracy import calculate_accuracy


PROMPT_VERSION = "1"
SYSTEM_PROMPT = """You create reference answers for extraction benchmarks.
Use only facts supported by the narrative, preserve source wording when practical,
and return only JSON matching the supplied template. Do not add fields."""


def calculate_reference_accuracy(
    extracted: dict, narrative: str, template: dict, cache_path: str
) -> tuple[float, dict]:
    """Score an on-device extraction against a cached large-model reference."""
    model = os.environ["BENCHMARK_REFERENCE_MODEL"]
    input_hash = hashlib.sha256(
        (
            narrative
            + json.dumps(template, sort_keys=True)
            + model
            + PROMPT_VERSION
        ).encode()
    ).hexdigest()

    if os.path.exists(cache_path):
        with open(cache_path) as file:
            cached = json.load(file)
        if cached["metadata"]["input_hash"] == input_hash:
            reference = cached["reference"]
            return calculate_accuracy(extracted, reference), reference

    headers = {"Content-Type": "application/json"}
    if api_key := os.getenv("BENCHMARK_REFERENCE_API_KEY"):
        headers["Authorization"] = f"Bearer {api_key}"

    response = requests.post(
        os.environ["BENCHMARK_REFERENCE_URL"],
        headers=headers,
        json={
            "model": model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"template": template, "narrative": narrative}
                    ),
                },
            ],
        },
        timeout=int(os.getenv("BENCHMARK_REFERENCE_TIMEOUT", "120")),
    )
    response.raise_for_status()
    reference = json.loads(response.json()["choices"][0]["message"]["content"])

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w") as file:
        json.dump(
            {
                "metadata": {
                    "model": model,
                    "prompt_version": PROMPT_VERSION,
                    "input_hash": input_hash,
                },
                "reference": reference,
            },
            file,
            indent=2,
        )

    return calculate_accuracy(extracted, reference), reference

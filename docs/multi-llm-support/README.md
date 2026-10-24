# Multi LLM Support

FireForm can fill forms with several LLM providers at once. Each fill request picks a provider and a model, or falls back to the default.

## Supported providers

| Provider  | Value       | Runs where                                                                  | Needs               |
| --------- | ----------- | --------------------------------------------------------------------------- | ------------------- |
| Ollama    | `ollama`    | Local or your own server                                                    | `OLLAMA_HOST`       |
| OpenAI    | `openai`    | Hosted                                                                      | `OPENAI_API_KEY`    |
| Gemini    | `gemini`    | Hosted                                                                      | `GEMINI_API_KEY`    |
| Anthropic | `anthropic` | Hosted                                                                      | `ANTHROPIC_API_KEY` |
| Custom    | `custom`    | Any OpenAI compatible server (vLLM, LM Studio, llama.cpp, Groq, OpenRouter) | `CUSTOM_BASE_URL`   |

## How it works

1. At startup the backend reads the env file and turns on every provider whose `<PROVIDER>_MODELS` is set.
2. The local configuration API can additionally save provider credentials and custom provider settings; those settings are shared by the API and worker.
3. It asks each provider for its model list and logs a warning for anything that does not match.
4. `GET /api/v1/system/llm/models` returns the providers and the models that can be picked.
5. A fill request sends `provider` and `model`. The backend checks the pair before it stores or queues anything.
6. A request with neither uses the default, set by `LLM_PROVIDER` and `LLM_MODEL`, except that an unreadable saved default credential falls back to Ollama when Ollama is enabled.

## Privacy

Incident text holds names, addresses and medical detail. Hosted providers stay off until `LLM_ALLOW_EXTERNAL=true`. Ollama and custom servers on localhost or a private network need no flag.

## Pages

- [Setup](setup.md): turn providers on in the backend.
- [Configuration](configuration.md): every env setting.
- [API](api.md): endpoints, request fields and error codes.
- [User configuration](user-configuration.md): locally stored credentials, consent, manual models, and limitations.
- [Troubleshooting](troubleshooting.md): startup warnings and failed fills.

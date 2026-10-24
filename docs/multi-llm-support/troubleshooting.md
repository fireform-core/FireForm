# Troubleshooting

Check `make logs-app` for the app and `make logs-worker` for queued fills. Every message names the setting to change.

## Startup

| Log line                                                          | Fix                                                          |
| ----------------------------------------------------------------- | ------------------------------------------------------------ |
| `LLM settings need fixing, forms can't be filled until they are.` | Fix the setting named on the next line, then `make up`.      |
| `<PREFIX>_API_KEY is set but <PREFIX>_MODELS is empty.`           | Add `<PREFIX>_MODELS`, or remove the key.                    |
| `LLM_PROVIDER=<p>, but <PREFIX>_MODELS is empty so <p> is off.`   | Add `<PREFIX>_MODELS`, or change `LLM_PROVIDER`.             |
| `LLM_MODEL=<m> is not in <PREFIX>_MODELS.`                        | Add the model to the list, or change `LLM_MODEL`.            |
| `<PREFIX>_MODELS=* lists no model to default to. Set LLM_MODEL.`  | Set `LLM_MODEL`.                                             |
| `<p> is off: <PREFIX>_API_KEY is needed.`                         | Add the key, or empty `<PREFIX>_MODELS`.                     |
| `<url> is outside the local network ...`                          | Set `LLM_ALLOW_EXTERNAL=true`, or use a local server.        |
| `<PREFIX>_MODELS has <m>, but <p> does not offer it.`             | Fix the model name. It is left out of the model list.        |
| `<p> does not offer the default model <m>. Fills will fail.`      | Point `LLM_MODEL` at a model the provider lists.             |
| `Could not check the <p> models. <reason>`                        | The provider was down or refused at startup. See the reason. |

## Runtime

| Code                  | Usual cause                                           | Fix                                                                              |
| --------------------- | ----------------------------------------------------- | -------------------------------------------------------------------------------- |
| `LLM_AUTH_FAILED`     | Wrong or expired key                                  | Replace `<PREFIX>_API_KEY`, then `make up`.                                      |
| `LLM_MODEL_NOT_FOUND` | Typo, retired model, or not pulled in Ollama          | Pick a model from `GET /api/v1/system/llm/models`. If it appears under `downloadable`, install it with `POST /api/v1/system/llm/pull` (when the server allows that model), or run `ollama pull <model>` on the host. |
| `LLM_UNAVAILABLE`     | Server down, wrong URL, or timeout                    | Check `<PREFIX>_BASE_URL` or `OLLAMA_HOST`. Raise `LLM_TIMEOUT` for slow models. |
| `LLM_RATE_LIMITED`    | Provider quota or rate limit                          | Wait, or check the plan on the provider side.                                    |
| `LLM_BAD_RESPONSE`    | Server rejected an option, or the answer was cut off  | Set `<PREFIX>_STRUCTURED_OUTPUT=false`, or raise `<PREFIX>_MAX_TOKENS`.          |
| `LLM_NOT_AVAILABLE`   | Request named a provider or model that is not enabled | Use a pair from `GET /api/v1/system/llm/models`.                                 |

The log also records when a provider goes down and when it comes back.

## Ollama ran out of memory

`Ollama ran out of memory loading <model> and was killed` means the OS stopped the model runner. Ollama in Docker shares the Docker VM memory with every other container. A 1.5B model with the 32k context FireForm uses needs a little over 2 GB free.

- Raise the memory limit in Docker Desktop, Settings, Resources.
- Stop containers you don't need.
- Use a smaller model.
- Run Ollama on the host with `make fireform-native`. It uses the machine's memory and the GPU.

## Settings did not apply

- Run `make up`, not a restart. Containers only read the env file when they are created.
- After switching branches, also restart the worker. It keeps the old code loaded.
- Make sure no compose `environment:` entry sets the same variable. Those override the env file.

## Noisy model list

`*` returns everything the provider lists, including speech, image and embedding models. Use an explicit `<PREFIX>_MODELS` list to show only the models that can fill forms.

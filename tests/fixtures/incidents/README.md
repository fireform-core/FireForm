# Golden Incident Fixtures

These fixtures provide stable sample incident narratives and expected extracted
fields for regression testing FireForm's extraction pipeline.

Each fixture should include:

- `name`: a short unique fixture name.
- `input_text`: the incident narrative or transcript text.
- `fields`: the target extraction fields for the scenario.
- `expected`: the expected structured values for those fields.

The fixtures are intentionally small and deterministic. Tests should mock the
LLM/Ollama layer when using them so extraction regression checks can run
offline and reliably in CI.

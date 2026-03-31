# Session Resuming & Checkpointing

## Overview

In this pull request, FireForm's LLM extraction pipeline supports **stateful resumption**. If an extraction run is interrupted (container crash, Ollama timeout, manual `Ctrl+C`),  progress is saved after every successfully extracted field. The next run with the same transcript and target fields picks up where it left off.

## How It Works

### 1. Session ID

At the start of `main_loop()`, a unique `session_id` is computed as an MD5
hash of both the transcript text and the sorted field names. 

Hashing both inputs means the same transcript run against two different form
templates produces two separate checkpoints. 

### 2. State File Location

Progress is stored at:
```
$FIREFORM_STATE_DIR/.fireform_state_<session_id>.json
```

`FIREFORM_STATE_DIR` defaults to `/tmp/fireform_states`, which is always
writable inside Docker containers. Override it with:
```bash
export FIREFORM_STATE_DIR=/var/fireform/checkpoints
```

### 3. Atomic Writes

The pipeline writes to a `.tmp` file first then renames it. A crash mid-write won't
corrupt a previous checkpoint.

### 4. Per-Field Checkpointing

`save_state()` is called after every successful Ollama response. Any completed fields
don't need to be extracted again on the next run. 

### 5. Resume Logic

`main_loop()` calls `load_state()` at startup. If a matching checkpoint
exists, the prior JSON is loaded and `_target_fields` is filtered to skip
any field already present:
```python
fields_to_process = [f for f in all_field_names if f not in self._json]
```

### 6. Ctrl+C Handling

A `SIGINT` handler is registered at the start of `main_loop()`. Pressing
`Ctrl+C` calls `save_state()` before the process exits.

### 7. Cleanup on Success

`clear_state()` removes the checkpoint file automatically when all fields
are extracted.

### 8. Error Logging

When Ollama returns `-1` (field not found in transcript), the event is tracked in:
```
$FIREFORM_LOG_DIR/extraction_errors.jsonl
```

### 9. Retry on Timeout

If Ollama times out, the pipeline retries up to 3 delays (5s, 10s, 15s). If all 
retries are used, the checkpoint is saved before the error field so the next run resumes at the error field.

---

## Environment Variables

| Variable             | Default                  | Description                                |
|----------------------|--------------------------|--------------------------------------------|
| `FIREFORM_STATE_DIR` | `/tmp/fireform_states`   | Where checkpoint `.json` files are stored  |
| `FIREFORM_LOG_DIR`   | same as `STATE_DIR`      | Where `extraction_errors.jsonl` is written |
| `OLLAMA_HOST`        | `http://localhost:11434` | Ollama API endpoint                        |

---

## Example: Testing Resumption
```bash
# Start extraction, interrupt it with Ctrl+C partway through
docker compose exec app python3 src/main.py
# ^C
# [FireForm] Interrupted! Saving checkpoint so you can resume later...

# Another run, resuming from the checkpoint automatically
docker compose exec app python3 src/main.py
# [LOG] Found existing state file. Resuming session a3f91b2c...
#       (2 field(s) already extracted: ['name', 'date'])
# [LOG] Skipping 2 already-extracted field(s). 5 remaining.
```

## Clearing a Checkpoint Manually

To force a completely fresh extraction:
```bash
rm /tmp/fireform_states/.fireform_state_<session_id>.json
```

Or simply change the transcript or field list — that generates a new
`session_id` automatically and the old checkpoint is ignored.
# Form-filling benchmark

Runs `app/services/form_filler` on the ICS narratives and scores the filled
fields against hand-written ground truth, with an LLM judge for answers that
are right but worded differently.

## Setup

```bash
pip install -r requirements.txt
cp benchmark/.env.example benchmark/.env   # then set OLLAMA_HOST etc.
```

`benchmark/.env` is gitignored, so a private server address stays local.
Settings (see `config.py` and `.env.example`):

| Variable | Default | Used for |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | model under test (read by `app.core.config`) |
| `OLLAMA_MODEL` | `qwen2.5:1.5b` | model under test |
| `OLLAMA_TIMEOUT` | `300` | seconds per fill request |
| `JUDGE_HOST` | `OLLAMA_HOST` | LLM judge |
| `JUDGE_MODEL` | `qwen3.5:4b` | LLM judge |
| `JUDGE_TIMEOUT_SECONDS` | `300` | seconds per judge request |

Shell environment variables override `.env`. Both models must be pulled on
their Ollama server (`ollama pull qwen2.5:1.5b`, `ollama pull qwen3.5:4b`).

## Running

```bash
cd benchmark
python3 run.py                          # all 56 narratives (~10 min on a GPU server)
python3 run.py -d ics_203_1 ics_206_1   # a subset
python3 run.py -m qwen3.5:4b            # another model under test
python3 run.py --baseline               # full run, then publish it (see Baselines)
```

A document whose model call fails or times out, or whose output is cut off
mid-JSON (runaway generation hitting `num_predict`), is skipped and listed;
it is left out of the averages.

## Output

Each run gets its own folder, `results/<date>_<time>_<model>/` (gitignored):

| File | Contents |
|---|---|
| `summary.csv` | one row per document: judged, populated and raw accuracy, status |
| `wrong_fields.txt` | every wrong field, expected vs got, with the score before and after the judge |
| `run.log` | everything printed during the run |
| `run_info.json` | how to recreate the run (see below) |
| `prompt.txt` | the prompt file the run used |
| `<doc>/prompt.txt` | exact prompt sent to the model |
| `<doc>/schema.json` | JSON schema sent as Ollama's `format` |
| `<doc>/response.json` | raw model output |
| `<doc>/filled.json` | flat `{widget name: value}` written to the PDF |
| `<doc>/filled.pdf` | the filled form |
| `<doc>/review.pdf` | the filled form with wrong (red), partial (yellow) and missing (orange) fields marked |

## run_info.json

Every run records what produced it:

- **code**: git commit, branch, and any uncommitted changes under `app/`,
  `benchmark/` or `requirements.txt` (a run is only reproducible from its
  commit when that list is empty)
- **model_under_test**: model name, Ollama digest (the exact weights), size and
  quantization, the generation options, timeout, and the prompt's SHA-256
  (the prompt itself is saved next to it as `prompt.txt`)
- **judge**: the same for the judge model, plus its threshold
- **ollama_version**, Python and package versions, platform
- **documents** run, and the **results**: averages, skipped documents, time

Server addresses are left out on purpose; the digest identifies the model.
To recreate a run: check out the commit, `ollama pull` the models and check
their digests match, and run the same command.

## Baselines

Most runs stay local in `results/`. When a change is worth recording (a new
prompt, template change or model), run the full benchmark with `--baseline`:

```bash
python3 run.py --baseline
```

It overwrites `baselines/<model>/` with that run's `summary.csv`,
`wrong_fields.txt`, `run_info.json` and `prompt.txt`, which are small text
files meant to be committed with the change. The diff then shows the effect
on every document, and the folder's git history is the record of how
accuracy changed over time. The large per-document files (PDFs, raw
responses) are not published; attach a zipped run folder to the PR if
someone needs them.

`--baseline` refuses `-d`, so a baseline always covers every document.

Ollama is not fully deterministic even at temperature 0 with a fixed seed:
the same prompt can give different answers between runs, and single
documents (especially ICS 203) can move 10-30 points. Compare averages, and
treat one document's change as meaningful only if it repeats.

## Scoring

- Tables are compared row by row, matching each expected row to its
  best-matching output row, so rows in a different order are not wrong.
- Short values (6 words or fewer) must match exactly after lowercasing and
  punctuation removal; longer text is scored by word overlap.
- Filled-in fields scoring below 0.99 go to the LLM judge with the narrative,
  which accepts (1.0) or rejects (0.0) them. Blank answers are not judged.
  "Accuracy" is after the judge; "raw accuracy" is before it.
- "Populated" accuracy leaves out fields that are blank in the ground truth.

## Files

| File | Role |
|---|---|
| `run.py` | runner: fill, save, score, report, publish baselines |
| `config.py` | settings and `.env` loading |
| `run_info.py` | writes `run_info.json` |
| `compare.py` | shapes output and ground truth, computes the scores |
| `accuracy.py` | field and row similarity |
| `llm_judge.py` | LLM judge for failing fields |
| `report.py` | writes `wrong_fields.txt` |
| `review_pdf.py` | writes `review.pdf` |
| `data/pdfs/` | the 11 blank ICS forms |
| `data/narratives/` | 56 incident narratives, `<form>_<n>.txt` |
| `data/ground_truth/` | expected field values per narrative, keyed by widget name |
| `data/ICS_DATASET_GENERATOR_PROMPT.md` | prompt used to generate the narratives and ground truth |
| `baselines/<model>/` | published baseline results (committed) |
| `results/` | every run (gitignored) |

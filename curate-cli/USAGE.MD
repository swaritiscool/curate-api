# Curate.ai CLI Usage

This folder contains the high-performance Rust binary (`curate-cli`) and its companion Python wrapper. This toolset allows you to execute Curate.ai API tasks directly from the command line or from automation tools like n8n.

## Python Wrapper (Recommended for n8n)

The Python wrapper provides a convenient, robust interface to the underlying Rust binary. It safely handles loading JSON documents from disk to avoid terminal argument length limits.

**Path:** `../curate_wrapper.py`

### 1. Transform Operation

Transforms unstructured documents into structured JSON data according to a specified schema.

```bash
python3 ../curate_wrapper.py \
  --operation transform \
  --token "cai_live_YOUR_TOKEN" \
  --url "http://localhost:8000" \
  --task "extract action items" \
  --schema "tasks_v1" \
  --docs-file /path/to/your/documents.json
```

**Arguments:**
- `--operation transform`: Tells the script to run the document transformation pipeline.
- `--token`: Your Curate.ai API Bearer token.
- `--url`: (Optional) Base URL of the API. Defaults to `http://localhost:8000`.
- `--task`: Instructions for the LLM.
- `--schema`: Target JSON schema (e.g., `tasks_v1`, `summary_v1`, `entities_v1`).
- `--docs-file`: Absolute path to a JSON file containing an array of your documents.

**Example `documents.json` format:**
```json
[
  {
    "id": "doc_1",
    "content": "Raw text content here..."
  }
]
```

### 2. Get Usage Operation

Fetches the usage statistics for the provided API token.

```bash
python3 ../curate_wrapper.py \
  --operation getUsage \
  --token "cai_live_YOUR_TOKEN"
```

---

## Rust Binary (Advanced Usage)

If you prefer to bypass Python entirely, you can pipe raw JSON directly into the Rust binary's `stdin`.

**Path:** `./target/release/curate-cli`

### 1. Build the Binary

```bash
cargo build --release
```

### 2. Execute via Stdin

You must pipe a complete JSON object matching the `InputPayload` schema into the binary.

**Example Payload (`input.json`):**
```json
{
  "operation": "transform",
  "baseUrl": "http://localhost:8000",
  "token": "cai_live_YOUR_TOKEN",
  "payload": {
    "task": "extract action items",
    "schema": "tasks_v1",
    "documents": [
      {
        "id": "doc_1",
        "content": "Meeting notes..."
      }
    ]
  }
}
```

**Run Command:**
```bash
cat input.json | ./target/release/curate-cli
```

The binary will output the resulting JSON directly to `stdout`. Any crashes or API errors will result in a non-zero exit code and an error JSON object.

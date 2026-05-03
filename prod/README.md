# Curate.ai Go Port

Curate.ai is a document transformation API that takes messy multi-document input and returns schema-locked JSON. It uses BM25 pre-filtering to reduce token costs by 40-65% before calling an LLM.

## Features
- Contiguous document chunking with tiktoken (cl100k_base).
- Document classification (task vs reference).
- Okapi BM25 scoring with dynamic thresholding and fallback loops.
- Proportional chunk allocation across documents.
- Schema-locked JSON extraction via Ollama Cloud.
- Post-processing: deduplication, date/priority normalization, source traceability.

## Local Testing
Since these are Vercel Serverless Functions, you can test them using a minimal test harness or by running a local server that mimics the Vercel environment.

To run unit tests:
```bash
cd prod
go test ./pipeline/...
```

To test the handlers locally, you can use the `vercel dev` CLI if installed, or create a simple `main.go` that imports the handlers.

## Deployment to Vercel
Deploy using the Vercel CLI from the `prod/` directory:
```bash
cd prod
vercel --prod
```

## Environment Variables
- `OLLAMA_API_URL`: Base URL for the LLM provider (default: https://api.ollama.com/v1).
- `OLLAMA_API_KEY`: API key for the LLM provider.
- `MODEL_TASKS`: Model used for task extraction (default: llama3.3:70b).

## Schemas
- `tasks_v1`: Extracts action items with owners, priorities, and deadlines.
- `summary_v1`: Generates a concise summary and key points list.
- `entities_v1`: Extracts named entities (Person, Org, Location, etc.).

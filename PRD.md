
Curate.ai PRD — pipeline, build phases, constraints, and schemas
What you're building
Context structuring API for AI agents
POST messy multi-doc input → get back clean, schema-locked JSON. No chat. No UI. Pure transformation pipeline.
Processing pipeline
1
Chunking Python/Go
Split each doc into fixed-size chunks (256–512 tokens). Tag every chunk with doc_id, chunk_id, position. Never lose provenance.
2
Pre-filter No LLM
BM25 scoring against the task field. Drop any chunk below threshold. Kill 60–80% of tokens before any LLM call. Length filter removes boilerplate (<30 tokens).
3
Relevance ranking No LLM
Score surviving chunks against task-specific heuristics. extract_tasks → boost verb density. entities_v1 → boost named entity signals. Return top-N only.
4
LLM extraction Single call
One structured prompt. Top chunks + strict schema injected as system instruction. Output: JSON only — no prose, no markdown. Model must match the output schema exactly or retry once.
5
Post-processing Python/Go
Dedup identical extractions. Normalize field values (lowercase priorities, ISO dates). Attach source chunk references. Validate final JSON against schema before return.
V1 output schema — tasks_v1
{
  "status": "success",
  "data": {
    "tasks": [{
      "task": "string",
      "priority": "low | medium | high",
      "deadline": "string | null",
      "source": "doc1_chunk_4"
    }],
    "summary": "string"
  },
  "meta": {
    "chunks_used": 12,
    "tokens_used": 900,
    "docs_processed": 3
  }
}
Hard constraints
Max documents
20 per request
Max doc size
~4,000 tokens (aggressively enforce)
Max LLM calls
1 per request (V1)
Max processing time
15s hard timeout
Top chunks to LLM
Top 15 after filtering
JSON validation
Fail-fast if schema mismatch after 1 retry
Build phases
Day 1
Dumbest thing that works

    POST /v1/transform endpoint
    Single doc input only
    tasks_v1 schema hardcoded
    Direct LLM call, no filtering
    Return validated JSON

Day 2
Add the pipeline

    Chunker with provenance tags
    BM25 pre-filter
    Length + boilerplate filter
    Token count in meta

Day 3
Multi-doc + schemas

    Multi-doc support (up to 20)
    Source chunk tracing
    summary_v1 + entities_v1
    Task-specific ranking rules

Day 4
Make it real

    API key auth (Bearer)
    Usage logging
    Rate limiting
    Error codes + messages

What kills this
Vague or flexible schemas — if output shape shifts per request, agents can't integrate it. Rigidity is the product.
Skipping pre-filter — LLM on every chunk destroys unit economics. The cheap filter IS the margin.
Multiple LLM calls in V1 — adds latency, cost, and failure points. One call, one schema, one response.
Feature creep before the core works — no summarization modes, no webhooks, no streaming until the basic transform is bulletproof.
Where you actually win
Pre-filtering kills 60–80% of tokens before LLM — lower cost than calling the LLM directly on raw docs.
Deterministic output schema — agents can hardcode the response shape. No prompt engineering needed on the caller's side.
Source tracing on every field — debuggable. Agents and devs know exactly which doc chunk produced each result.
Multi-doc merging with dedup — signals from 20 docs collapsed into one clean object. Callers don't have to loop.


Here's the full hands-on PRD. Let me walk through the key decisions that will actually make or break the build:

The pipeline order matters a lot. The non-LLM stages (chunking → BM25 filter → ranking) are where your real value is. If you skip them and just dump docs into the LLM, you're just a wrapper — no cost advantage, no differentiation. The filtering is the product.

Day 1 should be embarrassingly simple. One doc. One hardcoded schema. Direct LLM call. The goal of Day 1 is just to validate that your input/output contract is correct and that JSON validation works end-to-end. Don't touch the pipeline until that's solid.

For the LLM call on Day 1, use Claude or OpenAI with a strict system prompt like: "You are a JSON extractor. Return ONLY valid JSON matching this exact schema. No prose, no markdown. If you cannot extract a field, use null." Then inject the schema inline. Add a one-retry if the response fails JSON validation — after that, return a 500.

BM25 on Day 2 — there are solid Python libraries (rank_bm25) that take 20 lines to wire up. Tokenize your chunks, score them against the task string, drop anything below a threshold (experiment around 0.1–0.2). This single step is what lets you cap token cost.

The three schemas for V1 are: tasks_v1 (action extraction), summary_v1 (structured summary with key points), entities_v1 (named entities — people, orgs, dates). Don't add a fourth until all three return consistent output across 20 different inputs.

Don't overthink the tech stack now. Use Python with FastAPI for speed of iteration — it's the fastest way to get the pipeline testable.

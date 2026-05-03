package models

// Document represents an input document to be processed.
type Document struct {
	ID      string `json:"id"`
	Content string `json:"content"`
	DocType string `json:"doc_type,omitempty"` // "task" | "reference" — set by classifier
}

// TransformRequest is the incoming request body for /v1/transform.
type TransformRequest struct {
	Documents  []Document `json:"documents"`
	Task       string     `json:"task"`
	SchemaType string     `json:"schema_type"`
}

// Chunk represents a segment of a document with metadata and scoring.
type Chunk struct {
	DocID    string  `json:"doc_id"`
	ChunkID  string  `json:"chunk_id"`
	Position int     `json:"position"`
	Content  string  `json:"content"`
	Score    float64 `json:"score"`
	DocType  string  `json:"doc_type"`
	Tokens   int     `json:"tokens"`
}

// Task represents a single extracted action item.
type Task struct {
	Task     string  `json:"task"`
	Priority string  `json:"priority"`
	Deadline *string `json:"deadline"`
	Source   string  `json:"source"`
}

// TransformData contains the structured output of the transformation.
type TransformData struct {
	Tasks    []Task   `json:"tasks,omitempty"`
	Summary  string   `json:"summary,omitempty"`
	Entities []Entity `json:"entities,omitempty"`
}

// Entity represents a named entity extracted from text.
type Entity struct {
	Name   string `json:"name"`
	Type   string `json:"type"`
	Source string `json:"source"`
}

// Meta contains processing statistics for token reduction tracking.
type Meta struct {
	ChunksUsed         int                `json:"chunks_used"`
	TokensUsed         int                `json:"tokens_used"`
	DocsProcessed      int                `json:"docs_processed"`
	TokensBeforeFilter int                `json:"tokens_before_filter"`
	TokensAfterFilter  int                `json:"tokens_after_filter"`
	ReductionPct       float64            `json:"reduction_pct"`
	DocClassifications map[string]string `json:"doc_classifications,omitempty"`
}

// TransformResponse is the final API response.
type TransformResponse struct {
	Status string        `json:"status"`
	Data   TransformData `json:"data"`
	Meta   Meta          `json:"meta"`
}

// ErrorResponse is returned for failed requests.
type ErrorResponse struct {
	Status  string `json:"status"`
	Message string `json:"message"`
	Code    int    `json:"code"`
}

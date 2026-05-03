package handler

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/your-org/curate-ai/models"
	"github.com/your-org/curate-ai/pipeline"
)

func TransformHandler(w http.ResponseWriter, r *http.Request) {
	startTime := time.Now()
	w.Header().Set("Content-Type", "application/json")

	if r.Method != http.MethodPost {
		w.WriteHeader(http.StatusMethodNotAllowed)
		json.NewEncoder(w).Encode(models.ErrorResponse{
			Status:  "error",
			Message: "Method not allowed",
			Code:    405,
		})
		return
	}

	var req models.TransformRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(models.ErrorResponse{
			Status:  "error",
			Message: "Invalid request body",
			Code:    400,
		})
		return
	}

	// Validation
	if len(req.Documents) == 0 {
		sendError(w, 400, "At least one document required")
		return
	}
	if len(req.Documents) > 20 {
		sendError(w, 400, "Maximum 20 documents allowed")
		return
	}
	if req.Task == "" {
		sendError(w, 400, "Task cannot be empty")
		return
	}
	validSchemas := map[string]bool{"tasks_v1": true, "summary_v1": true, "entities_v1": true}
	if !validSchemas[req.SchemaType] {
		sendError(w, 400, "Invalid schema type")
		return
	}

	totalTokensBefore := 0
	for _, doc := range req.Documents {
		if strings.TrimSpace(doc.Content) == "" {
			sendError(w, 400, "Document content cannot be empty")
			return
		}
		tokens, err := pipeline.CountTokens(doc.Content)
		if err != nil {
			sendError(w, 500, "Error counting tokens")
			return
		}
		if tokens > 4000 {
			sendError(w, 400, fmt.Sprintf("Document %s exceeds 4000 token limit", doc.ID))
			return
		}
		totalTokensBefore += tokens
	}

	// Pipeline
	// 1. Chunk
	chunks, err := pipeline.ChunkDocuments(req.Documents)
	if err != nil {
		sendError(w, 500, "Chunking failed: "+err.Error())
		return
	}

	// 2. Filter
	filteredChunks, err := pipeline.FilterChunks(chunks, req.Task, req.Documents)
	if err != nil {
		sendError(w, 500, "Filtering failed: "+err.Error())
		return
	}

	tokensAfterFilter := 0
	for _, c := range filteredChunks {
		tokensAfterFilter += c.Tokens
	}

	// 3. Rank
	rankedChunks := pipeline.RankChunks(filteredChunks, req.Task, req.SchemaType, 15)
	rankedChunks = pipeline.SelectTopChunksPerDoc(rankedChunks, req.Documents, 15)

	// 4. Extract
	data, tokensUsed, err := pipeline.ExtractWithLLM(rankedChunks, req.SchemaType, req.Task)
	if err != nil {
		sendError(w, 500, "Extraction failed: "+err.Error())
		return
	}

	// 5. Post-process
	resp, err := pipeline.PostProcess(data, rankedChunks, req.SchemaType, totalTokensBefore, tokensAfterFilter, len(req.Documents))
	if err != nil {
		sendError(w, 500, "Post-processing failed: "+err.Error())
		return
	}

	resp.Meta.TokensUsed = tokensUsed // Update with LLM reported tokens
	
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(resp)

	duration := time.Since(startTime).Milliseconds()
	log.Printf("Request processed in %d ms", duration)
}

func sendError(w http.ResponseWriter, code int, message string) {
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(models.ErrorResponse{
		Status:  "error",
		Message: message,
		Code:    code,
	})
}

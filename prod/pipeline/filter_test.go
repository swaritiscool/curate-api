package pipeline

import (
	"testing"
	"github.com/your-org/curate-ai/models"
)

func TestFilterChunks(t *testing.T) {
	t.Run("Happy Path", func(t *testing.T) {
		chunks := []models.Chunk{
			{ChunkID: "c1", Content: "urgent task: send the report by tomorrow morning", Tokens: 40, DocType: "task"},
			{ChunkID: "c2", Content: "irrelevant boilerplate text that should be filtered out", Tokens: 35, DocType: "reference"},
		}
		task := "send report"
		filtered, err := FilterChunks(chunks, task, nil)
		if err != nil {
			t.Fatalf("Expected no error, got %v", err)
		}
		if len(filtered) == 0 {
			t.Error("Expected at least one filtered chunk")
		}
	})

	t.Run("Empty Input", func(t *testing.T) {
		filtered, err := FilterChunks([]models.Chunk{}, "task", nil)
		if err != nil {
			t.Fatalf("Expected no error, got %v", err)
		}
		if len(filtered) != 0 {
			t.Error("Expected zero chunks")
		}
	})
}

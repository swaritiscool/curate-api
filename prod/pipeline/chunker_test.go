package pipeline

import (
	"testing"
	"github.com/your-org/curate-ai/models"
)

func TestChunkDocuments(t *testing.T) {
	t.Run("Happy Path", func(t *testing.T) {
		docs := []models.Document{
			{ID: "doc1", Content: "This is a simple document for testing chunking logic."},
		}
		chunks, err := ChunkDocuments(docs)
		if err != nil {
			t.Fatalf("Expected no error, got %v", err)
		}
		if len(chunks) == 0 {
			t.Error("Expected at least one chunk")
		}
	})

	t.Run("Empty Input", func(t *testing.T) {
		docs := []models.Document{}
		chunks, err := ChunkDocuments(docs)
		if err != nil {
			t.Fatalf("Expected no error, got %v", err)
		}
		if len(chunks) != 0 {
			t.Error("Expected zero chunks")
		}
	})

	t.Run("Oversized Input", func(t *testing.T) {
		content := ""
		for i := 0; i < 5000; i++ {
			content += "word "
		}
		docs := []models.Document{
			{ID: "oversized", Content: content},
		}
		chunks, err := ChunkDocuments(docs)
		if err != nil {
			t.Fatalf("Expected no error, got %v", err)
		}
		if len(chunks) <= 1 {
			t.Error("Expected multiple chunks for oversized input")
		}
	})
}

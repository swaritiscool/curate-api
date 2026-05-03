package pipeline

import (
	"testing"
	"github.com/your-org/curate-ai/models"
)

func TestSelectTopChunksPerDoc(t *testing.T) {
	t.Run("Happy Path", func(t *testing.T) {
		chunks := []models.Chunk{
			{DocID: "doc1", Score: 0.9},
			{DocID: "doc1", Score: 0.8},
			{DocID: "doc1", Score: 0.7},
			{DocID: "doc1", Score: 0.6},
			{DocID: "doc2", Score: 0.5},
		}
		docs := []models.Document{
			{ID: "doc1", Content: "Long doc..."},
			{ID: "doc2", Content: "Short doc"},
		}
		selected := SelectTopChunksPerDoc(chunks, docs, 15)
		if len(selected) != 5 {
			t.Errorf("Expected 5 chunks, got %d", len(selected))
		}
	})
}

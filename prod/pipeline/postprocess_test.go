package pipeline

import (
	"testing"
	"github.com/your-org/curate-ai/models"
)

func TestPostProcess(t *testing.T) {
	t.Run("Happy Path", func(t *testing.T) {
		deadline := "05/02/2026"
		data := &models.TransformData{
			Tasks: []models.Task{
				{Task: "Task 1", Priority: "High", Deadline: &deadline, Source: "c1"},
				{Task: "task 1", Priority: "Low", Source: "c1"}, // Duplicate
			},
		}
		chunks := []models.Chunk{{ChunkID: "c1"}}
		resp, err := PostProcess(data, chunks, "tasks_v1", 1000, 500, 1)
		if err != nil {
			t.Fatalf("Expected no error, got %v", err)
		}
		if len(resp.Data.Tasks) != 1 {
			t.Errorf("Expected 1 task after dedup, got %d", len(resp.Data.Tasks))
		}
		if resp.Meta.ReductionPct != 50.0 {
			t.Errorf("Expected 50.0%% reduction, got %f", resp.Meta.ReductionPct)
		}
	})
}

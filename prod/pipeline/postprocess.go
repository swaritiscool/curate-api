package pipeline

import (
	"math"
	"strings"
	"time"

	"github.com/your-org/curate-ai/models"
)

// PORTED FROM: pipeline/postprocess.py

func normalizePriority(priority string) string {
	p := strings.ToLower(strings.TrimSpace(priority))
	switch p {
	case "high", "medium", "low":
		return p
	case "urgent", "critical":
		return "high"
	case "normal", "regular":
		return "medium"
	default:
		if p == "" {
			return "medium"
		}
		return p
	}
}

func normalizeDate(dateStr string) *string {
	if dateStr == "" || strings.ToLower(dateStr) == "null" {
		return nil
	}

	formats := []string{
		"2006-01-02",
		"01/02/2006",
		"02/01/2006",
		"January 02, 2006",
		"Jan 02, 2006",
	}

	for _, fmt := range formats {
		t, err := time.Parse(fmt, strings.TrimSpace(dateStr))
		if err == nil {
			s := t.Format("2006-01-02")
			return &s
		}
	}

	return &dateStr
}

func PostProcess(
	data *models.TransformData,
	chunks []models.Chunk,
	schemaType string,
	tokensBeforeFilter int,
	tokensAfterFilter int,
	docsProcessed int,
) (*models.TransformResponse, error) {
	chunkIDs := make(map[string]bool)
	for _, c := range chunks {
		chunkIDs[c.ChunkID] = true
	}

	if schemaType == "tasks_v1" {
		seenTasks := make(map[string]bool)
		var uniqueTasks []models.Task
		for _, t := range data.Tasks {
			taskKey := strings.ToLower(strings.TrimSpace(t.Task))
			if !seenTasks[taskKey] {
				seenTasks[taskKey] = true
				
				t.Priority = normalizePriority(t.Priority)
				if t.Deadline != nil {
					t.Deadline = normalizeDate(*t.Deadline)
				}
				
				if !chunkIDs[t.Source] {
					t.Source = "unknown"
				}
				uniqueTasks = append(uniqueTasks, t)
			}
		}
		data.Tasks = uniqueTasks
	} else if schemaType == "entities_v1" {
		seenEntities := make(map[string]bool)
		var uniqueEntities []models.Entity
		for _, e := range data.Entities {
			entityKey := strings.ToLower(strings.TrimSpace(e.Name))
			if !seenEntities[entityKey] {
				seenEntities[entityKey] = true
				
				if !chunkIDs[e.Source] {
					e.Source = "unknown"
				}
				uniqueEntities = append(uniqueEntities, e)
			}
		}
		data.Entities = uniqueEntities
	}

	reductionPct := 0.0
	if tokensBeforeFilter > 0 {
		reductionPct = (1.0 - float64(tokensAfterFilter)/float64(tokensBeforeFilter)) * 100.0
		reductionPct = math.Round(reductionPct*10) / 10
	}

	return &models.TransformResponse{
		Status: "success",
		Data:   *data,
		Meta: models.Meta{
			ChunksUsed:         len(chunks),
			TokensUsed:         tokensAfterFilter, // Approximate as tokens after filter
			DocsProcessed:      docsProcessed,
			TokensBeforeFilter: tokensBeforeFilter,
			TokensAfterFilter:  tokensAfterFilter,
			ReductionPct:       reductionPct,
		},
	}, nil
}

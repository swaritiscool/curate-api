package pipeline

import (
	"regexp"
	"sort"
	"strings"

	"github.com/your-org/curate-ai/models"
)

// PORTED FROM: pipeline/ranker.py

var verbPatterns = []string{
	`\b(need|must|should|will|would|could|may|might)\b`,
	`\b(complete|finish|start|begin|end|submit|review|approve|finalize|wrap|close)\b`,
	`\b(create|update|delete|fix|build|deploy|test|implement|develop|code|refactor|merge|rollback)\b`,
	`\b(send|call|email|contact|meet|schedule|ping|notify|alert|inform|tell|ask|request)\b`,
	`\b(confirm|coordinate|check|chase|follow|follow-up|sync|align|pair|loop|escalate|flag|block)\b`,
	`\b(write|document|draft|prepare|update|record|log|note|report|present|share)\b`,
	`\b(check|verify|validate|investigate|debug|analyze|research|look|spike|audit|inspect)\b`,
	`\b(decide|choose|select|pick|confirm|approve|reject|accept|agree|commit)\b`,
	`\b(action|todo|task|ticket|blocker|blocked|pending|waiting|owner|due|deadline)\b`,
}

var verbRegexes []*regexp.Regexp

func init() {
	for _, p := range verbPatterns {
		verbRegexes = append(verbRegexes, regexp.MustCompile("(?i)"+p))
	}
}

func calculateVerbDensity(text string) float64 {
	textLower := strings.ToLower(text)
	verbCount := 0
	for _, re := range verbRegexes {
		verbCount += len(re.FindAllString(textLower, -1))
	}

	words := strings.Fields(text)
	if len(words) == 0 {
		return 0.0
	}
	return float64(verbCount) / float64(len(words))
}

func extractNamedEntitiesCount(text string) int {
	count := 0
	capWords := regexp.MustCompile(`\b[A-Z][a-z]+\b`)
	count += len(capWords.FindAllString(text, -1))

	datePatterns := regexp.MustCompile(`\b\d{1,2}/\d{1,2}/\d{2,4}\b`)
	count += len(datePatterns.FindAllString(text, -1))

	return count
}

func RankChunks(chunks []models.Chunk, task string, schemaType string, topN int) []models.Chunk {
	scoredChunks := make([]models.Chunk, len(chunks))
	for i, chunk := range chunks {
		if chunk.Score == 0 {
			switch schemaType {
			case "tasks_v1":
				chunk.Score = calculateVerbDensity(chunk.Content)
			case "entities_v1":
				chunk.Score = float64(extractNamedEntitiesCount(chunk.Content)) * 0.01
			case "summary_v1":
				chunk.Score = float64(len(chunk.Content)) / 100.0
			default:
				chunk.Score = 0.5
			}
		}
		scoredChunks[i] = chunk
	}

	sort.Slice(scoredChunks, func(i, j int) bool {
		return scoredChunks[i].Score > scoredChunks[j].Score
	})

	if len(scoredChunks) > topN {
		return scoredChunks[:topN]
	}
	return scoredChunks
}

func SelectTopChunksPerDoc(allChunks []models.Chunk, documents []models.Document, totalBudget int) []models.Chunk {
	numDocs := len(documents)
	if numDocs == 0 {
		if len(allChunks) > totalBudget {
			return allChunks[:totalBudget]
		}
		return allChunks
	}

	minPerDoc := 3
	baseAllocation := minPerDoc
	remainingBudget := totalBudget - (baseAllocation * numDocs)
	if remainingBudget < 0 {
		remainingBudget = 0
	}

	totalTokens := 0
	for _, doc := range documents {
		// Estimate tokens if not available (4 chars per token roughly)
		tokens := len(doc.Content) / 4
		if tokens == 0 {
			tokens = 1
		}
		totalTokens += tokens
	}

	var selected []models.Chunk
	for _, doc := range documents {
		var docChunks []models.Chunk
		for _, c := range allChunks {
			if c.DocID == doc.ID {
				docChunks = append(docChunks, c)
			}
		}

		if len(docChunks) == 0 {
			continue
		}

		docTokens := len(doc.Content) / 4
		proportion := float64(docTokens) / float64(totalTokens)
		extra := int(float64(remainingBudget) * proportion)
		allocation := baseAllocation + extra

		sort.Slice(docChunks, func(i, j int) bool {
			return docChunks[i].Score > docChunks[j].Score
		})

		if len(docChunks) > allocation {
			selected = append(selected, docChunks[:allocation]...)
		} else {
			selected = append(selected, docChunks...)
		}
	}

	// Final sort and limit to total budget
	sort.Slice(selected, func(i, j int) bool {
		return selected[i].Score > selected[j].Score
	})

	if len(selected) > totalBudget {
		return selected[:totalBudget]
	}
	return selected
}

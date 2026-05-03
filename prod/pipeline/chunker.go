package pipeline

import (
	"fmt"
	"regexp"
	"strings"

	"github.com/pkoukk/tiktoken-go"
	"github.com/your-org/curate-ai/models"
)

// PORTED FROM: pipeline/chunker.py

func ClassifyDocument(content string) string {
	content = strings.TrimSpace(content)
	lines := strings.Split(content, "\n")
	if len(lines) == 0 {
		return "reference"
	}

	// First 20% and middle 20%
	first20Limit := len(lines) / 5
	if first20Limit < 5 {
		first20Limit = 5
	}
	if first20Limit > len(lines) {
		first20Limit = len(lines)
	}
	first20Lines := lines[:first20Limit]

	middleStart := int(float64(len(lines)) * 0.4)
	middleLimit := len(lines) / 5
	if middleLimit < 5 {
		middleLimit = 5
	}
	middleEnd := middleStart + middleLimit
	if middleEnd > len(lines) {
		middleEnd = len(lines)
	}
	if middleStart > len(lines) {
		middleStart = len(lines)
		middleEnd = len(lines)
	}
	middle20Lines := lines[middleStart:middleEnd]

	combinedText := strings.ToLower(strings.Join(first20Lines, " ") + " " + strings.Join(middle20Lines, " "))

	strongTaskIndicators := []string{
		"meeting", "minutes", "participants", "attendees",
		"action item", "action items",
		"agenda", "sync", "standup", "retrospective",
		"said", "asked", "replied", "responded",
	}

	taskIndicators := []string{
		"send", "schedule", "follow up", "confirm", "update",
		"create", "review", "complete", "assign", "check",
		"coordinate", "draft", "ping", "relay", "chase",
		"own", "write", "flag", "contact",
	}

	strongRefIndicators := []string{
		"runbook", "specification", "glossary", "architecture",
		"technical documentation", "api reference", "user guide",
		"system design", "infrastructure", "deployment guide",
		"table of contents", "overview", "introduction",
	}

	referenceIndicators := []string{
		"technical", "implementation", "deployed", "configured",
		"service", "microservice", "kubernetes", "docker", "container",
		"module", "component", "infrastructure", "system",
		"api", "endpoint", "authentication", "authorization",
		"database", "cache", "queue", "worker", "gateway",
	}

	totalTaskWords := 0
	totalRefWords := 0
	strongTaskCount := 0
	taskCount := 0
	strongRefCount := 0
	refCount := 0

	for _, indicator := range strongTaskIndicators {
		count := strings.Count(combinedText, indicator)
		if count > 0 {
			strongTaskCount++
			totalTaskWords += count * 3
		}
	}
	for _, indicator := range taskIndicators {
		count := strings.Count(combinedText, indicator)
		if count > 0 {
			taskCount++
			totalTaskWords += count
		}
	}
	for _, indicator := range strongRefIndicators {
		count := strings.Count(combinedText, indicator)
		if count > 0 {
			strongRefCount++
			totalRefWords += count * 3
		}
	}
	for _, indicator := range referenceIndicators {
		count := strings.Count(combinedText, indicator)
		if count > 0 {
			refCount++
			totalRefWords += count
		}
	}

	listRegex := regexp.MustCompile(`^[-\*•]\s`)
	hasListStructure := false
	for _, line := range first20Lines {
		if listRegex.MatchString(strings.TrimSpace(line)) {
			hasListStructure = true
			break
		}
	}

	hasDialogue := false
	names := []string{"rohan", "sarah", "mike", "team:", "priya:", "dev:", "marcus:"}
	for i := 0; i < len(first20Lines) && i < 10; i++ {
		line := strings.ToLower(first20Lines[i])
		if strings.Contains(line, ":") && len(strings.Fields(line)) < 20 {
			for _, name := range names {
				if strings.Contains(line, name) {
					hasDialogue = true
					break
				}
			}
		}
		if hasDialogue {
			break
		}
	}

	if strongTaskCount >= 3 || (strongTaskCount >= 2 && hasDialogue) {
		return "task"
	}
	if strongRefCount >= 2 {
		return "reference"
	}
	if refCount >= 8 {
		return "reference"
	}
	if hasListStructure && taskCount >= 3 {
		return "task"
	}
	if totalTaskWords >= 20 {
		return "task"
	}
	if float64(totalTaskWords) > float64(totalRefWords)*1.5 {
		return "task"
	}

	return "reference"
}

func CountTokens(text string) (int, error) {
	tke, err := tiktoken.GetEncoding("cl100k_base")
	if err != nil {
		return 0, err
	}
	tokens := tke.Encode(text, nil, nil)
	return len(tokens), nil
}

func ChunkDocuments(docs []models.Document) ([]models.Chunk, error) {
	tke, err := tiktoken.GetEncoding("cl100k_base")
	if err != nil {
		return nil, err
	}

	var allChunks []models.Chunk
	chunkSize := 256
	overlap := 50

	for _, doc := range docs {
		docType := ClassifyDocument(doc.Content)
		tokens := tke.Encode(doc.Content, nil, nil)
		
		start := 0
		chunkIdx := 0
		
		if len(tokens) == 0 {
			continue
		}

		for start < len(tokens) {
			end := start + chunkSize
			if end > len(tokens) {
				end = len(tokens)
			}
			
			chunkTokens := tokens[start:end]
			chunkText := tke.Decode(chunkTokens)
			
			if strings.TrimSpace(chunkText) != "" {
				chunk := models.Chunk{
					DocID:    doc.ID,
					ChunkID:  fmt.Sprintf("%s_chunk_%d", doc.ID, chunkIdx),
					Position: start,
					Content:  chunkText,
					DocType:  docType,
					Tokens:   len(chunkTokens),
				}
				allChunks = append(allChunks, chunk)
				chunkIdx++
			}
			
			if end == len(tokens) {
				break
			}
			start += chunkSize - overlap
		}
	}

	return allChunks, nil
}

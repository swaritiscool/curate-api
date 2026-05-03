package pipeline

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/your-org/curate-ai/models"
	"github.com/your-org/curate-ai/schemas"
)

// PORTED FROM: pipeline/extractor.py

var ModelMap = map[string]string{
	"tasks_v1":    "llama3.3:70b",
	"entities_v1": "llama3.3:70b",
	"summary_v1":  "llama3.1:8b",
}

func trimChunkText(text string, maxWords int) string {
	words := strings.Fields(text)
	if len(words) <= maxWords {
		return text
	}
	keepStart := int(float64(maxWords) * 0.7)
	keepEnd := int(float64(maxWords) * 0.3)
	
	if keepStart+keepEnd > len(words) {
		return text
	}
	
	return strings.Join(words[:keepStart], " ") + " ... " + strings.Join(words[len(words)-keepEnd:], " ")
}

func buildExtractPrompt(chunks []models.Chunk, task string, schemaType string) string {
	var chunkTexts []string
	for _, chunk := range chunks {
		trimmed := trimChunkText(chunk.Content, 100)
		chunkTexts = append(chunkTexts, fmt.Sprintf("[Source: %s]\n%s", chunk.ChunkID, trimmed))
	}
	
	chunkSection := strings.Join(chunkTexts, "\n\n---\n\n")
	
	return fmt.Sprintf("TASK: %s\n\nCHUNKS:\n%s\n\nOUTPUT:\nReturn ONLY valid JSON matching the schema.", task, chunkSection)
}

func getSystemPrompt(schemaType string) string {
	switch schemaType {
	case "tasks_v1":
		return schemas.TasksV1SystemPrompt
	case "summary_v1":
		return schemas.SummaryV1SystemPrompt
	case "entities_v1":
		return schemas.EntitiesV1SystemPrompt
	default:
		return "You are a JSON extraction engine. Return ONLY valid JSON."
	}
}

type ChatMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type OllamaChatRequest struct {
	Model    string        `json:"model"`
	Messages []ChatMessage `json:"messages"`
	Stream   bool          `json:"stream"`
}

type OllamaChatResponse struct {
	Message struct {
		Content string `json:"content"`
	} `json:"message"`
}

func ExtractWithLLM(chunks []models.Chunk, schemaType string, task string) (*models.TransformData, int, error) {
	apiKey := os.Getenv("OLLAMA_API_KEY")

	if apiKey == "" {
		return nil, 0, errors.New("OLLAMA_API_KEY not set")
	}

	model, ok := ModelMap[schemaType]
	if !ok {
		model = "llama3.3:70b"
	}

	systemPrompt := getSystemPrompt(schemaType)
	userPrompt := buildExtractPrompt(chunks, task, schemaType)

	client := &http.Client{
		Timeout: 55 * time.Second,
	}

	var lastErr error
	for retry := 0; retry <= 1; retry++ {
		reqBody := OllamaChatRequest{
			Model: model,
			Messages: []ChatMessage{
				{Role: "system", Content: systemPrompt},
				{Role: "user", Content: userPrompt},
			},
			Stream: false,
		}

		bodyBytes, _ := json.Marshal(reqBody)
		req, _ := http.NewRequest("POST", "https://ollama.com/api/chat", bytes.NewBuffer(bodyBytes))
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Authorization", "Bearer "+apiKey)

		ctx, cancel := context.WithTimeout(context.Background(), 55*time.Second)
		defer cancel()
		req = req.WithContext(ctx)

		resp, err := client.Do(req)
		if err != nil {
			lastErr = err
			continue
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			respBody, _ := io.ReadAll(resp.Body)
			lastErr = fmt.Errorf("LLM API error: %d - %s", resp.StatusCode, string(respBody))
			continue
		}

		var ollamaResp OllamaChatResponse
		if err := json.NewDecoder(resp.Body).Decode(&ollamaResp); err != nil {
			lastErr = err
			continue
		}

		content := strings.TrimSpace(ollamaResp.Message.Content)
		if strings.HasPrefix(content, "```json") {
			content = strings.TrimPrefix(content, "```json")
			content = strings.TrimSuffix(content, "```")
		} else if strings.HasPrefix(content, "```") {
			content = strings.TrimPrefix(content, "```")
			content = strings.TrimSuffix(content, "```")
		}
		content = strings.TrimSpace(content)

		var data models.TransformData
		if err := json.Unmarshal([]byte(content), &data); err != nil {
			lastErr = err
			continue
		}

		tokensUsed := int(float64(len(strings.Fields(content+userPrompt+systemPrompt))) * 1.3)

		return &data, tokensUsed, nil
	}

	return nil, 0, lastErr
}

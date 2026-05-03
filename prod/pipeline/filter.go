package pipeline

import (
	"fmt"
	"math"
	"regexp"
	"strings"

	"github.com/your-org/curate-ai/models"
)

// PORTED FROM: pipeline/filter.py

var bm25Cleaner = regexp.MustCompile(`[^\w\s]`)

func tokenizeForBM25(text string) []string {
	text = strings.ToLower(text)
	text = bm25Cleaner.ReplaceAllString(text, "")
	return strings.Fields(text)
}

type BM25Index struct {
	DocCount    int
	AvgDocLen   float64
	DocLengths  []int
	DocFreqs    map[string]int
	TermFreqs   []map[string]int
	K1          float64
	B           float64
}

func NewBM25Index(chunks []models.Chunk) *BM25Index {
	idx := &BM25Index{
		DocCount:  len(chunks),
		DocFreqs:  make(map[string]int),
		TermFreqs: make([]map[string]int, len(chunks)),
		K1:        1.5,
		B:         0.75,
	}

	totalLen := 0
	for i, chunk := range chunks {
		tokens := tokenizeForBM25(chunk.Content)
		idx.DocLengths = append(idx.DocLengths, len(tokens))
		totalLen += len(tokens)
		
		tf := make(map[string]int)
		for _, token := range tokens {
			tf[token]++
		}
		idx.TermFreqs[i] = tf
		
		for token := range tf {
			idx.DocFreqs[token]++
		}
	}

	if idx.DocCount > 0 {
		idx.AvgDocLen = float64(totalLen) / float64(idx.DocCount)
	}

	return idx
}

func (idx *BM25Index) GetScores(query string) []float64 {
	queryTokens := tokenizeForBM25(query)
	scores := make([]float64, idx.DocCount)

	for _, token := range queryTokens {
		df := idx.DocFreqs[token]
		// rank_bm25 uses: log((N - n(qi) + 0.5) / (n(qi) + 0.5) + 1)
		idf := math.Log((float64(idx.DocCount-df)+0.5)/(float64(df)+0.5) + 1.0)
		if idf < 0 {
			idf = 0
		}

		for i := 0; i < idx.DocCount; i++ {
			tf := float64(idx.TermFreqs[i][token])
			docLen := float64(idx.DocLengths[i])
			
			score := idf * (tf * (idx.K1 + 1)) / (tf + idx.K1*(1-idx.B+idx.B*(docLen/idx.AvgDocLen)))
			scores[i] += score
		}
	}

	return scores
}

func FilterChunks(chunks []models.Chunk, task string, docs []models.Document) ([]models.Chunk, error) {
	if len(chunks) == 0 {
		return []models.Chunk{}, nil
	}

	// Filter by length first (drop < 30 tokens)
	var lengthFiltered []models.Chunk
	for _, chunk := range chunks {
		if chunk.Tokens >= 30 {
			lengthFiltered = append(lengthFiltered, chunk)
		}
	}

	if len(lengthFiltered) == 0 {
		// Fallback if everything filtered by length
		limit := 15
		if len(chunks) < limit {
			limit = len(chunks)
		}
		return chunks[:limit], nil
	}

	baseThreshold := 2.5 // From main.py: prefilter_chunks_with_stats(..., bm25_threshold=2.5, ...)
	
	// Fallback loop logic
	docIDs := make(map[string]bool)
	for _, chunk := range lengthFiltered {
		docIDs[chunk.DocID] = true
	}
	minRequired := 3 * len(docIDs)
	if minRequired > len(lengthFiltered) {
		minRequired = len(lengthFiltered)
	}

	relaxedThreshold := baseThreshold
	var filteredResult []models.Chunk

	idx := NewBM25Index(lengthFiltered)
	
	for {
		scores := idx.GetScores(task)
		filteredResult = nil
		
		for i, chunk := range lengthFiltered {
			score := scores[i]
			effectiveThreshold := relaxedThreshold
			if chunk.DocType == "reference" {
				effectiveThreshold = relaxedThreshold * 1.4
			}

			if score >= effectiveThreshold {
				chunk.Score = score
				filteredResult = append(filteredResult, chunk)
			}
		}

		if len(filteredResult) >= minRequired || relaxedThreshold <= 0.05 {
			break
		}
		
		relaxedThreshold = relaxedThreshold - 0.25
		if relaxedThreshold < 0.05 {
			relaxedThreshold = 0.05
		}
	}

	if len(filteredResult) == 0 && len(chunks) > 0 {
		limit := 15
		if len(chunks) < limit {
			limit = len(chunks)
		}
		return chunks[:limit], nil
	}

	// Log debug info (mimicking Python)
	fmt.Printf("Filter applied. Chunks before: %d, after: %d\n", len(chunks), len(filteredResult))

	return filteredResult, nil
}

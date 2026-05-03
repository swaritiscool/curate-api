package handler

import (
	"encoding/json"
	"net/http"
	"os"
)

func HealthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	
	model := os.Getenv("MODEL_TASKS")
	if model == "" {
		model = "llama3.3:70b"
	}

	resp := map[string]string{
		"status":  "ok",
		"model":   model,
		"version": "1.0.4",
	}

	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(resp)
}

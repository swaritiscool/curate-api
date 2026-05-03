package main

import (
	"log"
	"net/http"

	"github.com/your-org/curate-ai/api"
)

func main() {
	// Map the routes to the handlers in the prod/api package
	http.HandleFunc("/v1/transform", handler.TransformHandler)
	http.HandleFunc("/v1/health", handler.HealthHandler)

	log.Println("Curate.ai Go Port starting on http://localhost:8000")
	log.Println("Endpoints:")
	log.Println("  POST /v1/transform")
	log.Println("  GET  /v1/health")
	
	if err := http.ListenAndServe(":8000", nil); err != nil {
		log.Fatalf("Server failed to start: %v", err)
	}
}

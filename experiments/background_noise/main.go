// Package main generates background noise/load for SGLang to simulate
// a real-world agentic serving environment with concurrent requests.
//
// Usage:
//
//	go run . --backend http://localhost:30000 --rate 2
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"math/rand"
	"net/http"
	"os"
	"sync"
	"time"
)

func init() {
	log.SetOutput(os.Stderr)
	log.SetFlags(log.LstdFlags | log.Lmicroseconds)
}

func main() {
	backend := flag.String("backend", "http://localhost:30000", "SGLang backend URL")
	rate := flag.Float64("rate", 1.0, "Poisson arrival rate (requests per second, λ)")
	duration := flag.Duration("duration", 0, "Duration to run (0 = forever)")
	flag.Parse()

	// Create a simple client to send requests directly to SGLang
	// We'll use HTTP requests to the Ollama-compatible API
	client := &http.Client{Timeout: 30 * time.Second}

	ctx := context.Background()
	if *duration > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, *duration)
		defer cancel()
	}

	// Prompts to use for background noise
	prompts := []string{
		"What is the weather today?",
		"Explain quantum computing in simple terms.",
		"Write a haiku about programming.",
		"List 5 benefits of exercise.",
		"What is the capital of France?",
		"Describe the water cycle.",
		"Tell me a fun fact about space.",
		"What are the main components of a computer?",
	}

	fixedSeed := int64(42)

	// Initialize random number generator with fixed seed
	// Use mutex to protect RNG from concurrent access
	rng := rand.New(rand.NewSource(fixedSeed))
	var rngMu sync.Mutex

	log.Printf("Starting background noise generator: %.2f req/s (Poisson process), backend: %s", *rate, *backend)

	// Use Poisson process: inter-arrival times follow exponential distribution
	// For rate λ, mean inter-arrival time is 1/λ seconds
	// rand.ExpFloat64() returns exponential with rate 1, so divide by λ to get rate λ
	for {
		select {
		case <-ctx.Done():
			log.Printf("Background noise generator stopped")
			return
		default:
			// Generate next request immediately
			go func() {
				rngMu.Lock()
				prompt := prompts[rng.Intn(len(prompts))]
				rngMu.Unlock()
				err := sendNoiseRequest(client, *backend, prompt)
				if err != nil {
					log.Printf("Background request failed: %v", err)
				}
			}()

			// Calculate next inter-arrival time using exponential distribution
			// rand.ExpFloat64() has mean 1, so dividing by rate gives mean 1/rate
			rngMu.Lock()
			interArrivalTime := time.Duration(rng.ExpFloat64() / *rate * float64(time.Second))
			rngMu.Unlock()

			// Wait for the next arrival time
			select {
			case <-ctx.Done():
				log.Printf("Background noise generator stopped")
				return
			case <-time.After(interArrivalTime):
				// Continue to next iteration
			}
		}
	}
}

func sendNoiseRequest(client *http.Client, backend, prompt string) error {
	// Send a simple chat completion request to SGLang
	// SGLang uses Ollama-compatible API
	url := fmt.Sprintf("%s/api/chat", backend)

	reqBody := map[string]any{
		"model": "mistralai/Mistral-7B-Instruct-v0.3",
		"messages": []map[string]string{
			{"role": "user", "content": prompt},
		},
		"stream": false,
		"options": map[string]any{
			"num_predict": 20, // Short responses for noise
		},
	}

	jsonData, err := json.Marshal(reqBody)
	if err != nil {
		return fmt.Errorf("failed to marshal request: %w", err)
	}

	req, err := http.NewRequest("POST", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("unexpected status: %d", resp.StatusCode)
	}

	return nil
}

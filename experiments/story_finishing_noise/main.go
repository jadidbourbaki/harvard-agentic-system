// Story finishing experiment using Orla's agent API and vLLM.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"math/rand"
	"os"
	"path/filepath"
	"strings"
	"time"

	orla "github.com/dorcha-inc/orla/pkg/api"
	"github.com/harvard-agentic-system/pkg/dolly"
	"github.com/harvard-agentic-system/pkg/metrics"
)

const (
	orlaBackendName = "vllm"
	// vLLM endpoint as seen by the Orla container (docker compose service name).
	vllmEndpoint = "http://vllm:8000/v1"
	modelID      = "openai:mistralai/Mistral-7B-Instruct-v0.3"
)

var storyPromptTemplate = `We are playing a story finishing game. It is your turn. You are only allowed to give me the next %d tokens. You must give me exactly the next %d tokens to finish the story. The story starts as follows:

Once upon a time %s`

var dollyManager *dolly.InstructionsManager

func RunBackgroundNoiseAgent(ctx context.Context, agent *orla.Agent, rate float64, bg *metrics.AgentMetrics) {
	rng := rand.New(rand.NewSource(42))

	for {
		// Poisson inter-arrival: wait this long before *starting* the next request.
		interArrival := time.Duration(rng.ExpFloat64() / rate * float64(time.Second))

		select {
		case <-ctx.Done():
			log.Printf("Background noise agent context done")
			return
		case <-time.After(interArrival):
		}

		// Fire each request asynchronously
		go func() {
			prompt := dollyManager.RandomPrompt()
			start := time.Now()
			resp, err := agent.ExecuteStream(ctx, prompt)
			if err != nil {
				log.Fatalf("Background noise ExecuteStream: %v", err)
			}

			inferenceResp, err := agent.ConsumeStream(ctx, resp, nil)
			if err != nil {
				log.Fatalf("Background noise ConsumeStream: %v", err)
			}

			if inferenceResp.Metrics == nil {
				log.Fatalf("Background noise Metrics is nil, this should never happen")
			}

			elapsedMs := float64(time.Since(start).Milliseconds())
			bg.TTFTMilliseconds.AddSample(float64(inferenceResp.Metrics.TTFTMs), time.Now())
			bg.TPOTMilliseconds.AddSample(float64(inferenceResp.Metrics.TPOTMs), time.Now())
			bg.LatencyMilliseconds.AddSample(elapsedMs, time.Now())
		}()
	}
}

func main() {
	turns := flag.Int("turns", 20, "Number of turns")
	k := flag.Int("k", 32, "Tokens per turn")
	cacheStrategy := flag.String("cache-strategy", "preserve", "Cache strategy: 'flush' (unique prefix per turn to avoid vLLM prefix cache) or 'preserve'")
	noiseRate := flag.Float64("noise-rate", 0, "Background noise: Poisson rate (req/s); 0 = disabled. Uses Dolly 15K prompts.")
	orlaURL := flag.String("orla-url", "http://localhost:8081", "Orla daemon base URL")
	output := flag.String("output", "output/story_finishing/run.json", "Output JSON file (optional)")
	noiseMaxTokens := flag.Int("noise-max-tokens", 128, "Maximum tokens for background noise agent")
	flag.Parse()

	if *output == "" {
		log.Fatalf("output file is required")
	}

	if *cacheStrategy != "flush" && *cacheStrategy != "preserve" {
		log.Fatalf("cache-strategy must be 'flush' or 'preserve', got %q", *cacheStrategy)
	}

	if err := os.MkdirAll(filepath.Dir(*output), 0755); err != nil {
		log.Fatalf("create output dir: %v", err)
	}

	log.SetOutput(os.Stderr)
	log.Printf("Story finishing: turns=%d k=%d cache=%s noise-rate=%.2f orla=%s output=%s", *turns, *k, *cacheStrategy, *noiseRate, *orlaURL, *output)

	ctx := context.Background()
	client := orla.NewOrlaClient(*orlaURL)

	backend, err := client.RegisterBackend(ctx, &orla.RegisterBackendRequest{
		Name:     orlaBackendName,
		Endpoint: vllmEndpoint,
		Type:     "openai",
		ModelID:  modelID,
	})

	if err != nil {
		log.Fatalf("register backend: %v", err)
	}

	agent := orla.NewAgent(client, backend)
	agent.SetMaxTokens(*k)

	var noiseCancel context.CancelFunc
	agent3Metrics := metrics.NewAgentMetrics()

	if *noiseRate > 0 {
		log.Printf("Starting background noise agent: %.2f req/s (Poisson)", *noiseRate)
		log.Printf("Loading Dolly 15K prompts")

		dollyManager = dolly.NewInstructionsManager()
		err := dollyManager.LoadFromHuggingFace()
		if err != nil {
			log.Fatalf("load Dolly 15K prompts from Hugging Face: %v", err)
		}

		err = dollyManager.Validate()
		if err != nil {
			log.Fatalf("validate Dolly 15K prompts: %v", err)
		}

		noiseCtx, cancel := context.WithCancel(ctx)
		noiseCancel = cancel

		noiseAgent := orla.NewAgent(client, backend)
		noiseAgent.SetMaxTokens(*noiseMaxTokens)

		go RunBackgroundNoiseAgent(noiseCtx, noiseAgent, *noiseRate, agent3Metrics)
		log.Printf("Background noise agent started: %.2f req/s (Poisson), Dolly 15K prompts (third agent)", *noiseRate)
	}

	agent1Metrics := metrics.NewAgentMetrics()
	agent2Metrics := metrics.NewAgentMetrics()

	storyContext := ""
	startTotal := time.Now()

	for turn := 0; turn < *turns; turn++ {
		prompt := fmt.Sprintf(storyPromptTemplate, *k, *k, storyContext)

		if storyContext == "" {
			prompt = fmt.Sprintf(storyPromptTemplate, *k, *k, "")
		}

		// Add a unique prefix per turn to avoid vLLM prefix cache reuse.
		if *cacheStrategy == "flush" {
			prompt = fmt.Sprintf("Request %d.\n\n", turn) + prompt
		}

		turnStart := time.Now()
		resp, err := agent.ExecuteStream(ctx, prompt)

		if err != nil {
			log.Fatalf("turn %d execute stream: %v", turn+1, err)
		}

		inferenceResp, err := agent.ConsumeStream(ctx, resp, nil)
		if err != nil {
			log.Fatalf("turn %d consume stream: %v", turn+1, err)
		}

		if inferenceResp.Metrics == nil {
			log.Fatalf("turn %d metrics is nil", turn+1)
		}

		content := strings.TrimSpace(inferenceResp.Content)
		if content == "" {
			log.Fatalf("turn %d content is empty", turn+1)
		}

		if storyContext != "" {
			storyContext += " "
		}
		storyContext += content

		agentToAdd := agent1Metrics
		if turn%2 == 1 {
			agentToAdd = agent2Metrics
		}

		agentToAdd.TTFTMilliseconds.AddSample(float64(inferenceResp.Metrics.TTFTMs), time.Now())
		agentToAdd.TPOTMilliseconds.AddSample(float64(inferenceResp.Metrics.TPOTMs), time.Now())
		agentToAdd.LatencyMilliseconds.AddSample(float64(time.Since(turnStart).Milliseconds()), time.Now())

		log.Printf("[Turn %d/%d] +%q  ttft=%.1fms tpot=%.1fms", turn+1, *turns, content, float64(inferenceResp.Metrics.TTFTMs), float64(inferenceResp.Metrics.TPOTMs))
	}

	if noiseCancel != nil {
		noiseCancel()
	}

	totalTime := time.Since(startTotal)
	agent1 := map[string]any{
		"ttft_ms":    agent1Metrics.TTFTMilliseconds.Samples(),
		"tpot_ms":    agent1Metrics.TPOTMilliseconds.Samples(),
		"latency_ms": agent1Metrics.LatencyMilliseconds.Samples(),
	}
	agent2 := map[string]any{
		"ttft_ms":    agent2Metrics.TTFTMilliseconds.Samples(),
		"tpot_ms":    agent2Metrics.TPOTMilliseconds.Samples(),
		"latency_ms": agent2Metrics.LatencyMilliseconds.Samples(),
	}
	agent3 := map[string]any{
		"ttft_ms":    agent3Metrics.TTFTMilliseconds.Samples(),
		"tpot_ms":    agent3Metrics.TPOTMilliseconds.Samples(),
		"latency_ms": agent3Metrics.LatencyMilliseconds.Samples(),
	}

	results := map[string]any{
		"turns":              *turns,
		"k":                  *k,
		"cache_strategy":     *cacheStrategy,
		"noise_rate":         *noiseRate,
		"total_time_sec":     totalTime.Seconds(),
		"story_length_chars": len(storyContext),
		"story":              storyContext,
		"orla_url":           *orlaURL,
		"agents": map[string]any{
			"agent_1": agent1,
			"agent_2": agent2,
			"agent_3": agent3,
		},
	}

	jsonData, _ := json.MarshalIndent(results, "", "  ")
	if err := os.WriteFile(*output, jsonData, 0644); err != nil {
		log.Fatalf("write output: %v", err)
	}
	log.Printf("Results written to %s", *output)
}

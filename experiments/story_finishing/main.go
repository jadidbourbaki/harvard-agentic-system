// Package main runs story-finishing experiments using Orla.
//
// Usage:
//
//	go run . --policy preserve --turns 100 --k 8
//
// Supported policies: aggressive_flush, preserve, preserve_on_small_turns
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	orla "github.com/dorcha-inc/orla/pkg/api"
)

func init() {
	log.SetOutput(os.Stderr)
	log.SetFlags(log.LstdFlags | log.Lmicroseconds)
}

func main() {
	// kill all orla processes
	err := exec.Command("killall", "orla").Run()
	if err != nil {
		// Ignore error if no orla processes are running
		log.Printf("Note: No existing orla processes to kill (this is OK)")
	}

	policy := flag.String("policy", "aggressive_flush", "Cache policy")
	turns := flag.Int("turns", 100, "Number of turns")
	k := flag.Int("k", 8, "Tokens per turn")
	backend := flag.String("backend", "http://localhost:30000", "SGLang URL")
	model := flag.String("model", "mistralai/Mistral-7B-Instruct-v0.3", "Model name (will be prefixed with 'sglang:')")
	output := flag.String("output", "", "Output file (default: stdout)")
	smallTurnThreshold := flag.Int("small-turn-threshold", 100, "Token threshold for preserve_on_small_turns policy (default: 100)")
	flag.Parse()

	if *output != "" {
		if err := os.MkdirAll(filepath.Dir(*output), 0755); err != nil {
			log.Fatalf("Failed to create output directory: %v", err)
		}
	}

	// Create temp config
	// Format model identifier as "sglang:model-name" (required by Orla)
	modelID := *model
	if !strings.Contains(modelID, ":") {
		modelID = "sglang:" + modelID
	}

	log.Printf("Running story finishing experiment with policy %s, turns %d, k %d, backend %s, model %s", *policy, *turns, *k, *backend, *model)
	log.Printf("Output will be saved to %s", *output)
	// Determine config file location - use outputs directory if output is specified, otherwise current directory
	var configFile string
	if *output != "" {
		outputDir := filepath.Dir(*output)
		configFile = filepath.Join(outputDir, fmt.Sprintf("orla_exp_%d.yaml", time.Now().Unix()))
	} else {
		configFile = fmt.Sprintf("orla_exp_%d.yaml", time.Now().Unix())
	}

	log.Printf("Creating config file %s", configFile)

	configErr := createConfig(configFile, *policy, *turns, *backend, modelID, *smallTurnThreshold)
	if configErr != nil {
		log.Fatalf("Failed to create config: %v", configErr)
	}
	// Keep the config file for debugging/reference

	log.Printf("Config file created")

	// Check if SGLang server is running
	log.Printf("Checking if SGLang server is running at %s...", *backend)

	sgLangReadyErr := checkSGLangReady(*backend)
	if sgLangReadyErr != nil {
		log.Fatalf("Failed to check SGLang server: %v", sgLangReadyErr)
	}

	log.Printf("SGLang server is running")

	log.Printf("Starting Orla daemon...")
	// Create log file for daemon output - use outputs directory if output is specified
	var logFile string
	if *output != "" {
		outputDir := filepath.Dir(*output)
		logFile = filepath.Join(outputDir, fmt.Sprintf("orla_exp_%d_daemon.log", time.Now().Unix()))
	} else {
		logFile = fmt.Sprintf("orla_exp_%d_daemon.log", time.Now().Unix())
	}

	daemonLog, err := os.Create(logFile)
	if err != nil {
		log.Fatalf("Failed to create daemon log file: %v", err)
	}
	defer daemonLog.Close()

	log.Printf("Orla daemon logs will be written to %s", logFile)

	// Start Orla daemon
	cmd := exec.Command("orla", "daemon", "--config", configFile)
	cmd.Stdout = daemonLog
	cmd.Stderr = daemonLog
	startErr := cmd.Start()
	if startErr != nil {
		log.Fatalf("Failed to start Orla: %v", startErr)
	}
	defer cmd.Process.Kill()

	log.Printf("Orla daemon started at http://localhost:8081")

	// Wait for daemon
	time.Sleep(2 * time.Second)

	log.Printf("Running experiment...")
	// Run experiment
	ctx := context.Background()
	results, err := runExperiment(ctx, "http://localhost:8081", "story_finishing_game", *turns, *k)
	if err != nil {
		log.Fatalf("Experiment failed: %v", err)
	}

	// Output
	jsonData, jsonErr := json.MarshalIndent(results, "", "  ")
	if jsonErr != nil {
		log.Fatalf("Failed to marshal results: %v", jsonErr)
	}

	log.Printf("Experiment completed successfully")

	if *output != "" {
		writeErr := os.WriteFile(*output, jsonData, 0644)
		if writeErr != nil {
			log.Fatalf("Failed to write results to file: %v", writeErr)
		}
		log.Printf("Results written to %s", *output)
		return
	}

	log.Printf("Results: %v", results)
}

func createConfig(path string, policy string, turns int, backend string, model string, smallTurnThreshold int) error {
	var config strings.Builder
	fmt.Fprintf(&config, `log_format: pretty
log_level: debug
agentic_serving:
mode: daemon
daemon:
listen_address: "localhost:8081"
llm_servers:
- name: "sglang_shared"
  backend:
	type: "sglang"
	endpoint: "%s"
  model: "%s"
  context:
	shared: true
  cache:
	policy: "%s"
`, backend, model, policy)

	// Add small_turn_threshold if using preserve_on_small_turns policy
	if policy == "preserve_on_small_turns" {
		fmt.Fprintf(&config, "        small_turn_threshold: %d\n", smallTurnThreshold)
	}

	fmt.Fprintf(&config, `  agent_profiles:
- name: "story_agent_a"
  llm_server: "sglang_shared"
- name: "story_agent_b"
  llm_server: "sglang_shared"
workflows:
- name: "story_finishing_game"
  tasks:
`)

	for i := 0; i < turns; i++ {
		agent := "story_agent_a"

		if i%2 == 1 {
			agent = "story_agent_b"
		}

		fmt.Fprintf(&config, "        - agent_profile: %s\n", agent)
	}

	return os.WriteFile(path, []byte(config.String()), 0644)
}

func checkSGLangReady(backendURL string) error {
	// Try to connect to SGLang's health endpoint or a simple API endpoint
	// SGLang uses Ollama-compatible API, so we can check /api/tags or /api/version
	client := &http.Client{Timeout: 3 * time.Second}

	// Try multiple endpoints - SGLang might have different endpoints available
	// /model_info is known to work based on SGLang logs
	endpoints := []string{"/model_info", "/api/tags", "/api/version", "/health"}

	var lastErr error
	for _, endpoint := range endpoints {
		resp, err := client.Get(backendURL + endpoint)
		if err == nil {
			resp.Body.Close()
			// Any HTTP response (even 404 or 405) means the server is reachable
			// We just need to confirm the server is listening
			return nil
		}
		lastErr = err
	}

	// If all endpoints failed, return the last error with more context
	if lastErr != nil {
		return fmt.Errorf("cannot connect to SGLang server at %s: %v (is SGLang running in Docker?)", backendURL, lastErr)
	}
	return fmt.Errorf("SGLang server at %s is not responding", backendURL)
}

// runExperiment executes the story finishing workflow using the Orla public API.
// It uses the low-level Client API directly since we need custom prompt construction
// that builds up the story context incrementally each turn.
func runExperiment(ctx context.Context, orlaURL, workflow string, turns, k int) (map[string]interface{}, error) {
	// Create client using the public API
	client := orla.NewClient(orlaURL)

	// Start workflow
	execID, err := client.StartWorkflow(ctx, workflow)
	if err != nil {
		return nil, fmt.Errorf("failed to start workflow: %w", err)
	}

	var storyContext string
	var metrics []map[string]any
	start := time.Now()

	for turn := 1; turn <= turns; turn++ {
		// Get next task
		_, taskIndex, complete, _, err := client.GetNextTask(ctx, execID)
		if err != nil {
			return nil, fmt.Errorf("failed to get next task: %w", err)
		}

		if complete {
			break
		}

		// Construct prompt for this turn with accumulated context
		prompt := constructPrompt(storyContext, k)

		// Execute task (this advances CurrentTaskIndex internally)
		turnStart := time.Now()
		response, err := client.ExecuteTask(ctx, execID, taskIndex, prompt, k)
		if err != nil {
			return nil, fmt.Errorf("failed to execute task %d: %w", taskIndex, err)
		}
		duration := time.Since(turnStart)

		content := response.Content
		storyContext += " " + content

		// Log the story continuation for this turn
		log.Printf("Turn %d: %.1fms - Story continuation: %s", turn, float64(duration.Milliseconds()), content)

		metrics = append(metrics, map[string]any{
			"turn":             turn,
			"total_time_ms":    float64(duration.Milliseconds()),
			"context_size":     len(storyContext),
			"tokens_generated": len(content) / 4,
			"content":          content,
		})

		// Get the updated task index after ExecuteTask (which advances CurrentTaskIndex)
		_, updatedTaskIndex, _, _, err := client.GetNextTask(ctx, execID)
		if err != nil {
			return nil, fmt.Errorf("failed to get updated task index: %w", err)
		}

		// Complete task with the updated index
		if err := client.CompleteTask(ctx, execID, updatedTaskIndex, response); err != nil {
			return nil, fmt.Errorf("failed to complete task %d: %w", updatedTaskIndex, err)
		}
	}

	var avgTime float64
	if len(metrics) > 1 {
		var sum float64
		for _, m := range metrics[1:] {
			sum += m["total_time_ms"].(float64)
		}
		avgTime = sum / float64(len(metrics)-1)
	}

	return map[string]any{
		"turns":              len(metrics),
		"k":                  k,
		"total_time_seconds": time.Since(start).Seconds(),
		"avg_turn_time_ms":   avgTime,
		"per_turn_metrics":   metrics,
		"final_story":        storyContext,
		"machine_info": map[string]any{
			"os":      runtime.GOOS,
			"arch":    runtime.GOARCH,
			"num_cpu": runtime.NumCPU(),
		},
	}, nil
}

func constructPrompt(context string, c int) string {
	return fmt.Sprintf(`We are playing a story finishing game. It is your turn. You are only 
allowed to give me the next %d tokens. You must give me exactly the next %d 
tokens to finish the story. The story starts as follows:

Once upon a time %s`, c, c, context)
}

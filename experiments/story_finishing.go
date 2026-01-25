// Package main runs story-finishing experiments using Orla.
//
// Usage:
//
//	go run . --policy preserve --turns 100 --k 8
package main

import (
	"bytes"
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
)

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

	configFile := filepath.Join(os.TempDir(), fmt.Sprintf("orla_exp_%d.yaml", time.Now().Unix()))

	log.Printf("Creating config file %s", configFile)

	configErr := createConfig(configFile, *policy, *turns, *backend, modelID)
	if configErr != nil {
		log.Fatalf("Failed to create config: %v", configErr)
	}
	defer os.Remove(configFile)

	log.Printf("Config file created")

	// Check if SGLang server is running
	log.Printf("Checking if SGLang server is running at %s...", *backend)

	sgLangReadyErr := checkSGLangReady(*backend)
	if sgLangReadyErr != nil {
		log.Fatalf("Failed to check SGLang server: %v", sgLangReadyErr)
	}

	log.Printf("SGLang server is running")

	log.Printf("Starting Orla daemon...")
	// Start Orla daemon
	cmd := exec.Command("orla", "daemon", "--config", configFile)
	cmd.Stdout = os.Stderr
	cmd.Stderr = os.Stderr
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
	results, err := runExperiment("http://localhost:8081", "story_finishing_game", *turns, *k)
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

func createConfig(path, policy string, turns int, backend, model string) error {
	var config strings.Builder
	fmt.Fprintf(&config, `agentic_serving:
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
  agent_profiles:
    - name: "story_agent_a"
      llm_server: "sglang_shared"
    - name: "story_agent_b"
      llm_server: "sglang_shared"
  workflows:
    - name: "story_finishing_game"
      tasks:
`, backend, model, policy)

	for i := range turns {
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

func runExperiment(orlaURL, workflow string, turns, k int) (map[string]interface{}, error) {
	// Start workflow
	execID, err := httpPost(orlaURL+"/api/v1/workflow/start", map[string]string{"workflow_name": workflow})
	if err != nil {
		return nil, err
	}
	execIDStr := execID["execution_id"].(string)

	var context string
	var metrics []map[string]any
	start := time.Now()

	for turnIterator := range turns {
		turn := turnIterator + 1

		// Get next task
		task, err := httpGet(fmt.Sprintf("%s/api/v1/workflow/task/next?execution_id=%s", orlaURL, execIDStr))
		if err != nil {
			return nil, fmt.Errorf("failed to get next task: %w", err)
		}

		if task["complete"].(bool) {
			break
		}

		taskIndex := int(task["task_index"].(float64))

		// Execute task
		prompt := constructPrompt(context, k)

		turnStart := time.Now()
		resp, err := httpPost(orlaURL+"/api/v1/workflow/task/execute", map[string]any{
			"execution_id": execIDStr,
			"task_index":   taskIndex,
			"prompt":       prompt,
		})

		if err != nil {
			return nil, fmt.Errorf("failed to execute task %d: %w", taskIndex, err)
		}
		duration := time.Since(turnStart)

		// Check API response structure: {success: bool, response: {content: string}, error: string}
		success, ok := resp["success"].(bool)
		if !ok || !success {
			errorMsg, ok := resp["error"].(string)
			if !ok {
				return nil, fmt.Errorf("invalid API response for task %d: missing 'error' field. Full response: %+v", taskIndex, resp)
			}
			return nil, fmt.Errorf("task %d execution failed: %s", taskIndex, errorMsg)
		}

		responseObj, ok := resp["response"]
		if !ok || responseObj == nil {
			return nil, fmt.Errorf("invalid API response for task %d: missing 'response' field. Full response: %+v", taskIndex, resp)
		}

		responseMap, ok := responseObj.(map[string]interface{})
		if !ok {
			return nil, fmt.Errorf("invalid API response for task %d: 'response' is not a map. Got: %T, Value: %+v", taskIndex, responseObj, responseObj)
		}

		contentObj, ok := responseMap["content"]
		if !ok || contentObj == nil {
			return nil, fmt.Errorf("invalid API response for task %d: missing 'content' field. Response: %+v", taskIndex, responseMap)
		}

		content, ok := contentObj.(string)
		if !ok {
			return nil, fmt.Errorf("invalid API response for task %d: 'content' is not a string. Got: %T, Value: %+v", taskIndex, contentObj, contentObj)
		}

		context += " " + content

		metrics = append(metrics, map[string]any{
			"turn":             turn,
			"total_time_ms":    float64(duration.Milliseconds()),
			"context_size":     len(context),
			"tokens_generated": len(content) / 4,
		})

		log.Printf("Turn %d: %.1fms", turn, float64(duration.Milliseconds()))
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
		"machine_info": map[string]any{
			"os":      runtime.GOOS,
			"arch":    runtime.GOARCH,
			"num_cpu": runtime.NumCPU(),
		},
	}, nil
}

func httpPost(url string, body any) (map[string]any, error) {
	jsonData, _ := json.Marshal(body)
	resp, err := http.Post(url, "application/json", bytes.NewReader(jsonData))
	if err != nil {
		return nil, fmt.Errorf("HTTP POST failed: %w", err)
	}
	defer resp.Body.Close()

	bodyBytes := &bytes.Buffer{}
	bodyBytes.ReadFrom(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("HTTP error %d: %s", resp.StatusCode, bodyBytes.String())
	}

	var result map[string]any
	if err := json.Unmarshal(bodyBytes.Bytes(), &result); err != nil {
		return nil, fmt.Errorf("failed to decode JSON response: %w", err)
	}
	return result, nil
}

func httpGet(url string) (map[string]any, error) {
	resp, err := http.Get(url)
	if err != nil {
		return nil, fmt.Errorf("HTTP GET failed: %w", err)
	}
	defer resp.Body.Close()

	bodyBytes := &bytes.Buffer{}
	bodyBytes.ReadFrom(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("HTTP error %d: %s", resp.StatusCode, bodyBytes.String())
	}

	var result map[string]any
	if err := json.Unmarshal(bodyBytes.Bytes(), &result); err != nil {
		return nil, fmt.Errorf("failed to decode JSON response: %w", err)
	}
	return result, nil
}

func constructPrompt(context string, c int) string {
	return fmt.Sprintf(`We are playing a story finishing game. It is your turn. You are only 
allowed to give me the next %d tokens. You must give me exactly the next %d 
tokens to finish the story. The story starts as follows:

Once upon a time %s`, c, c, context)
}

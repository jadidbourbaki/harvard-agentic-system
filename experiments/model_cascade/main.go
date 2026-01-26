// Package main runs a model cascade experiment demonstrating Orla's ability
// to route different tasks to different models based on intent.
//
// This experiment uses a SWE-Bench-inspired workflow with 3 stages:
// - Issue Analysis: Understand the problem (small model in cascade mode)
// - Code Generation: Fix the code (large model)
// - Summary: Summarize the fix (small model in cascade mode)
//
// Baseline: Always uses large model (Mistral-7B) for all tasks
// Orla cascade: Uses small model (Qwen2.5-0.5B) for analysis/summary, large model for code generation
//
// Usage:
//
//	go run . --mode baseline --backend http://localhost:30000
//	go run . --mode cascade --backend-small http://localhost:30001 --backend-large http://localhost:30000
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
	"strings"
	"time"

	orla "github.com/dorcha-inc/orla/pkg/api"
)

func init() {
	log.SetOutput(os.Stderr)
	log.SetFlags(log.LstdFlags | log.Lmicroseconds)
}

func main() {
	// Kill all orla processes
	if killErr := exec.Command("killall", "orla").Run(); killErr != nil {
		log.Printf("Note: No existing orla processes to kill (this is OK)")
	}

	mode := flag.String("mode", "baseline", "Experiment mode: 'baseline' (SGLang), 'cascade' (SGLang), 'baseline-ollama' (Ollama), or 'cascade-ollama' (Ollama)")
	backendLarge := flag.String("backend-large", "http://localhost:30000", "SGLang URL for large model (Mistral-7B)")
	backendSmall := flag.String("backend-small", "http://localhost:30001", "SGLang URL for small model (Qwen2.5-0.5B)")
	backendOllama := flag.String("backend-ollama", "http://localhost:11434", "Ollama URL (used for both models in Ollama variants)")
	output := flag.String("output", "", "Output file (default: stdout)")
	numTasks := flag.Int("num-tasks", 20, "Number of tasks to process")
	flag.Parse()

	if *output != "" {
		if err := os.MkdirAll(filepath.Dir(*output), 0755); err != nil {
			log.Fatalf("Failed to create output directory: %v", err)
		}
	}

	log.Printf("Running model cascade experiment: mode=%s, num_tasks=%d", *mode, *numTasks)

	// Create config
	var configFile string
	if *output != "" {
		outputDir := filepath.Dir(*output)
		configFile = filepath.Join(outputDir, fmt.Sprintf("orla_cascade_%d.yaml", time.Now().Unix()))
	} else {
		configFile = fmt.Sprintf("orla_cascade_%d.yaml", time.Now().Unix())
	}

	var configErr error
	switch *mode {
	case "cascade":
		configErr = createCascadeConfig(configFile, *backendSmall, *backendLarge)
	case "baseline-ollama":
		configErr = createOllamaBaselineConfig(configFile, *backendOllama)
	case "cascade-ollama":
		configErr = createOllamaCascadeConfig(configFile, *backendOllama)
	default:
		configErr = createBaselineConfig(configFile, *backendLarge)
	}

	if configErr != nil {
		log.Fatalf("Failed to create config: %v", configErr)
	}

	// Verify backends are ready
	log.Printf("Verifying backends are ready...")
	switch *mode {
	case "cascade":
		if err := checkBackendReady(*backendSmall); err != nil {
			log.Fatalf("Small model backend (%s) is not ready: %v", *backendSmall, err)
		}
		log.Printf("Small model backend ready: %s", *backendSmall)
		if err := checkBackendReady(*backendLarge); err != nil {
			log.Fatalf("Large model backend (%s) is not ready: %v", *backendLarge, err)
		}
		log.Printf("Large model backend ready: %s", *backendLarge)
	case "baseline-ollama", "cascade-ollama":
		if err := checkBackendReady(*backendOllama); err != nil {
			log.Fatalf("Ollama backend (%s) is not ready: %v", *backendOllama, err)
		}
		log.Printf("Ollama backend ready: %s", *backendOllama)
	default:
		if err := checkBackendReady(*backendLarge); err != nil {
			log.Fatalf("Large model backend (%s) is not ready: %v", *backendLarge, err)
		}
		log.Printf("Large model backend ready: %s", *backendLarge)
	}

	// Start Orla daemon
	log.Printf("Starting Orla daemon...")
	var logFile string
	if *output != "" {
		outputDir := filepath.Dir(*output)
		logFile = filepath.Join(outputDir, fmt.Sprintf("orla_cascade_%s_%d.log", *mode, time.Now().Unix()))
	} else {
		logFile = fmt.Sprintf("orla_cascade_%s_%d.log", *mode, time.Now().Unix())
	}

	daemonLog, err := os.Create(logFile)
	if err != nil {
		log.Fatalf("Failed to create daemon log file: %v", err)
	}
	defer daemonLog.Close()

	cmd := exec.Command("orla", "daemon", "--config", configFile)
	cmd.Stdout = daemonLog
	cmd.Stderr = daemonLog
	if startErr := cmd.Start(); startErr != nil {
		log.Fatalf("Failed to start Orla: %v", startErr)
	}
	defer func() {
		if cmd.Process != nil {
			cmd.Process.Kill()
		}
	}()

	// Monitor process exit in background
	processExited := make(chan error, 1)
	go func() {
		processExited <- cmd.Wait()
	}()

	// Wait for Orla to be ready
	orlaURL := "http://localhost:8081"
	log.Printf("Waiting for Orla daemon to be ready...")
	maxWait := 60 * time.Second
	checkInterval := 500 * time.Millisecond
	waited := 0 * time.Second
	for {
		// Check if process exited
		select {
		case err := <-processExited:
			log.Printf("Orla daemon process exited unexpectedly (exit code: %v)", err)
			displayLogTail(logFile)
			log.Fatalf("Orla daemon process exited. Check full logs at: %s", logFile)
		default:
			// Process still running, continue
		}

		if err := checkOrlaReady(orlaURL); err == nil {
			log.Printf("Orla daemon is ready (waited %.1fs)", waited.Seconds())
			break
		}

		if waited >= maxWait {
			log.Printf("Orla daemon process is still running but not responding")
			displayLogTail(logFile)
			log.Fatalf("Orla daemon did not become ready within %v. Check full logs at: %s", maxWait, logFile)
		}
		time.Sleep(checkInterval)
		waited += checkInterval
	}

	// Run experiment
	ctx := context.Background()
	results, err := runExperiment(ctx, orlaURL, *mode, *numTasks)
	if err != nil {
		log.Fatalf("Experiment failed: %v", err)
	}

	// Output results
	jsonData, jsonErr := json.MarshalIndent(results, "", "  ")
	if jsonErr != nil {
		log.Fatalf("Failed to marshal results: %v", jsonErr)
	}

	if *output != "" {
		if writeErr := os.WriteFile(*output, jsonData, 0644); writeErr != nil {
			log.Fatalf("Failed to write results to file: %v", writeErr)
		}
		log.Printf("Results written to %s", *output)
	} else {
		log.Printf("Results: %s", string(jsonData))
	}
}

func createBaselineConfig(path string, backendLarge string) error {
	config := fmt.Sprintf(`log_format: pretty
log_level: info
agentic_serving:
  mode: daemon
  daemon:
    listen_address: "localhost:8081"
  llm_servers:
    - name: "large_model"
      backend:
        type: "sglang"
        endpoint: "%s"
      model: "sglang:mistralai/Mistral-7B-Instruct-v0.3"
  agent_profiles:
    - name: "router"
      llm_server: "large_model"
    - name: "synthesizer"
      llm_server: "large_model"
    - name: "summarizer"
      llm_server: "large_model"
  workflows:
    - name: "task_processor"
      tasks:
        - agent_profile: "router"
        - agent_profile: "synthesizer"
        - agent_profile: "summarizer"
`, backendLarge)

	return os.WriteFile(path, []byte(config), 0644)
}

func createCascadeConfig(path string, backendSmall string, backendLarge string) error {
	config := fmt.Sprintf(`log_format: pretty
log_level: info
agentic_serving:
  mode: daemon
  daemon:
    listen_address: "localhost:8081"
  llm_servers:
    - name: "small_model"
      backend:
        type: "sglang"
        endpoint: "%s"
      model: "sglang:Qwen/Qwen2.5-0.5B-Instruct"
    - name: "large_model"
      backend:
        type: "sglang"
        endpoint: "%s"
      model: "sglang:mistralai/Mistral-7B-Instruct-v0.3"
  agent_profiles:
    - name: "router"
      llm_server: "small_model"
    - name: "synthesizer"
      llm_server: "large_model"
    - name: "summarizer"
      llm_server: "small_model"
  workflows:
    - name: "task_processor"
      tasks:
        - agent_profile: "router"
        - agent_profile: "synthesizer"
        - agent_profile: "summarizer"
`, backendSmall, backendLarge)

	return os.WriteFile(path, []byte(config), 0644)
}

func createOllamaBaselineConfig(path string, backendOllama string) error {
	config := fmt.Sprintf(`log_format: pretty
log_level: info
agentic_serving:
  mode: daemon
  daemon:
    listen_address: "localhost:8081"
  llm_servers:
    - name: "large_model"
      backend:
        type: "ollama"
        endpoint: "%s"
      model: "ollama:mistral:7b-instruct"
  agent_profiles:
    - name: "router"
      llm_server: "large_model"
    - name: "synthesizer"
      llm_server: "large_model"
    - name: "summarizer"
      llm_server: "large_model"
  workflows:
    - name: "task_processor"
      tasks:
        - agent_profile: "router"
        - agent_profile: "synthesizer"
        - agent_profile: "summarizer"
`, backendOllama)

	return os.WriteFile(path, []byte(config), 0644)
}

func createOllamaCascadeConfig(path string, backendOllama string) error {
	config := fmt.Sprintf(`log_format: pretty
log_level: info
agentic_serving:
  mode: daemon
  daemon:
    listen_address: "localhost:8081"
  llm_servers:
    - name: "small_model"
      backend:
        type: "ollama"
        endpoint: "%s"
      model: "ollama:qwen2.5:0.5b-instruct"
    - name: "large_model"
      backend:
        type: "ollama"
        endpoint: "%s"
      model: "ollama:mistral:7b-instruct"
  agent_profiles:
    - name: "router"
      llm_server: "small_model"
    - name: "synthesizer"
      llm_server: "large_model"
    - name: "summarizer"
      llm_server: "small_model"
  workflows:
    - name: "task_processor"
      tasks:
        - agent_profile: "router"
        - agent_profile: "synthesizer"
        - agent_profile: "summarizer"
`, backendOllama, backendOllama)

	return os.WriteFile(path, []byte(config), 0644)
}

func runExperiment(ctx context.Context, orlaURL string, mode string, numTasks int) (map[string]interface{}, error) {
	client := orla.NewClient(orlaURL)

	// SWE-Bench inspired issues: realistic software engineering tasks
	type Task struct {
		Issue string
		Code  string
	}
	tasks := []Task{
		{
			Issue: "The `validate_email` function incorrectly accepts emails with consecutive dots (e.g., 'user..name@example.com'). Please fix the validation logic.",
			Code:  "def validate_email(email):\n    return '@' in email and '.' in email.split('@')[1]",
		},
		{
			Issue: "The API endpoint `/api/users/{id}` returns 500 error when user ID is not found. It should return 404 with a proper error message instead.",
			Code:  "def get_user(user_id):\n    user = db.query(User).filter(User.id == user_id).first()\n    return user.to_dict()",
		},
		{
			Issue: "The `calculate_total` function doesn't handle negative prices correctly. Negative prices should be treated as discounts and subtracted from the total.",
			Code:  "def calculate_total(items):\n    return sum(item['price'] for item in items)",
		},
		{
			Issue: "The `parse_date` function fails when given dates in 'YYYY-MM-DD' format. Add support for this ISO 8601 format.",
			Code:  "def parse_date(date_str):\n    return datetime.strptime(date_str, '%m/%d/%Y')",
		},
		{
			Issue: "The `find_duplicates` function has O(n²) time complexity. Optimize it to use a hash set for O(n) performance.",
			Code:  "def find_duplicates(arr):\n    duplicates = []\n    for i in range(len(arr)):\n        for j in range(i+1, len(arr)):\n            if arr[i] == arr[j]:\n                duplicates.append(arr[i])\n    return duplicates",
		},
		{
			Issue: "The `sanitize_input` function doesn't escape HTML special characters. This creates an XSS vulnerability. Please fix it.",
			Code:  "def sanitize_input(text):\n    return text.strip()",
		},
		{
			Issue: "The `merge_dicts` function overwrites values when keys conflict. It should merge nested dictionaries recursively instead.",
			Code:  "def merge_dicts(dict1, dict2):\n    result = dict1.copy()\n    result.update(dict2)\n    return result",
		},
		{
			Issue: "The `format_currency` function doesn't handle negative amounts correctly. Negative amounts should be formatted with parentheses: (USD 100.00).",
			Code:  "def format_currency(amount, currency='USD'):\n    return f'{currency} {amount:.2f}'",
		},
		{
			Issue: "The `validate_password` function only checks length. Add checks for: at least one uppercase letter, one lowercase letter, one digit, and one special character.",
			Code:  "def validate_password(password):\n    return len(password) >= 8",
		},
		{
			Issue: "The `retry_request` function doesn't implement exponential backoff. Add exponential backoff with jitter to prevent thundering herd problems.",
			Code:  "def retry_request(url, max_retries=3):\n    for i in range(max_retries):\n        try:\n            return requests.get(url)\n        except:\n            time.sleep(1)\n    raise Exception('Max retries exceeded')",
		},
		{
			Issue: "The `parse_csv` function fails when CSV contains quoted fields with commas. Add proper CSV parsing that handles quoted fields.",
			Code:  "def parse_csv(csv_text):\n    return [line.split(',') for line in csv_text.split('\\n')]",
		},
		{
			Issue: "The `calculate_age` function gives incorrect results for leap year birthdays. Fix the date calculation to handle leap years correctly.",
			Code:  "def calculate_age(birth_date):\n    today = datetime.now()\n    return (today - birth_date).days // 365",
		},
		{
			Issue: "The `sort_by_key` function doesn't handle None values. None values should be sorted to the end of the list.",
			Code:  "def sort_by_key(items, key_func):\n    return sorted(items, key=key_func)",
		},
		{
			Issue: "The `truncate_string` function cuts words in the middle. Modify it to truncate at word boundaries and add ellipsis.",
			Code:  "def truncate_string(text, max_length):\n    return text[:max_length]",
		},
		{
			Issue: "The `find_missing_numbers` function has O(n²) complexity. Optimize it to find all missing numbers in range [1, n] in O(n) time.",
			Code:  "def find_missing_numbers(arr, n):\n    missing = []\n    for i in range(1, n+1):\n        if i not in arr:\n            missing.append(i)\n    return missing",
		},
		{
			Issue: "The `normalize_path` function doesn't handle '..' and '.' correctly. Implement proper path normalization that resolves parent and current directory references.",
			Code:  "def normalize_path(path):\n    return path.replace('\\\\', '/')",
		},
		{
			Issue: "The `batch_process` function processes all items in memory at once. Refactor it to process items in chunks to reduce memory usage.",
			Code:  "def batch_process(items, process_func):\n    return [process_func(item) for item in items]",
		},
		{
			Issue: "The `validate_url` function accepts invalid URLs like 'http://' or 'not-a-url'. Add proper URL validation using regex or a URL parsing library.",
			Code:  "def validate_url(url):\n    return url.startswith('http://') or url.startswith('https://')",
		},
		{
			Issue: "The `format_phone_number` function doesn't handle international formats. Add support for formatting phone numbers in E.164 format (+1234567890).",
			Code:  "def format_phone_number(phone):\n    return f'({phone[:3]}) {phone[3:6]}-{phone[6:]}'",
		},
		{
			Issue: "The `calculate_median` function has O(n log n) complexity due to sorting. Use a selection algorithm to achieve O(n) average case complexity.",
			Code:  "def calculate_median(numbers):\n    sorted_nums = sorted(numbers)\n    mid = len(sorted_nums) // 2\n    return sorted_nums[mid]",
		},
	}

	var totalTime time.Duration
	var analysisTimes []float64
	var synthesisTimes []float64
	var summaryTimes []float64
	var totalTimes []float64

	startTime := time.Now()

	for i := 0; i < numTasks && i < len(tasks); i++ {
		task := tasks[i%len(tasks)]
		log.Printf("[Task %d/%d] Processing issue: %s", i+1, numTasks, task.Issue)

		// Start workflow
		execID, err := client.StartWorkflow(ctx, "task_processor")
		if err != nil {
			return nil, fmt.Errorf("failed to start workflow: %w", err)
		}

		taskStart := time.Now()

		// Task 1: Issue Analysis (uses small model in cascade mode)
		_, taskIndex1, complete, _, err := client.GetNextTask(ctx, execID)
		if err != nil {
			return nil, fmt.Errorf("failed to get analysis task: %w", err)
		}
		if complete {
			break
		}

		analysisStart := time.Now()
		prompt1 := fmt.Sprintf("Analyze this software engineering issue and identify the problem:\n\nIssue: %s\n\nCurrent code:\n```python\n%s\n```\n\nProvide a brief analysis: what is the problem, what needs to be fixed, and what approach should be taken?", task.Issue, task.Code)
		// Use a longer timeout for inference tasks (2 minutes should be enough for small models)
		taskCtx, cancel := context.WithTimeout(ctx, 2*time.Minute)
		_, err = client.ExecuteTask(taskCtx, execID, taskIndex1, prompt1, 50)
		cancel()
		if err != nil {
			return nil, fmt.Errorf("failed to execute analysis task: %w", err)
		}
		analysisTime := time.Since(analysisStart)
		analysisTimes = append(analysisTimes, float64(analysisTime.Milliseconds()))

		// Task 2: Code Generation (uses large model)
		_, taskIndex2, complete, _, err := client.GetNextTask(ctx, execID)
		if err != nil {
			return nil, fmt.Errorf("failed to get synthesis task: %w", err)
		}
		if complete {
			break
		}

		synthesisStart := time.Now()
		prompt2 := fmt.Sprintf("Based on the analysis, generate the fixed code for this issue:\n\nIssue: %s\n\nOriginal code:\n```python\n%s\n```\n\nProvide the complete fixed function with proper error handling and edge cases.", task.Issue, task.Code)
		// Use a longer timeout for code generation (3 minutes for large models, especially Ollama which can be slower)
		taskCtx, cancel := context.WithTimeout(ctx, 3*time.Minute)
		_, err = client.ExecuteTask(taskCtx, execID, taskIndex2, prompt2, 150)
		cancel()
		if err != nil {
			return nil, fmt.Errorf("failed to execute synthesis task: %w", err)
		}
		synthesisTime := time.Since(synthesisStart)
		synthesisTimes = append(synthesisTimes, float64(synthesisTime.Milliseconds()))

		// Task 3: Summary (uses small model in cascade mode)
		_, taskIndex3, complete, _, err := client.GetNextTask(ctx, execID)
		if err != nil {
			return nil, fmt.Errorf("failed to get summary task: %w", err)
		}
		if complete {
			break
		}

		summaryStart := time.Now()
		prompt3 := fmt.Sprintf("Summarize the fix that was applied to resolve this issue in 2-3 sentences:\n\nIssue: %s", task.Issue)
		// Use a longer timeout for inference tasks (2 minutes should be enough for small models)
		taskCtx, cancel := context.WithTimeout(ctx, 2*time.Minute)
		_, err = client.ExecuteTask(taskCtx, execID, taskIndex3, prompt3, 30)
		cancel()
		if err != nil {
			return nil, fmt.Errorf("failed to execute summary task: %w", err)
		}
		summaryTime := time.Since(summaryStart)
		summaryTimes = append(summaryTimes, float64(summaryTime.Milliseconds()))

		taskTime := time.Since(taskStart)
		totalTimes = append(totalTimes, float64(taskTime.Milliseconds()))

		log.Printf("[Task %d] Analysis: %.1fms, Synthesis: %.1fms, Summary: %.1fms, Total: %.1fms",
			i+1, float64(analysisTime.Milliseconds()), float64(synthesisTime.Milliseconds()), float64(summaryTime.Milliseconds()), float64(taskTime.Milliseconds()))
	}

	totalTime = time.Since(startTime)

	// Calculate statistics
	avgAnalysis := average(analysisTimes)
	avgSynthesis := average(synthesisTimes)
	avgSummary := average(summaryTimes)
	avgTotal := average(totalTimes)

	return map[string]interface{}{
		"mode":               mode,
		"num_tasks":          numTasks,
		"total_time_seconds": totalTime.Seconds(),
		"avg_analysis_ms":    avgAnalysis,
		"avg_synthesis_ms":   avgSynthesis,
		"avg_summary_ms":     avgSummary,
		"avg_total_ms":       avgTotal,
		"analysis_times":     analysisTimes,
		"synthesis_times":    synthesisTimes,
		"summary_times":      summaryTimes,
		"total_times":        totalTimes,
	}, nil
}

func average(values []float64) float64 {
	if len(values) == 0 {
		return 0
	}
	sum := 0.0
	for _, v := range values {
		sum += v
	}
	return sum / float64(len(values))
}

func checkOrlaReady(url string) error {
	resp, err := http.Get(url + "/api/v1/health")
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("health check returned status %d", resp.StatusCode)
	}
	return nil
}

func checkBackendReady(url string) error {
	// SGLang doesn't have a standard health endpoint, so we check if the server responds
	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Get(url)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	// Any response (even 404) means the server is up
	return nil
}

func displayLogTail(logFile string) {
	// Read and display last 20 lines of log file
	data, err := os.ReadFile(logFile)
	if err != nil {
		log.Printf("Could not read log file: %v", err)
		return
	}

	lines := strings.Split(string(data), "\n")
	start := len(lines) - 20
	if start < 0 {
		start = 0
	}

	log.Printf("Last 20 lines of Orla daemon log:")
	log.Printf("---")
	for i := start; i < len(lines); i++ {
		log.Printf("%s", lines[i])
	}
	log.Printf("---")
}

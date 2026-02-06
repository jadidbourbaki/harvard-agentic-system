// Package main runs the Story Finishing game experiment from the Harvard Agentic System.
//
// Two agents alternate turns; each turn an agent receives the story so far and generates
// exactly k tokens (k = c). The Orla daemon uses streaming for workflow tasks and returns
// TTFT (time to first token) and TPOT (time per output token) in the response.
//
// Usage:
//
//	go run . --turns 100 --k 32 --cache-strategy flush --backend http://localhost:30000
//	go run . --turns 100 --noise-rate 2   # with background load (Poisson, 2 req/s)
//	go run . --start-sglang   # start SGLang in a new tmux window (must be inside tmux), wait for ready, then shut down when done
//	go run . --backend-type vllm --backend http://localhost:8000/v1 --start-vllm   # run on vLLM to avoid SGLang global KVCache flush dips
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
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"

	orla "github.com/dorcha-inc/orla/pkg/api"
)

const (
	sglangTmuxSession = "sglang-story" // used for docker container name and tmux window name
	sglangTmuxWindow  = "sglang-story"
	vllmTmuxSession   = "vllm-story"
	vllmTmuxWindow    = "vllm-story"
	storyModelName    = "mistralai/Mistral-7B-Instruct-v0.3"
)

func init() {
	log.SetOutput(os.Stderr)
	log.SetFlags(log.LstdFlags | log.Lmicroseconds)
}

var sudoPassword string

const storyPromptTemplate = `We are playing a story finishing game. It is your turn. You are only allowed to give me the next %d tokens. You must give me exactly the next %d tokens to finish the story. The story starts as follows:

Once upon a time %s`

func main() {
	sudoPassword = os.Getenv("SUDO_PASSWORD")
	if sudoPassword == "" {
		log.Fatalf("SUDO_PASSWORD environment variable is not set")
	}

	if killErr := exec.Command("killall", "orla").Run(); killErr != nil {
		log.Printf("Note: No existing orla processes to kill (this is OK)")
	}

	turns := flag.Int("turns", 100, "Number of turns T")
	k := flag.Int("k", 32, "Tokens per turn (k = c)")
	cacheStrategy := flag.String("cache-strategy", "flush", "Cache strategy: 'flush' or 'preserve'")
	backendType := flag.String("backend-type", "sglang", "Backend type: 'sglang' or 'vllm' (vllm uses Orla's openai backend)")
	backend := flag.String("backend", "", "Backend URL (default: http://localhost:30000 for sglang, http://localhost:8000/v1 for vllm)")
	noiseRate := flag.Float64("noise-rate", 0, "Background noise: Poisson rate (req/s); 0 = disabled")
	startSGLang := flag.Bool("start-sglang", false, "Start SGLang in a new tmux session before the experiment and shut it down when done")
	startVLLM := flag.Bool("start-vllm", false, "Start vLLM in a new tmux session before the experiment and shut it down when done")
	output := flag.String("output", "", "Output file (default: stdout)")
	flag.Parse()

	if *backendType != "sglang" && *backendType != "vllm" {
		log.Fatalf("backend-type must be 'sglang' or 'vllm', got %q", *backendType)
	}
	if *backend == "" {
		if *backendType == "vllm" {
			*backend = "http://localhost:8000/v1"
		} else {
			*backend = "http://localhost:30000"
		}
	}
	if *startSGLang && *startVLLM {
		log.Fatalf("cannot use both --start-sglang and --start-vllm")
	}
	if *startVLLM && *backendType != "vllm" {
		log.Fatalf("--start-vllm requires --backend-type vllm")
	}
	if *startSGLang && *backendType != "sglang" {
		log.Fatalf("--start-sglang requires --backend-type sglang")
	}

	if *cacheStrategy != "flush" && *cacheStrategy != "preserve" {
		log.Fatalf("cache-strategy must be 'flush' or 'preserve', got %q", *cacheStrategy)
	}

	if *output != "" {
		if err := os.MkdirAll(filepath.Dir(*output), 0755); err != nil {
			log.Fatalf("Failed to create output directory: %v", err)
		}
	}

	log.Printf("Story finishing: turns=%d, k=%d, cache=%s, backend-type=%s, noise-rate=%.2f, start-sglang=%v, start-vllm=%v", *turns, *k, *cacheStrategy, *backendType, *noiseRate, *startSGLang, *startVLLM)

	configFile, configErr := createStoryFinishingConfig(*backendType, *backend, *cacheStrategy)
	if configErr != nil {
		log.Fatalf("Failed to create config: %v", configErr)
	}
	defer os.Remove(configFile)

	// Optional: start SGLang in tmux before experiment, shut down when we exit
	if *startSGLang {
		if err := startSGLangInTmux(*backend); err != nil {
			log.Fatalf("Failed to start SGLang in tmux: %v", err)
		}
		defer stopSGLangTmux()
		if err := waitForBackendReady(*backend, *backendType, 5*time.Minute); err != nil {
			log.Fatalf("SGLang did not become ready: %v", err)
		}
		log.Printf("SGLang is ready")
	}

	// Optional: start vLLM in tmux before experiment, shut down when we exit
	if *startVLLM {
		if err := startVLLMInTmux(*backend); err != nil {
			log.Fatalf("Failed to start vLLM in tmux: %v", err)
		}
		defer stopVLLMTmux()
		if err := waitForBackendReady(*backend, *backendType, 5*time.Minute); err != nil {
			log.Fatalf("vLLM did not become ready: %v", err)
		}
		log.Printf("vLLM is ready")
	}

	if err := checkBackendReady(*backend, *backendType); err != nil {
		log.Fatalf("Backend %s not ready: %v", *backend, err)
	}

	logFile := fmt.Sprintf("orla_story_finishing_%s_k_%v_turns_%v_noise_%.2f_%s.log", *cacheStrategy, *k, *turns, *noiseRate, *backendType)
	if *output != "" {
		logFile = filepath.Join(filepath.Dir(*output), filepath.Base(logFile))
	}

	daemonLog, err := os.Create(logFile)
	if err != nil {
		log.Fatalf("Failed to create daemon log: %v", err)
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

	processExited := make(chan error, 1)
	go func() { processExited <- cmd.Wait() }()

	orlaURL := "http://localhost:8081"
	for waited := 0 * time.Second; ; waited += 500 * time.Millisecond {
		select {
		case err := <-processExited:
			log.Fatalf("Orla daemon exited: %v", err)
		default:
		}
		if err := checkOrlaReady(orlaURL); err == nil {
			log.Printf("Orla ready (waited %.1fs)", waited.Seconds())
			break
		}
		if waited >= 60*time.Second {
			log.Fatalf("Orla did not become ready")
		}
		time.Sleep(500 * time.Millisecond)
	}

	daemonMonitorDone := make(chan bool, 1)
	go func() {
		select {
		case err := <-processExited:
			log.Fatalf("Orla exited during experiment: %v", err)
		case <-daemonMonitorDone:
			return
		}
	}()

	ctx := context.Background()

	// Optional background noise: send concurrent requests to the backend on another goroutine
	var noiseCancel context.CancelFunc
	if *noiseRate > 0 {
		noiseCtx, cancel := context.WithCancel(ctx)
		noiseCancel = cancel
		go runBackgroundNoise(noiseCtx, *backend, *backendType, *noiseRate)
		log.Printf("Background noise started: %.2f req/s (Poisson)", *noiseRate)
	}

	results, runErr := runStoryFinishing(ctx, orlaURL, *backendType, *cacheStrategy, *turns, *k)

	if noiseCancel != nil {
		noiseCancel()
	}
	close(daemonMonitorDone)

	if runErr != nil {
		log.Fatalf("Experiment failed: %v", runErr)
	}

	results["experiment_params"] = map[string]interface{}{
		"turns":          *turns,
		"k":              *k,
		"cache_strategy": *cacheStrategy,
		"backend_type":   *backendType,
		"backend":        *backend,
		"noise_rate":     *noiseRate,
		"start_sglang":   *startSGLang,
		"start_vllm":     *startVLLM,
	}

	jsonData, _ := json.MarshalIndent(results, "", "  ")
	if *output != "" {
		_ = os.WriteFile(*output, jsonData, 0644)
		log.Printf("Results written to %s", *output)
	} else {
		log.Printf("Results: %s", string(jsonData))
	}
}

func createStoryFinishingConfig(backendType, backend, cacheStrategy string) (string, error) {
	policy := "preserve"
	if cacheStrategy == "flush" {
		policy = "aggressive_flush"
	}
	var config string
	if backendType == "vllm" {
		// Orla's "openai" backend; vLLM exposes OpenAI-compatible API. Cache policy is recorded but not applied (no global flush).
		config = fmt.Sprintf(`log_format: pretty
log_level: info
agentic_serving:
  mode: daemon
  daemon:
    listen_address: "localhost:8081"
  llm_servers:
    - name: "story_model"
      backend:
        type: "openai"
        endpoint: "%s"
      model: "openai:%s"
      cache:
        policy: "%s"
  agent_profiles:
    - name: "agent_i"
      llm_server: "story_model"
    - name: "agent_j"
      llm_server: "story_model"
  workflows:
    - name: "story_finishing_game"
      tasks:
        - agent_profile: "agent_i"
          use_context: false
        - agent_profile: "agent_j"
          use_context: false
`, backend, storyModelName, policy)
	} else {
		config = fmt.Sprintf(`log_format: pretty
log_level: info
agentic_serving:
  mode: daemon
  daemon:
    listen_address: "localhost:8081"
  llm_servers:
    - name: "story_model"
      backend:
        type: "sglang"
        endpoint: "%s"
      model: "sglang:%s"
      cache:
        policy: "%s"
  agent_profiles:
    - name: "agent_i"
      llm_server: "story_model"
    - name: "agent_j"
      llm_server: "story_model"
  workflows:
    - name: "story_finishing_game"
      tasks:
        - agent_profile: "agent_i"
          use_context: false
        - agent_profile: "agent_j"
          use_context: false
`, backend, storyModelName, policy)
	}
	f, err := os.CreateTemp("", "orla_story_finishing_*.yaml")
	if err != nil {
		return "", err
	}
	if _, err := f.Write([]byte(config)); err != nil {
		f.Close()
		os.Remove(f.Name())
		return "", err
	}
	if err := f.Close(); err != nil {
		os.Remove(f.Name())
		return "", err
	}
	return f.Name(), nil
}

func runStoryFinishing(ctx context.Context, orlaURL, backendType, cacheStrategy string, turns, k int) (map[string]interface{}, error) {
	client := orla.NewClient(orlaURL)

	var ttftPerTurn, tpotPerTurn []float64
	var latencyPerTurnMs []float64
	storyContext := ""
	startTotal := time.Now()
	turn := 0

	for turn < turns {
		execID, err := client.StartWorkflow(ctx, "story_finishing_game")
		if err != nil {
			return nil, fmt.Errorf("start workflow: %w", err)
		}

		for step := 0; step < 2 && turn < turns; step++ {
			_, taskIndex, complete, _, err := client.GetNextTask(ctx, execID)
			if err != nil {
				return nil, fmt.Errorf("get next task: %w", err)
			}
			if complete {
				break
			}

			prompt := fmt.Sprintf(storyPromptTemplate, k, k, storyContext)
			if storyContext == "" {
				prompt = fmt.Sprintf(storyPromptTemplate, k, k, "")
			}
			// For vLLM + flush: prepend a unique prefix per request so every turn gets a fresh KVCache.
			// vLLM hashes the first block by token content; different prefix => no cache reuse.
			if backendType == "vllm" && cacheStrategy == "flush" {
				prompt = fmt.Sprintf("Request %d.\n\n", turn) + prompt
			}

			turnStart := time.Now()
			resp, err := client.ExecuteTask(ctx, execID, taskIndex, prompt, &orla.ExecuteTaskOptions{MaxTokens: k, Stream: true})
			if err != nil {
				return nil, fmt.Errorf("execute task: %w", err)
			}
			elapsed := time.Since(turnStart)

			content := strings.TrimSpace(resp.Content)
			if content != "" {
				if storyContext != "" {
					storyContext += " " + content
				} else {
					storyContext = content
				}
			}

			latencyPerTurnMs = append(latencyPerTurnMs, float64(elapsed.Milliseconds()))
			var ttftMs, tpotMs float64
			if resp.Metrics != nil {
				ttftMs = float64(resp.Metrics.TTFTMs)
				tpotMs = float64(resp.Metrics.TPOTMs)
			}
			ttftPerTurn = append(ttftPerTurn, ttftMs)
			tpotPerTurn = append(tpotPerTurn, tpotMs)
			turn++

			// Print each increment so you can validate the experiment is working
			log.Printf("[Turn %d/%d] +%q  (ttft=%.1fms tpot=%.1fms)", turn, turns, content, ttftMs, tpotMs)
			if turn%10 == 0 && storyContext != "" {
				preview := storyContext
				if len(preview) > 128 {
					preview = preview[:128] + "..."
				}
				log.Printf("[Turn %d/%d] story so far (%d chars): %q", turn, turns, len(storyContext), preview)
			}
		}
	}

	totalTime := time.Since(startTotal)
	avg := func(x []float64) float64 {
		s := 0.0
		for _, v := range x {
			s += v
		}
		if len(x) == 0 {
			return 0
		}
		return s / float64(len(x))
	}

	return map[string]interface{}{
		"turns":               turns,
		"k":                   k,
		"total_time_sec":      totalTime.Seconds(),
		"avg_ttft_ms":         avg(ttftPerTurn),
		"avg_tpot_ms":         avg(tpotPerTurn),
		"ttft_per_turn":       ttftPerTurn,
		"tpot_per_turn":       tpotPerTurn,
		"latency_per_turn_ms": latencyPerTurnMs,
		"story_length_chars":  len(storyContext),
		"story":               storyContext,
	}, nil
}

func checkOrlaReady(url string) error {
	resp, err := http.Get(url + "/api/v1/health")
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("health %d", resp.StatusCode)
	}
	return nil
}

func vllmProbeURL(backendURL string) string {
	base := strings.TrimSuffix(backendURL, "/")
	if strings.HasSuffix(base, "/v1") {
		return base + "/models"
	}
	return base + "/v1/models"
}

func checkBackendReady(backendURL, backendType string) error {
	c := &http.Client{Timeout: 5 * time.Second}
	probeURL := backendURL
	if backendType == "vllm" {
		probeURL = vllmProbeURL(backendURL)
	}
	resp, err := c.Get(probeURL)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	return nil
}

// waitForBackendReady polls the backend until it responds or timeout.
// SGLang may not return 200 on GET; we consider it ready when the server accepts connections.
// vLLM: probe /v1/models.
func waitForBackendReady(backendURL, backendType string, timeout time.Duration) error {
	probeURL := backendURL
	if backendType == "vllm" {
		probeURL = vllmProbeURL(backendURL)
	}
	deadline := time.Now().Add(timeout)
	c := &http.Client{Timeout: 5 * time.Second}
	for time.Now().Before(deadline) {
		resp, err := c.Get(probeURL)
		if err == nil {
			resp.Body.Close()
			return nil
		}
		time.Sleep(2 * time.Second)
	}
	return fmt.Errorf("backend %s not ready after %v", backendURL, timeout)
}

// startSGLangInTmux starts SGLang in a new detached tmux window in the current session.
// Requires running inside tmux (TMUX set); errors out if not. Uses SGLANG_START_CMD env if set.
func startSGLangInTmux(backendURL string) error {
	// Kill existing window with same name if present to avoid errors
	if err := exec.Command("tmux", "kill-window", "-t", ":"+sglangTmuxWindow).Run(); err != nil {
		log.Printf("Note: tmux kill-window %s: %v (window may already be gone)", sglangTmuxWindow, err)
	}

	if os.Getenv("TMUX") == "" {
		return fmt.Errorf("--start-sglang requires running inside tmux (so SGLang runs in a new window); start tmux first, then run this command")
	}

	// Remove any existing container so the new one can bind the port and use the name (do this from Go before creating the window so waitForBackendReady waits for the new SGLang).
	rm := exec.Command("sh", "-c", "echo \"$SUDO_PASSWORD\" | sudo -S docker rm -f "+sglangTmuxSession+" 2>/dev/null")
	rm.Env = append(os.Environ(), "SUDO_PASSWORD="+sudoPassword)
	if err := rm.Run(); err != nil {
		return fmt.Errorf("could not remove existing container: %w", err)
	}

	// Pass SUDO_PASSWORD into the tmux session so the new window's shell has it (new windows don't inherit the pane's env otherwise).
	if err := exec.Command("tmux", "set-environment", "SUDO_PASSWORD", sudoPassword).Run(); err != nil {
		return fmt.Errorf("could not set SUDO_PASSWORD in tmux session: %w", err)
	}

	u, err := url.Parse(backendURL)
	if err != nil {
		return fmt.Errorf("parse backend URL: %w", err)
	}

	port := u.Port()
	if port == "" {
		port = "30000"
	}

	cmdStr := os.Getenv("SGLANG_START_CMD")
	if cmdStr == "" {
		cmdStr = fmt.Sprintf("echo \"$SUDO_PASSWORD\" | sudo -S docker run --rm --name %s --gpus all --shm-size 32g -p %s:30000 "+
			"-v $HOME/.cache/huggingface:/root/.cache/huggingface --ipc=host "+
			"lmsysorg/sglang:latest python -m sglang.launch_server "+
			"--model-path mistralai/Mistral-7B-Instruct-v0.3 --port 30000 --host 0.0.0.0 --mem-fraction-static 0.5",
			sglangTmuxSession, port)
	}
	cmdStr += "; echo 'SGLang process exited. Window stays open until experiment ends.'; exec bash"

	tmux := exec.Command("tmux", "new-window", "-d", "-n", sglangTmuxWindow, "bash", "-c", cmdStr)
	tmux.Stdout = os.Stdout
	tmux.Stderr = os.Stderr
	if err := tmux.Run(); err != nil {
		return fmt.Errorf("tmux new-window: %w", err)
	}
	log.Printf("Started SGLang in new tmux window %q (switch with C-b n or C-b w)", sglangTmuxWindow)
	return nil
}

func stopSGLangTmux() {
	// Remove the container so the name/port are free for the next run (and so we don't leave it running).
	rm := exec.Command("sh", "-c", "echo \"$SUDO_PASSWORD\" | sudo -S docker rm -f "+sglangTmuxSession+" 2>/dev/null")
	rm.Env = append(os.Environ(), "SUDO_PASSWORD="+sudoPassword)

	if err := rm.Run(); err != nil {
		log.Fatalf("Could not remove container: %v", err)
	}

	if err := exec.Command("tmux", "kill-window", "-t", ":"+sglangTmuxWindow).Run(); err != nil {
		log.Printf("Note: tmux kill-window %s: %v (window may already be gone)", sglangTmuxWindow, err)
		return
	}

	log.Printf("Stopped SGLang (tmux window %s)", sglangTmuxWindow)
}

// startVLLMInTmux starts vLLM (OpenAI-compatible) in a new detached tmux window.
// Requires running inside tmux. Uses VLLM_START_CMD env if set.
func startVLLMInTmux(backendURL string) error {
	if err := exec.Command("tmux", "kill-window", "-t", ":"+vllmTmuxWindow).Run(); err != nil {
		log.Printf("Note: tmux kill-window %s: %v (window may already be gone)", vllmTmuxWindow, err)
	}

	if os.Getenv("TMUX") == "" {
		return fmt.Errorf("--start-vllm requires running inside tmux; start tmux first, then run this command")
	}

	rm := exec.Command("sh", "-c", "echo \"$SUDO_PASSWORD\" | sudo -S docker rm -f "+vllmTmuxSession+" 2>/dev/null")
	rm.Env = append(os.Environ(), "SUDO_PASSWORD="+sudoPassword)
	if err := rm.Run(); err != nil {
		return fmt.Errorf("could not remove existing container: %w", err)
	}

	if err := exec.Command("tmux", "set-environment", "SUDO_PASSWORD", sudoPassword).Run(); err != nil {
		return fmt.Errorf("could not set SUDO_PASSWORD in tmux session: %w", err)
	}

	u, err := url.Parse(backendURL)
	if err != nil {
		return fmt.Errorf("parse backend URL: %w", err)
	}
	port := u.Port()
	if port == "" {
		port = "8000"
	}

	cmdStr := os.Getenv("VLLM_START_CMD")
	if cmdStr == "" {
		cmdStr = fmt.Sprintf("echo \"$SUDO_PASSWORD\" | sudo -S docker run --rm --name %s --gpus all -p %s:8000 "+
			"-v $HOME/.cache/huggingface:/root/.cache/huggingface "+
			"vllm/vllm-openai:latest "+
			"--model %s --host 0.0.0.0 --port 8000",
			vllmTmuxSession, port, storyModelName)
	}
	cmdStr += "; echo 'vLLM process exited. Window stays open until experiment ends.'; exec bash"

	tmux := exec.Command("tmux", "new-window", "-d", "-n", vllmTmuxWindow, "bash", "-c", cmdStr)
	tmux.Stdout = os.Stdout
	tmux.Stderr = os.Stderr
	if err := tmux.Run(); err != nil {
		return fmt.Errorf("tmux new-window: %w", err)
	}
	log.Printf("Started vLLM in new tmux window %q (switch with C-b n or C-b w)", vllmTmuxWindow)
	return nil
}

func stopVLLMTmux() {
	rm := exec.Command("sh", "-c", "echo \"$SUDO_PASSWORD\" | sudo -S docker rm -f "+vllmTmuxSession+" 2>/dev/null")
	rm.Env = append(os.Environ(), "SUDO_PASSWORD="+sudoPassword)
	if err := rm.Run(); err != nil {
		log.Fatalf("Could not remove vLLM container: %v", err)
	}
	if err := exec.Command("tmux", "kill-window", "-t", ":"+vllmTmuxWindow).Run(); err != nil {
		log.Printf("Note: tmux kill-window %s: %v (window may already be gone)", vllmTmuxWindow, err)
		return
	}
	log.Printf("Stopped vLLM (tmux window %s)", vllmTmuxWindow)
}

// runBackgroundNoise sends Poisson-paced requests to the backend to simulate concurrent load.
// It runs until ctx is cancelled. Uses SGLang /api/chat or OpenAI /v1/chat/completions depending on backendType.
func runBackgroundNoise(ctx context.Context, backend, backendType string, rate float64) {
	client := &http.Client{Timeout: 30 * time.Second}
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
	rng := rand.New(rand.NewSource(42))
	var rngMu sync.Mutex
	for {
		select {
		case <-ctx.Done():
			return
		default:
			go func() {
				rngMu.Lock()
				prompt := prompts[rng.Intn(len(prompts))]
				rngMu.Unlock()
				if err := sendNoiseRequest(client, backend, backendType, prompt); err != nil {
					log.Printf("Background noise request failed: %v", err)
				}
			}()
			rngMu.Lock()
			interArrival := time.Duration(rng.ExpFloat64() / rate * float64(time.Second))
			rngMu.Unlock()
			select {
			case <-ctx.Done():
				return
			case <-time.After(interArrival):
			}
		}
	}
}

func sendNoiseRequest(client *http.Client, backend, backendType, prompt string) error {
	if backendType == "vllm" {
		// OpenAI-compatible POST /v1/chat/completions
		base := strings.TrimSuffix(backend, "/v1")
		base = strings.TrimSuffix(base, "/")
		noiseURL := base + "/v1/chat/completions"
		reqBody := map[string]any{
			"model": storyModelName,
			"messages": []map[string]string{
				{"role": "user", "content": prompt},
			},
			"stream":     false,
			"max_tokens": 20,
		}
		jsonData, err := json.Marshal(reqBody)
		if err != nil {
			return err
		}
		req, err := http.NewRequest("POST", noiseURL, bytes.NewBuffer(jsonData))
		if err != nil {
			return err
		}
		req.Header.Set("Content-Type", "application/json")
		resp, err := client.Do(req)
		if err != nil {
			return err
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			return fmt.Errorf("status %d", resp.StatusCode)
		}
		return nil
	}
	// SGLang /api/chat
	noiseURL := fmt.Sprintf("%s/api/chat", backend)
	reqBody := map[string]any{
		"model": storyModelName,
		"messages": []map[string]string{
			{"role": "user", "content": prompt},
		},
		"stream": false,
		"options": map[string]any{
			"num_predict": 20,
		},
	}
	jsonData, err := json.Marshal(reqBody)
	if err != nil {
		return err
	}
	req, err := http.NewRequest("POST", noiseURL, bytes.NewBuffer(jsonData))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("status %d", resp.StatusCode)
	}
	return nil
}

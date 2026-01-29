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
	backend := flag.String("backend", "http://localhost:30000", "SGLang backend URL")
	noiseRate := flag.Float64("noise-rate", 0, "Background noise: Poisson rate (req/s) to SGLang; 0 = disabled")
	startSGLang := flag.Bool("start-sglang", false, "Start SGLang in a new tmux session before the experiment and shut it down when done")
	output := flag.String("output", "", "Output file (default: stdout)")
	flag.Parse()

	if *cacheStrategy != "flush" && *cacheStrategy != "preserve" {
		log.Fatalf("cache-strategy must be 'flush' or 'preserve', got %q", *cacheStrategy)
	}

	if *output != "" {
		if err := os.MkdirAll(filepath.Dir(*output), 0755); err != nil {
			log.Fatalf("Failed to create output directory: %v", err)
		}
	}

	log.Printf("Story finishing: turns=%d, k=%d, cache=%s, noise-rate=%.2f, start-sglang=%v", *turns, *k, *cacheStrategy, *noiseRate, *startSGLang)

	configFile, configErr := createStoryFinishingConfig(*backend, *cacheStrategy)
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
		if err := waitForBackendReady(*backend, 5*time.Minute); err != nil {
			log.Fatalf("SGLang did not become ready: %v", err)
		}
		log.Printf("SGLang is ready")
	}

	if err := checkBackendReady(*backend); err != nil {
		log.Fatalf("Backend %s not ready: %v", *backend, err)
	}

	logFile := fmt.Sprintf("orla_story_finishing_%s_k_%v_turns_%v_noise_%.2f.log", *cacheStrategy, *k, *turns, *noiseRate)
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

	// Optional background noise: send concurrent requests to SGLang on another goroutine
	var noiseCancel context.CancelFunc
	if *noiseRate > 0 {
		noiseCtx, cancel := context.WithCancel(ctx)
		noiseCancel = cancel
		go runBackgroundNoise(noiseCtx, *backend, *noiseRate)
		log.Printf("Background noise started: %.2f req/s (Poisson)", *noiseRate)
	}

	results, runErr := runStoryFinishing(ctx, orlaURL, *turns, *k)

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
		"backend":        *backend,
		"noise_rate":     *noiseRate,
		"start_sglang":   *startSGLang,
	}

	jsonData, _ := json.MarshalIndent(results, "", "  ")
	if *output != "" {
		_ = os.WriteFile(*output, jsonData, 0644)
		log.Printf("Results written to %s", *output)
	} else {
		log.Printf("Results: %s", string(jsonData))
	}
}

func createStoryFinishingConfig(backend, cacheStrategy string) (string, error) {
	policy := "preserve"
	if cacheStrategy == "flush" {
		policy = "aggressive_flush"
	}
	config := fmt.Sprintf(`log_format: pretty
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
      model: "sglang:mistralai/Mistral-7B-Instruct-v0.3"
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
          use_context: true
        - agent_profile: "agent_j"
          use_context: true
`, backend, policy)
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

func runStoryFinishing(ctx context.Context, orlaURL string, turns, k int) (map[string]interface{}, error) {
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

			if turn%10 == 0 || turn == 1 {
				log.Printf("[Turn %d/%d] ttft=%.1fms tpot=%.1fms elapsed=%v", turn, turns, ttftMs, tpotMs, elapsed)
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

func checkBackendReady(backendURL string) error {
	c := &http.Client{Timeout: 5 * time.Second}
	resp, err := c.Get(backendURL)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	return nil
}

// waitForBackendReady polls the backend until it responds or timeout.
// SGLang may not return 200 on GET; we consider it ready when the server accepts connections.
func waitForBackendReady(backendURL string, timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	c := &http.Client{Timeout: 5 * time.Second}
	for time.Now().Before(deadline) {
		resp, err := c.Get(backendURL)
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

// runBackgroundNoise sends Poisson-paced requests to the SGLang backend to simulate concurrent load.
// It runs until ctx is cancelled.
func runBackgroundNoise(ctx context.Context, backend string, rate float64) {
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
				if err := sendNoiseRequest(client, backend, prompt); err != nil {
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

func sendNoiseRequest(client *http.Client, backend, prompt string) error {
	url := fmt.Sprintf("%s/api/chat", backend)
	reqBody := map[string]any{
		"model": "mistralai/Mistral-7B-Instruct-v0.3",
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
	req, err := http.NewRequest("POST", url, bytes.NewBuffer(jsonData))
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

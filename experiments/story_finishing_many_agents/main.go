package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/harvard-agentic-system/pkg/agents"
	"github.com/harvard-agentic-system/pkg/metrics"
)

type ExperimentConfig struct {
	Turns            int    `json:"turns"`
	K                int    `json:"k"`
	CacheStrategy    string `json:"cache_strategy"`
	BackgroundAgents int    `json:"background_agents"`
}

var experimentConfig ExperimentConfig

func ParseFlags() error {
	turns := flag.Int("turns", 20, "Number of turns")
	k := flag.Int("k", 32, "Tokens per turn")
	cacheStrategy := flag.String("cache-strategy", "preserve", "Cache strategy: 'flush' (unique prefix per turn to avoid vLLM prefix cache) or 'preserve'")
	backgroundAgents := flag.Int("background-agents", 0, "Number of background agents")
	flag.Parse()

	if *turns <= 0 {
		return fmt.Errorf("turns must be greater than 0")
	}

	if *k <= 0 {
		return fmt.Errorf("k must be greater than 0")
	}

	if *cacheStrategy != "flush" && *cacheStrategy != "preserve" {
		return fmt.Errorf("cache-strategy must be 'flush' or 'preserve', got %q", *cacheStrategy)
	}

	if *backgroundAgents < 0 {
		return fmt.Errorf("background-agents must be >= 0")
	}

	experimentConfig = ExperimentConfig{Turns: *turns, K: *k, CacheStrategy: *cacheStrategy, BackgroundAgents: *backgroundAgents}
	return nil
}

func StoryFinishing(ctx context.Context, agent *agents.StoryAgent) error {
	prevStoryContext := ""

	for turn := 0; turn < experimentConfig.Turns; turn++ {
		fmt.Printf("turn %d starting\n", turn)

		err := agent.NextStoryTurn(ctx)
		if err != nil {
			return fmt.Errorf("turn %d failed to finish story: %v", turn, err)
		}

		fmt.Printf("turn %d finished\n", turn)

		currentStoryContext := agent.StoryContext()
		addedContent := strings.TrimPrefix(currentStoryContext, prevStoryContext)
		prevStoryContext = currentStoryContext

		fmt.Printf("addition to the story context: %q\n", addedContent)
	}

	return nil
}

// runBackgroundStoryAgent runs a single story agent in a loop (NextStoryTurn repeatedly) until ctx is cancelled.
func runBackgroundStoryAgent(ctx context.Context, agent *agents.StoryAgent) {
	currentTurn := 0

	for ctx.Err() == nil {
		err := agent.NextStoryTurn(ctx)

		if err != nil && ctx.Err() != nil {
			log.Printf("background story agent context done")
			return
		}

		if err != nil {
			log.Printf("background story agent error: %v", err)
		}

		currentTurn++

		if currentTurn == experimentConfig.Turns {
			agent.SetStoryContext("")
			currentTurn = 0
		}
	}
}

func outputPath() string {
	outputFileName := fmt.Sprintf("turns%d_k%d_cache%s_background_agents%d.json", experimentConfig.Turns, experimentConfig.K, experimentConfig.CacheStrategy, experimentConfig.BackgroundAgents)
	return filepath.Join("output/story_finishing_many_agents", outputFileName)
}

func main() {
	if err := ParseFlags(); err != nil {
		log.Fatalf("failed to parse flags: %v", err)
	}

	log.SetOutput(os.Stderr)
	outputDir := "output/story_finishing_many_agents"
	if err := os.MkdirAll(outputDir, 0755); err != nil {
		log.Fatalf("create output dir: %v", err)
	}

	outputPath := outputPath()

	log.Printf("Story finishing many agents: turns=%d k=%d cache=%s background_agents=%d, output=%s", experimentConfig.Turns, experimentConfig.K, experimentConfig.CacheStrategy, experimentConfig.BackgroundAgents, outputPath)

	client, backend, err := agents.NewOrlaClientWithVllmBackend()
	if err != nil {
		log.Fatalf("failed to create orla client with vllm backend: %v", err)
	}

	mainAgent := agents.NewStoryAgent(client, backend, experimentConfig.K)
	err = mainAgent.SetCacheStrategy(experimentConfig.CacheStrategy)
	if err != nil {
		log.Fatalf("failed to set cache strategy for agent: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	backgroundAgents := make([]*agents.StoryAgent, experimentConfig.BackgroundAgents)

	var wg sync.WaitGroup
	for i := range experimentConfig.BackgroundAgents {
		backgroundAgents[i] = agents.NewStoryAgent(client, backend, experimentConfig.K)
		err = backgroundAgents[i].SetCacheStrategy(experimentConfig.CacheStrategy)

		if err != nil {
			log.Fatalf("failed to set cache strategy for background agent %d: %v", i, err)
		}

		wg.Go(func() {
			runBackgroundStoryAgent(ctx, backgroundAgents[i])
		})
	}

	if experimentConfig.BackgroundAgents > 0 {
		log.Printf("started %d background story agents", experimentConfig.BackgroundAgents)
	}

	log.Printf("starting main story finishing agent loop")
	startTotal := time.Now()
	err = StoryFinishing(ctx, mainAgent)
	if err != nil {
		log.Fatalf("failed to finish story: %v", err)
	}

	cancel()
	log.Printf("cancelled context")
	wg.Wait()
	totalTime := time.Since(startTotal)

	backgroundAgentsMetrics := make([]*metrics.AgentMetrics, experimentConfig.BackgroundAgents)
	for i := range experimentConfig.BackgroundAgents {
		backgroundAgentsMetrics[i] = backgroundAgents[i].AgentMetrics()
	}

	agentsMetricsMap := make(map[string]any)
	for i := range experimentConfig.BackgroundAgents {
		agentsMetricsMap[fmt.Sprintf("background_agent_%d", i)] = backgroundAgentsMetrics[i].ToMap()
	}
	agentsMetricsMap["main_agent"] = mainAgent.AgentMetrics().ToMap()

	storyContext := mainAgent.StoryContext()
	results := map[string]any{
		"turns":              experimentConfig.Turns,
		"k":                  experimentConfig.K,
		"cache_strategy":     experimentConfig.CacheStrategy,
		"background_agents":  experimentConfig.BackgroundAgents,
		"total_time_sec":     totalTime.Seconds(),
		"story_length_chars": len(storyContext),
		"story":              storyContext,
		"agents":             agentsMetricsMap,
	}

	jsonData, err := json.MarshalIndent(results, "", "  ")
	if err != nil {
		log.Fatalf("failed to marshal results: %v", err)
	}
	if err := os.WriteFile(outputPath, jsonData, 0644); err != nil {
		log.Fatalf("failed to write output: %v", err)
	}
	log.Printf("Results written to %s", outputPath)
	log.Printf("story finishing finished in %s", totalTime)
}

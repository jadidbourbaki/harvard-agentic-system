package agents

import (
	"context"
	"fmt"
	"strings"
	"sync/atomic"
	"time"

	orla "github.com/dorcha-inc/orla/pkg/api"
	"github.com/harvard-agentic-system/pkg/metrics"
)

const (
	storyPromptTemplate = `We are playing a story finishing game. It is your turn. You are only allowed to give me the next %d tokens. You must give me exactly the next %d tokens to finish the story. The story starts as follows:

Once upon a time %s`
)

type StoryAgent struct {
	agent         *orla.Agent
	tokensPerTurn int
	agentMetrics  *metrics.AgentMetrics
	cacheStrategy string
	turnCounter   atomic.Uint64
	storyContext  string
}

func NewStoryAgent(client *orla.OrlaClient, backend *orla.LLMBackend, tokensPerTurn int) *StoryAgent {
	agent := orla.NewAgent(client, backend)
	agent.SetMaxTokens(tokensPerTurn)
	return &StoryAgent{agent: agent, tokensPerTurn: tokensPerTurn, cacheStrategy: "flush", agentMetrics: metrics.NewAgentMetrics()}
}

func (a *StoryAgent) TokensPerTurn() int {
	return a.tokensPerTurn
}

func (a *StoryAgent) SetCacheStrategy(cacheStrategy string) error {
	if cacheStrategy != "flush" && cacheStrategy != "preserve" {
		return fmt.Errorf("cache strategy must be 'flush' or 'preserve', got %q", cacheStrategy)
	}
	a.cacheStrategy = cacheStrategy
	return nil
}

func (a *StoryAgent) NextStoryTurn(ctx context.Context) error {
	prompt := fmt.Sprintf(storyPromptTemplate, a.tokensPerTurn, a.tokensPerTurn, a.storyContext)

	if a.cacheStrategy == "flush" {
		turn := a.turnCounter.Add(1) - 1
		prompt = fmt.Sprintf("Request %d.\n\n", turn) + prompt
	}

	start := time.Now()
	stream, err := a.agent.ExecuteStream(ctx, prompt)
	if err != nil {
		return fmt.Errorf("failed to execute stream: %w", err)
	}

	resp, err := a.agent.ConsumeStream(ctx, stream, nil)
	if err != nil {
		return fmt.Errorf("failed to consume stream: %w", err)
	}

	content := strings.TrimSpace(resp.Content)
	if content == "" {
		return fmt.Errorf("got empty content from agent")
	}

	if a.agentMetrics == nil || resp.Metrics == nil {
		return fmt.Errorf("agent metrics or response metrics are nil")
	}

	now := time.Now()

	a.agentMetrics.TTFTMilliseconds.AddSample(float64(resp.Metrics.TTFTMs), now)
	a.agentMetrics.TPOTMilliseconds.AddSample(float64(resp.Metrics.TPOTMs), now)
	a.agentMetrics.LatencyMilliseconds.AddSample(float64(time.Since(start).Milliseconds()), now)

	a.storyContext += " " + content

	return nil
}

func (a *StoryAgent) StoryContext() string {
	return a.storyContext
}

func (a *StoryAgent) SetStoryContext(storyContext string) {
	a.storyContext = storyContext
}

func (a *StoryAgent) AgentMetrics() *metrics.AgentMetrics {
	return a.agentMetrics
}

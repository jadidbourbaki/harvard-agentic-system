package dolly

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"math/rand"
	"net/http"

	"go.mills.io/jsonlines"
)

const dolly15kURL = "https://huggingface.co/datasets/databricks/databricks-dolly-15k/resolve/main/databricks-dolly-15k.jsonl"
const expectedNumberOfPrompts = 15011
const randomSeed = 42

// InstructionsManager fetches and parses the Dolly 15K dataset.
type InstructionsManager struct {
	prompts []string
	buffer  []byte
	rng     *rand.Rand
}

// Instruction is a single instruction from the Dolly 15K dataset.
// https://huggingface.co/datasets/databricks/databricks-dolly-15k
type Instruction struct {
	Instruction string `json:"instruction"`
	Context     string `json:"context"`
	Response    string `json:"response"`
	Category    string `json:"category"`
}

func NewInstructionsManager() *InstructionsManager {
	return &InstructionsManager{
		prompts: make([]string, 0),
		buffer:  make([]byte, 0),
		rng:     rand.New(rand.NewSource(randomSeed)),
	}
}

// fetch fetches the Dolly 15K dataset and stores it in the buffer.
func (m *InstructionsManager) fetch() error {
	client := http.Client{}

	req, err := http.NewRequestWithContext(context.Background(), http.MethodGet, dolly15kURL, nil)
	if err != nil {
		return fmt.Errorf("failed to create Dolly 15K instructions request: %w", err)
	}

	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("failed to send Dolly 15K instructions request: %w", err)
	}

	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("failed to fetch Dolly 15K instructions: HTTP %s", resp.Status)
	}

	buffer, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("failed to read Dolly 15K instructions response body: %w", err)
	}

	m.buffer = buffer
	return nil
}

// parse parses the buffer as JSONL and populates prompts.
func (m *InstructionsManager) parse() error {
	var instructions []Instruction
	if err := jsonlines.Decode(bytes.NewReader(m.buffer), &instructions); err != nil {
		return fmt.Errorf("failed to decode Dolly 15K instructions: %w", err)
	}
	for _, inst := range instructions {
		if inst.Instruction != "" {
			m.prompts = append(m.prompts, inst.Instruction)
		}
	}

	return nil
}

const expectedFirstPrompt = "When did Virgin Australia start operating?"
const expectedLastPrompt = "What is the Masters?"

func (m *InstructionsManager) Validate() error {
	if len(m.prompts) != expectedNumberOfPrompts {
		return fmt.Errorf("expected %d prompts, got %d", expectedNumberOfPrompts, len(m.prompts))
	}

	if m.prompts[0] != expectedFirstPrompt {
		return fmt.Errorf("expected first prompt to be '%s', got %s", expectedFirstPrompt, m.prompts[0])
	}

	if m.prompts[len(m.prompts)-1] != expectedLastPrompt {
		return fmt.Errorf("expected last prompt to be '%s', got %s", expectedLastPrompt, m.prompts[len(m.prompts)-1])
	}

	return nil
}

func (m *InstructionsManager) Prompts() []string {
	return m.prompts
}

func (m *InstructionsManager) RandomPrompt() string {
	randomIndex := m.rng.Intn(len(m.prompts))
	return m.prompts[randomIndex]
}

func (m *InstructionsManager) LoadFromHuggingFace() error {
	err := m.fetch()
	if err != nil {
		return fmt.Errorf("failed to fetch Dolly 15K instructions: %w", err)
	}

	err = m.parse()
	if err != nil {
		return fmt.Errorf("failed to parse Dolly 15K instructions: %w", err)
	}
	return nil
}

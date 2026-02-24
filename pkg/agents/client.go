package agents

import (
	"context"
	"fmt"

	orla "github.com/dorcha-inc/orla/pkg/api"
)

const (
	orlaBackendName = "vllm"
	// vLLM endpoint as seen by the Orla container (docker compose service name).
	vllmEndpoint = "http://vllm:8000/v1"

	modelID = "openai:mistralai/Mistral-7B-Instruct-v0.3"

	orlaURL = "http://localhost:8081"
)

func NewOrlaClientWithVllmBackend() (*orla.OrlaClient, *orla.LLMBackend, error) {
	ctx := context.Background()
	client := orla.NewOrlaClient(orlaURL)

	backend, err := client.RegisterBackend(ctx, &orla.RegisterBackendRequest{
		Name:     orlaBackendName,
		Endpoint: vllmEndpoint,
		Type:     "openai",
		ModelID:  modelID,
	})

	if err != nil {
		return nil, nil, fmt.Errorf("failed to register vLLM backend: %w", err)
	}

	return client, backend, nil
}

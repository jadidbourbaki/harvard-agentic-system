package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestCreateConfig(t *testing.T) {
	// Create a temporary directory for test files
	tmpDir := t.TempDir()
	configPath := filepath.Join(tmpDir, "test_config.yaml")

	policy := "aggressive_flush"
	turns := 5
	backend := "http://localhost:30000"
	model := "sglang:mistralai/Mistral-7B-Instruct-v0.3"

	err := createConfig(configPath, policy, turns, backend, model, 100)
	if err != nil {
		t.Fatalf("createConfig failed: %v", err)
	}

	// Verify file was created
	if _, err := os.Stat(configPath); os.IsNotExist(err) {
		t.Fatalf("Config file was not created: %s", configPath)
	}

	// Read and verify contents
	content, err := os.ReadFile(configPath)
	if err != nil {
		t.Fatalf("Failed to read config file: %v", err)
	}

	contentStr := string(content)

	// Check for required fields
	checks := []struct {
		name  string
		value string
	}{
		{"log_format", "log_format: pretty"},
		{"log_level", "log_level: debug"},
		{"mode", "mode: daemon"},
		{"policy", "policy: \"aggressive_flush\""},
		{"backend endpoint", "endpoint: \"http://localhost:30000\""},
		{"model", "model: \"sglang:mistralai/Mistral-7B-Instruct-v0.3\""},
		{"workflow name", "name: \"story_finishing_game\""},
		{"agent profile a", "name: \"story_agent_a\""},
		{"agent profile b", "name: \"story_agent_b\""},
	}

	for _, check := range checks {
		if !strings.Contains(contentStr, check.value) {
			t.Errorf("Config file missing %s: %s", check.name, check.value)
		}
	}

	// Verify correct number of tasks
	taskCount := strings.Count(contentStr, "agent_profile:")
	if taskCount != turns {
		t.Errorf("Expected %d tasks, found %d", turns, taskCount)
	}

	// Verify tasks alternate between agents
	lines := strings.Split(contentStr, "\n")
	taskLines := []string{}
	for _, line := range lines {
		if strings.Contains(line, "agent_profile:") {
			taskLines = append(taskLines, strings.TrimSpace(line))
		}
	}

	if len(taskLines) != turns {
		t.Errorf("Expected %d task lines, found %d", turns, len(taskLines))
	}

	// Check alternation pattern
	for i, line := range taskLines {
		expectedAgent := "story_agent_a"
		if i%2 == 1 {
			expectedAgent = "story_agent_b"
		}
		if !strings.Contains(line, expectedAgent) {
			t.Errorf("Task %d should use %s, but line is: %s", i, expectedAgent, line)
		}
	}
}

func TestCreateConfigWithDifferentPolicies(t *testing.T) {
	tmpDir := t.TempDir()

	policies := []string{"aggressive_flush", "preserve", "preserve_on_small_turns"}

	for _, policy := range policies {
		configPath := filepath.Join(tmpDir, "test_config_"+policy+".yaml")
		err := createConfig(configPath, policy, 3, "http://localhost:30000", "sglang:test-model", 100)
		if err != nil {
			t.Fatalf("createConfig failed for policy %s: %v", policy, err)
		}

		content, err := os.ReadFile(configPath)
		if err != nil {
			t.Fatalf("Failed to read config file for policy %s: %v", policy, err)
		}

		expectedPolicy := "policy: \"" + policy + "\""
		if !strings.Contains(string(content), expectedPolicy) {
			t.Errorf("Config for policy %s does not contain expected policy string: %s", policy, expectedPolicy)
		}
	}
}

func TestCreateConfigWithDifferentTurns(t *testing.T) {
	tmpDir := t.TempDir()

	turnCounts := []int{1, 5, 10, 100}

	for _, turns := range turnCounts {
		configPath := filepath.Join(tmpDir, fmt.Sprintf("test_config_turns_%d.yaml", turns))
		err := createConfig(configPath, "preserve", turns, "http://localhost:30000", "sglang:test-model", 100)
		if err != nil {
			t.Fatalf("createConfig failed for %d turns: %v", turns, err)
		}

		content, err := os.ReadFile(configPath)
		if err != nil {
			t.Fatalf("Failed to read config file for %d turns: %v", turns, err)
		}

		taskCount := strings.Count(string(content), "agent_profile:")
		if taskCount != turns {
			t.Errorf("Expected %d tasks for %d turns, found %d", turns, turns, taskCount)
		}
	}
}

func TestConstructPrompt(t *testing.T) {
	tests := []struct {
		name    string
		context string
		k       int
		want    string
	}{
		{
			name:    "empty context",
			context: "",
			k:       8,
			want:    "We are playing a story finishing game",
		},
		{
			name:    "with context",
			context: "there was a dragon",
			k:       8,
			want:    "Once upon a time there was a dragon",
		},
		{
			name:    "different k value",
			context: "test",
			k:       16,
			want:    "next 16 tokens",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := constructPrompt(tt.context, tt.k)
			if !strings.Contains(got, tt.want) {
				t.Errorf("constructPrompt() = %q, want to contain %q", got, tt.want)
			}
			// Verify k appears in the prompt
			kStr := fmt.Sprintf("%d", tt.k)
			if !strings.Contains(got, kStr) {
				t.Errorf("constructPrompt() should mention k (%d) value", tt.k)
			}
		})
	}
}

func TestCreateConfigFileLocation(t *testing.T) {
	// Test that config file is created in the correct location
	tmpDir := t.TempDir()
	configPath := filepath.Join(tmpDir, "test_config.yaml")

	err := createConfig(configPath, "preserve", 3, "http://localhost:30000", "sglang:test", 100)
	if err != nil {
		t.Fatalf("createConfig failed: %v", err)
	}

	// Verify file exists at specified path
	if _, err := os.Stat(configPath); os.IsNotExist(err) {
		t.Fatalf("Config file was not created at expected path: %s", configPath)
	}
}

func TestCreateConfigInvalidPath(t *testing.T) {
	// Test with invalid path (non-existent directory)
	invalidPath := "/nonexistent/directory/config.yaml"

	err := createConfig(invalidPath, "preserve", 3, "http://localhost:30000", "sglang:test", 100)
	if err == nil {
		t.Error("createConfig should fail with invalid path, but it didn't")
	}
}

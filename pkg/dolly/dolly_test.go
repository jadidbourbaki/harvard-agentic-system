package dolly

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestInstructionsManager(t *testing.T) {
	manager := NewInstructionsManager()
	err := manager.fetch()
	require.NoError(t, err)

	err = manager.parse()
	require.NoError(t, err)

	err = manager.Validate()
	require.NoError(t, err)

	prompts := manager.Prompts()
	require.Greater(t, len(prompts), 0)

	t.Logf("Fetched %d prompts", len(prompts))

	for i := range 10 {
		t.Logf("Prompt %d: %s", i, manager.Prompts()[i])
	}

	for range 10 {
		t.Logf("Random prompt: %s", manager.RandomPrompt())
	}

	for i := len(prompts) - 10; i < len(prompts); i++ {
		t.Logf("Prompt %d: %s", i, prompts[i])
	}
}

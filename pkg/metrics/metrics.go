package metrics

import (
	"sync"
	"time"
)

type Measurement struct {
	Value         float64   `json:"value"`
	TimeCollected time.Time `json:"time_collected"`
}

// MeasurementCollector is a thread-safe collector for measurement samples.
type MeasurementCollector struct {
	mu      sync.Mutex
	samples []Measurement
}

func (c *MeasurementCollector) AddSample(value float64, timeCollected time.Time) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.samples = append(c.samples, Measurement{Value: value, TimeCollected: timeCollected})
}

func (c *MeasurementCollector) Samples() []Measurement {
	c.mu.Lock()
	defer c.mu.Unlock()
	out := make([]Measurement, len(c.samples))
	copy(out, c.samples)
	return out
}

type AgentMetrics struct {
	TTFTMilliseconds    *MeasurementCollector
	TPOTMilliseconds    *MeasurementCollector
	LatencyMilliseconds *MeasurementCollector
}

func NewAgentMetrics() *AgentMetrics {
	return &AgentMetrics{
		TTFTMilliseconds:    &MeasurementCollector{},
		TPOTMilliseconds:    &MeasurementCollector{},
		LatencyMilliseconds: &MeasurementCollector{},
	}
}

func (m *AgentMetrics) ToMap() map[string]any {
	return map[string]any{
		"ttft_ms":    m.TTFTMilliseconds.Samples(),
		"tpot_ms":    m.TPOTMilliseconds.Samples(),
		"latency_ms": m.LatencyMilliseconds.Samples(),
	}
}

# Phase 6 Research Paper Direction (Optional)

## Candidate Topics

1. Long Narrative Consistency in Multi-Scene Story Generation
2. AI Story Memory Systems with Persistent Retrieval and Event Sourcing
3. Narrative State Machines for Deterministic Story Mutation
4. Persistent Character Modeling with Drift and Canon Constraints

## Suggested Evaluation Axes

- timeline accuracy
- character consistency
- canon integrity
- overall consistency score
- token cost per accepted scene
- correction latency (human or agent)

## Minimum Experimental Setup

1. Use benchmark datasets in `datasets/`
2. Evaluate at least 2 LLM providers and 1 heuristic baseline
3. Report per-rule precision/recall/F1
4. Include ablation: without semantic validator, without multi-agent analysis

## Reproducibility Checklist

- versioned dataset files
- fixed seeds where possible
- exact model and endpoint config
- commit hash for each run
- exported metric snapshots

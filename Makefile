.PHONY: judge-demo live forge-example
CASSETTE ?= cassettes/nebius-live.json

# Replays recorded Nemotron responses through the real harness (sandbox + checkers run for real). No key, no network.
judge-demo:
	SF_MODE=replay SF_CASSETTE=$(CASSETTE) python3 harness.py --workers 10

# Live run (NVIDIA build by default; Nebius: SF_BASE_URL=https://api.studio.nebius.com/v1 SF_API_KEY_FILE=... SF_MODEL=...)
live:
	SF_MODE=record SF_CASSETTE=cassettes/live-$$(date +%s).json python3 harness.py --workers 10

forge-example:
	python3 forge.py examples/transcript.json

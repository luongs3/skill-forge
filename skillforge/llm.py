"""OpenAI-compatible chat client with record/replay cassettes.

Env:
  SF_BASE_URL  default https://integrate.api.nvidia.com/v1  (Nebius Token Factory: https://api.tokenfactory.nebius.com/v1)
  SF_MODEL     default nvidia/nemotron-3-super-120b-a12b
  SF_API_KEY   or SF_API_KEY_FILE (default ~/.config/me-secrets/nvidia.txt)
  SF_MODE      live | record | replay   (replay needs no key / network)
  SF_CASSETTE  path to cassette JSON

Cassettes are keyed by (stream, call index), not by prompt hash, so replay
stays deterministic even if a judge's shell prints slightly different output.
"""
import json, os, threading, time, urllib.request, urllib.error

BASE_URL = os.environ.get("SF_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/")
MODEL = os.environ.get("SF_MODEL", "nvidia/nemotron-3-super-120b-a12b")
MODE = os.environ.get("SF_MODE", "record")
CASSETTE = os.environ.get("SF_CASSETTE", "cassettes/run.json")

_lock = threading.Lock()
_tape = {}
_usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}


def _key():
    k = os.environ.get("SF_API_KEY")
    if k:
        return k.strip()
    with open(os.path.expanduser(os.environ.get("SF_API_KEY_FILE", "~/.config/me-secrets/nvidia.txt"))) as f:
        return f.read().strip()


def load_cassette():
    global _tape
    if os.path.exists(CASSETTE):
        with open(CASSETTE) as f:
            _tape = json.load(f)


def save_cassette():
    os.makedirs(os.path.dirname(CASSETTE) or ".", exist_ok=True)
    with _lock, open(CASSETTE, "w") as f:
        json.dump(_tape, f, indent=0, sort_keys=True)


def usage():
    return dict(_usage)


def chat(stream, idx, messages, max_tokens=4096, temperature=0.0):
    key = f"{stream}#{idx}"
    if MODE == "replay" or (MODE == "record" and key in _tape):
        # record mode resumes a crashed run: already-recorded calls are not re-paid
        if key not in _tape:
            raise KeyError(f"cassette miss: {key}")
        return _tape[key]
    body = json.dumps({"model": MODEL, "messages": messages, "temperature": temperature,
                       "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(BASE_URL + "/chat/completions", data=body, headers={
        "Authorization": "Bearer " + _key(), "Content-Type": "application/json"})
    for attempt in range(20):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.load(r)
            break
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            if attempt == 19:
                raise
            time.sleep(min(60, 2 ** attempt + 1) if getattr(e, "code", None) != 429 else 15 * (attempt + 1))
    text = d["choices"][0]["message"].get("content") or ""
    u = d.get("usage") or {}
    with _lock:
        _usage["calls"] += 1
        _usage["prompt_tokens"] += u.get("prompt_tokens", 0)
        _usage["completion_tokens"] += u.get("completion_tokens", 0)
        if MODE == "record":
            _tape[key] = text
    return text

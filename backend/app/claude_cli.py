"""Claude through the local Claude Code CLI (`claude -p`), for the demo.

This runs on the developer's own Claude subscription, on their machine: no API key.
It is for local prototyping only. Anything other people use needs a real Anthropic
API key and the SDK.

Each call is one headless turn with no tools and a JSON Schema, so the answer comes
back as schema-valid JSON in `structured_output`. A call takes ~4-6 s with Haiku.
"""

import json
import logging
import os
import shutil
import subprocess
import tempfile

log = logging.getLogger("uvicorn.error")

MODEL = "haiku"  # the CLI's alias for the current Haiku
EFFORT = "low"  # a structured pick from a short list: little thinking needed, much faster
TIMEOUT_S = 45


class ClaudeUnavailable(RuntimeError):
    pass


def available() -> bool:
    return shutil.which("claude") is not None


def ask(prompt: str, schema: dict, system: str, model: str = MODEL) -> dict:
    """One structured answer from Claude, or ClaudeUnavailable."""
    exe = shutil.which("claude")
    if exe is None:
        raise ClaudeUnavailable("the `claude` CLI is not installed")
    # Run outside the repo (no project CLAUDE.md) and outside any parent Claude Code
    # session (its env vars would make this a nested session).
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDECODE", "CLAUDE_CODE_"))}
    cmd = [
        exe,
        "-p",
        "--model",
        model,
        "--effort",
        EFFORT,
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(schema),
        "--tools",
        "",
        "--no-session-persistence",
        "--system-prompt",
        system,
        prompt,
    ]
    try:
        with tempfile.TemporaryDirectory() as cwd:
            done = subprocess.run(
                cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=TIMEOUT_S
            )
    except subprocess.TimeoutExpired as e:
        raise ClaudeUnavailable(f"claude -p timed out after {TIMEOUT_S}s") from e
    if done.returncode != 0:
        raise ClaudeUnavailable(f"claude -p failed: {done.stderr.strip()[:300]}")
    try:
        out = json.loads(done.stdout)
    except json.JSONDecodeError as e:
        raise ClaudeUnavailable("claude -p returned no JSON") from e
    if out.get("is_error") or not isinstance(out.get("structured_output"), dict):
        raise ClaudeUnavailable(f"claude -p gave no structured answer: {str(out)[:300]}")
    log.info(
        "claude -p %s: %.1fs, %s output tokens",
        model,
        out.get("duration_ms", 0) / 1000,
        out.get("usage", {}).get("output_tokens"),
    )
    return out["structured_output"]

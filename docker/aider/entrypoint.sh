#!/bin/sh
set -eu

cd /workspace

if [ ! -d .git ]; then
  git init >/dev/null 2>&1 || true
fi

git config --local user.email "server-agent@local" >/dev/null 2>&1 || true
git config --local user.name "Server Aider" >/dev/null 2>&1 || true

if [ -n "${LLM_API_KEY:-}" ] && [ -z "${OPENAI_API_KEY:-}" ]; then
  export OPENAI_API_KEY="$LLM_API_KEY"
fi

if [ -n "${LLM_API_BASE:-}" ] && [ -z "${OPENAI_API_BASE:-}" ]; then
  export OPENAI_API_BASE="$LLM_API_BASE"
fi

if [ "${AIDER_TASK_MODE:-interactive}" = "worker" ]; then
  exec python /usr/local/bin/aider-worker.py
fi

exec aider --model "$AIDER_MODEL" --editor-model "$AIDER_EDITOR_MODEL"

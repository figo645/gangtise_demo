#!/usr/bin/env bash

# Shared process lifecycle helpers. This file is sourced by the existing
# public start/stop scripts; their names and invocation contracts stay intact.

resolve_python_bin() {
  local root_dir="$1"
  local requested="${PYTHON_BIN:-}"
  if [[ -n "$requested" ]]; then
    printf '%s\n' "$requested"
    return 0
  fi
  local candidate
  for candidate in "$root_dir/.venv/bin/python" "$root_dir/venv/bin/python" "$root_dir/env/bin/python"; do
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  printf '%s\n' "python3"
}

runtime_pid_matches() {
  local pid="$1"
  local expected="$2"
  ps -p "$pid" -o command= 2>/dev/null | grep -F -- "$expected" >/dev/null 2>&1
}

wait_for_runtime_process() {
  local pid="$1"
  local expected="$2"
  local timeout_seconds="${3:-30}"
  local elapsed=0
  while (( elapsed < timeout_seconds )); do
    if ! kill -0 "$pid" 2>/dev/null; then
      return 1
    fi
    if runtime_pid_matches "$pid" "$expected"; then
      return 0
    fi
    sleep 1
    ((elapsed += 1))
  done
  return 1
}

start_runtime_sidecar() {
  local root_dir="$1"
  local python_bin="$2"
  local mode="$3"
  local pid_file="$4"
  local log_file="$5"
  local environment="$6"
  local entry="$root_dir/src/process_${mode}.py"

  if [[ -f "$pid_file" ]]; then
    local existing_pid
    existing_pid="$(cat "$pid_file" 2>/dev/null || true)"
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null && runtime_pid_matches "$existing_pid" "$entry"; then
      echo "${mode} is already running (PID: ${existing_pid})."
      return 0
    fi
    rm -f "$pid_file"
  fi

  local python_path="$root_dir"
  if [[ -n "${PYTHONPATH:-}" ]]; then
    python_path="$root_dir:$PYTHONPATH"
  fi
  nohup env PYTHONPATH="$python_path" PYTHONUNBUFFERED=1 DEBUG=0 GANGTISE_RUNTIME_ENV="$environment" "$python_bin" "$entry" \
    >"$log_file" 2>&1 < /dev/null &
  local child_pid=$!
  echo "$child_pid" > "$pid_file"
  sleep 1
  if ! kill -0 "$child_pid" 2>/dev/null; then
    rm -f "$pid_file"
    echo "${mode} failed to start. Check ${log_file}" >&2
    return 1
  fi
  echo "Started ${mode} (PID: ${child_pid})."
}

stop_runtime_sidecar() {
  local pid_file="$1"
  local entry="$2"
  local label="$3"
  [[ -f "$pid_file" ]] || return 0
  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null || ! runtime_pid_matches "$pid" "$entry"; then
    rm -f "$pid_file"
    return 0
  fi
  kill "$pid" 2>/dev/null || true
  for _ in 1 2 3 4 5; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$pid_file"
  echo "Stopped ${label} (PID: ${pid})."
}

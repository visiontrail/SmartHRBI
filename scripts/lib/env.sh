#!/usr/bin/env bash

trim_env_token() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

load_env_file() {
  local env_file="$1"
  if [[ ! -f "$env_file" ]]; then
    echo "[env] Env file not found: $env_file" >&2
    return 1
  fi

  local raw_line line key value
  while IFS= read -r raw_line || [[ -n "$raw_line" ]]; do
    line="$(trim_env_token "$raw_line")"
    if [[ -z "$line" || "${line:0:1}" == "#" || "$line" != *=* ]]; then
      continue
    fi

    key="$(trim_env_token "${line%%=*}")"
    value="$(trim_env_token "${line#*=}")"
    if [[ ! "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      echo "[env] Invalid env key in $env_file: $key" >&2
      return 1
    fi

    if [[ ${#value} -ge 2 ]] && {
      [[ "${value:0:1}" == "\"" && "${value: -1}" == "\"" ]] ||
        [[ "${value:0:1}" == "'" && "${value: -1}" == "'" ]]
    }; then
      value="${value:1:${#value}-2}"
    fi

    export "$key=$value"
  done <"$env_file"
}

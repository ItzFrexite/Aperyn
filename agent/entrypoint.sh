#!/bin/sh
set -eu

data_dir=${APERYN_AGENT_DATA_DIR:-/agent-data}
runtime_uid=${APERYN_AGENT_UID:-1000}
runtime_gid=${APERYN_AGENT_GID:-1000}
tags_url=${APERYN_OLLAMA_TAGS_URL:-http://host.docker.internal:11435/api/tags}
show_url=${APERYN_OLLAMA_SHOW_URL:-${tags_url%/api/tags}/api/show}
base_url=${APERYN_OLLAMA_BASE_URL:-http://host.docker.internal:11435/v1}
requested_context=${APERYN_AGENT_CONTEXT_LIMIT:-98304}
secret_file="$data_dir/server.password"
config_file="$data_dir/opencode.json"

case "$runtime_uid:$runtime_gid" in
  *[!0-9:]*|:*|*:) echo 'Invalid Aperyn Agent UID/GID' >&2; exit 1 ;;
esac
[ "$requested_context" -ge 4096 ] 2>/dev/null && [ "$requested_context" -le 1048576 ] 2>/dev/null || requested_context=98304
[ "$runtime_uid" -gt 0 ] && [ "$runtime_gid" -gt 0 ] || { echo 'Aperyn Agent refuses to run tasks as root' >&2; exit 1; }

mkdir -p "$data_dir" "$data_dir/home" "$data_dir/xdg-data" "$data_dir/xdg-config" "$data_dir/config"
chown -R "$runtime_uid:$runtime_gid" "$data_dir"

runtime_group=$(awk -F: -v gid="$runtime_gid" '$3 == gid {print $1; exit}' /etc/group)
if [ -z "$runtime_group" ]; then
  runtime_group=aperynagent
  addgroup -g "$runtime_gid" "$runtime_group"
fi
runtime_user=$(awk -F: -v uid="$runtime_uid" '$3 == uid {print $1; exit}' /etc/passwd)
if [ -z "$runtime_user" ]; then
  runtime_user=aperynagent
  adduser -D -H -u "$runtime_uid" -G "$runtime_group" -h "$data_dir/home" -s /bin/sh "$runtime_user"
fi

if [ ! -s "$secret_file" ]; then
  umask 077
  secret_tmp="$secret_file.tmp"
  dd if=/dev/urandom bs=48 count=1 2>/dev/null | base64 | tr -d '\n' > "$secret_tmp"
  printf '\n' >> "$secret_tmp"
  chown "$runtime_uid:$runtime_gid" "$secret_tmp"
  mv "$secret_tmp" "$secret_file"
fi
chmod 0600 "$secret_file"
export OPENCODE_SERVER_USERNAME=aperyn
export OPENCODE_SERVER_PASSWORD="$(tr -d '\r\n' < "$secret_file")"

tags=''
attempt=0
while [ "$attempt" -lt 30 ]; do
  tags=$(wget -qO- "$tags_url" 2>/dev/null || true)
  if printf '%s' "$tags" | jq -e '.models | type == "array"' >/dev/null 2>&1; then break; fi
  attempt=$((attempt + 1))
  sleep 1
done

if printf '%s' "$tags" | jq -e '.models | type == "array"' >/dev/null 2>&1; then
  # OpenCode can only report meaningful context remaining when each model has
  # a real model.limit.context. Ollama exposes that limit in /api/show model_info.
  enriched_tags=$tags
  for encoded_name in $(printf '%s' "$tags" | jq -r '.models[]? | (.name // .model // "") | select(length > 0) | @base64'); do
    model_name=$(printf '%s' "$encoded_name" | base64 -d)
    show_payload=$(jq -nc --arg model "$model_name" '{model:$model,verbose:true}')
    show_data=$(wget -qO- --header='Content-Type: application/json' --post-data="$show_payload" "$show_url" 2>/dev/null || true)
    architecture_context=$(printf '%s' "$show_data" | jq -r '
      ([((.model_info // {}) | to_entries[])
        | select((.key | ascii_downcase) == "context_length" or (.key | ascii_downcase | endswith(".context_length")))
        | .value | tonumber?] | map(select(. > 0)) | first) // 0
    ' 2>/dev/null || printf '0')
    # An explicit Modelfile num_ctx is the configured runtime context and must
    # win over the Agent fallback. Otherwise use the architecture maximum,
    # bounded by the configurable Agent target.
    configured_context=$(printf '%s' "$show_data" | sed -nE 's/.*(^|[[:space:]])num_ctx[[:space:]]+([0-9]+).*/\2/p' | head -n1)
    context_limit=${configured_context:-0}
    if [ "$context_limit" -le 0 ] 2>/dev/null; then
      context_limit=$requested_context
      if [ "${architecture_context:-0}" -gt 0 ] 2>/dev/null && [ "$architecture_context" -lt "$context_limit" ] 2>/dev/null; then
        context_limit=$architecture_context
      fi
    fi
    enriched_tags=$(printf '%s' "$enriched_tags" | jq --arg name "$model_name" --argjson limit "${context_limit:-0}" '
      .models |= map(if (.name // .model // "") == $name then . + {aperyn_context: $limit} else . end)
    ')
  done
  config_tmp="$config_file.tmp"
  printf '%s' "$enriched_tags" | jq --arg base "$base_url" '
    {
      "$schema": "https://opencode.ai/config.json",
      autoupdate: false,
      share: "disabled",
      provider: {
        ollama: {
          npm: "@ai-sdk/openai-compatible",
          name: "Aperyn Ollama",
          options: {baseURL: $base},
          models: (reduce (.models[]?) as $model ({};
            ($model.name // $model.model // "") as $name |
            if $name == "" then . else .[$name] = {
              name: $name,
              limit: {context: ($model.aperyn_context // 0), output: 0},
              options: {num_ctx: ($model.aperyn_context // 0)}
            } end))
        }
      },
      permission: {
        read: {
          "*": "allow",
          "**/.ssh/**": "deny", "**/.gnupg/**": "deny",
          "**/.aws/**": "deny", "**/.kube/**": "deny",
          "**/.docker/**": "deny", "**/.config/gh/**": "deny",
          "**/.netrc": "deny", "**/.npmrc": "deny", "**/.pypirc": "deny",
          "*.env": "deny", "*.env.*": "deny", "*.env.example": "allow"
        },
        glob: "allow", grep: "allow", list: "allow",
        todoread: "allow", todowrite: "allow",
        bash: {
          "*": "ask",
          "pwd": "allow", "ls": "allow", "ls *": "allow", "cd *": "allow",
          "git status": "allow", "git status *": "allow"
        },
        edit: "ask", write: "ask", task: "ask",
        webfetch: "ask", websearch: "allow", external_directory: "deny"
      }
    }
  ' > "$config_tmp"
  chown "$runtime_uid:$runtime_gid" "$config_tmp"
  chmod 0600 "$config_tmp"
  mv "$config_tmp" "$config_file"
elif [ ! -s "$config_file" ]; then
  echo 'Aperyn Agent could not read the Ollama model list and has no existing configuration.' >&2
  exit 1
fi

# External provider connections are written by the authenticated WebUI to a
# runtime-only fragment. Merge them without ever embedding credentials in this
# configuration—the fragment references separate 0600 key files instead.
provider_fragment="$data_dir/provider-connections.json"
if [ -s "$provider_fragment" ] && jq -e '.provider | type == "object"' "$provider_fragment" >/dev/null 2>&1; then
  config_tmp="$config_file.providers.tmp"
  jq -s '.[0] as $base | .[1] as $extra | $base * {provider:(($base.provider // {}) * ($extra.provider // {}))}' \
    "$config_file" "$provider_fragment" > "$config_tmp"
  chown "$runtime_uid:$runtime_gid" "$config_tmp"
  chmod 0600 "$config_tmp"
  mv "$config_tmp" "$config_file"
fi

cd /workspace
exec su-exec "$runtime_uid:$runtime_gid" env \
  HOME="$data_dir/home" \
  XDG_DATA_HOME="$data_dir/xdg-data" \
  XDG_CONFIG_HOME="$data_dir/xdg-config" \
  OPENCODE_CONFIG="$config_file" \
  OPENCODE_CONFIG_DIR="$data_dir/config" \
  opencode "$@"

#!/usr/bin/env bash
set -euo pipefail

city="${1:-@auto_location}"
encoded_city="${city// /%20}"
curl --fail --silent --show-error --max-time 20 \
  "https://wttr.in/${encoded_city}?format=%l:+%c+%t,+feels+like+%f,+humidity+%h,+wind+%w&lang=zh"

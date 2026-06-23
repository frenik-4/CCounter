#!/bin/bash
# Skickar en persistent notis till Home Assistant när ccounter kraschar.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "notify_ha_failure: .env saknas ($ENV_FILE)" >&2
    exit 1
fi

HA_URL=$(grep -E '^HA_URL=' "$ENV_FILE" | cut -d= -f2-)
HA_TOKEN=$(grep -E '^HA_TOKEN=' "$ENV_FILE" | cut -d= -f2-)

if [[ -z "$HA_URL" || -z "$HA_TOKEN" ]]; then
    echo "notify_ha_failure: HA_URL eller HA_TOKEN saknas i .env" >&2
    exit 1
fi

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

curl -s -o /dev/null -X POST "${HA_URL}/api/services/persistent_notification/create" \
  -H "Authorization: Bearer ${HA_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"title\": \"CCounter kraschade\",
    \"message\": \"Appen startades om automatiskt. ${TIMESTAMP}\",
    \"notification_id\": \"ccounter_failure\"
  }"

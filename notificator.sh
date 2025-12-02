#!/bin/bash

# Credenziali Elasticsearch
ES_USER="elastic"
ES_PASS="RX+tdMrgfnDpsKaukNd6"
ES_HOST="http://localhost:9200"
WEBHOOK_URL="https://prod-170.westeurope.logic.azure.com:443/workflows/ef919fceece447279abe18a26b25e45e/triggers/manual/paths/invoke?api-version=2016-06-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=kNBNx-zUa0Ap5XrBbCBGqjYw8-pUymqiGP4SvEEeQpg"
INDEX="alerts-metricbeat"

# Funzione per inviare alert a Teams
test_send_teams_alert() {
  payload='{
      "attachments": [
          {
          "contentType": "application/vnd.microsoft.card.adaptive",
          "content": {
              "type": "AdaptiveCard",
              "version": "1.3",
              "body": [
              {
                  "type": "TextBlock",
                  "text": "🔔 ALLARME DA NODO ACC",
                  "weight": "Bolder",
                  "size": "Large",
                  "color": "Attention",
                  "wrap": true
              },
              {
                  "type": "TextBlock",
                  "text": "Un evento critico è stato rilevato nei tuoi dati Metricbeat.",
                  "wrap": true
              },
              {
                  "type": "FactSet",
                  "facts": [
                  {"title": "Indice:", "value": "metricbeat-*"},
                  {"title": "Tipo evento:", "value": "CPU Usage Critica"},
                  {"title": "Valore:", "value": "92%"}
                  ]
              }
              ],
              "actions": [
              {
                  "type": "Action.OpenUrl",
                  "title": "Apri Elastic Search Server",
                  "url": "http://10.27.199.243:5601/app/metrics"
              }
              ]
          }
          }
      ]
  }'

  curl -X POST -H "Content-Type: application/json" -d "$payload" "$WEBHOOK_URL"
}

check_alerts_after_timestamp() {
  echo "Checking for new alerts in Elasticsearch..."

  # Timestamp ultima esecuzione
  STATE_FILE="/tmp/last_alert_check.txt"
  LAST_TS=$(cat $STATE_FILE 2>/dev/null || echo "1970-01-01T00:00:00Z")

  # Query Elasticsearch: documenti più recenti
  RESULT=$(curl -s -u $ES_USER:$ES_PASS "$ES_HOST/alerts-metricbeat/_search" -H 'Content-Type: application/json' -d "
  {
    \"query\": {
      \"range\": {
        \"@timestamp\": { \"gt\": \"$LAST_TS\" }
      }
    },
    \"sort\": [{\"@timestamp\": \"asc\"}],
    \"size\": 10
  }")

  # Aggiorna timestamp ultima esecuzione
  NEW_LAST_TS=$(echo "$RESULT" | jq -r '.hits.hits[-1]._source["@timestamp"]')
  echo "$NEW_LAST_TS" > $STATE_FILE

  COUNT=$(echo "$RESULT" | jq '.hits.total.value')
}

send_teams_card() {

  if [ "$COUNT" -gt 0 ]; then

    # Costruisci card dettagliata
    CARDS=""
    for i in $(seq 0 $(($(echo "$RESULT" | jq '.hits.hits | length') - 1))); do
      TS=$(echo "$RESULT" | jq -r ".hits.hits[$i]._source['@timestamp']")
      HOST=$(echo "$RESULT" | jq -r ".hits.hits[$i]._source.host.name // \"N/A\"")
      EVENT=$(echo "$RESULT" | jq -r ".hits.hits[$i]._source.event.dataset // \"N/A\"")
      VALUE=$(echo "$RESULT" | jq -r ".hits.hits[$i]._source.system.network.in.bytes // 0")

      CARDS+=$(cat <<'EOF'
      {
        "activityTitle": "Host: $HOST",
        "activitySubtitle": "Event: $EVENT",
        "facts": [
          { "name": "Timestamp", "value": "$TS" },
          { "name": "In Bytes", "value": "$VALUE" }
        ],
        "markdown": true
      },
EOF
      )
    done

    # Rimuovi l'ultima virgola
    CARDS=$(echo "$CARDS" | sed '$ s/,$//')

    PAYLOAD=$(cat <<EOF
    {
      "@type": "MessageCard",
      "@context": "https://schema.org/extensions",
      "summary": "Elasticsearch Metricbeat Alerts",
      "themeColor": "FF0000",
      "title": "Metricbeat Alerts: $COUNT new document(s)",
      "sections": [
        $CARDS
      ]
    }
EOF
    )

    # Invia su Teams
    curl -s -H "Content-Type: application/json" -d "$PAYLOAD" "$WEBHOOK_URL"

  fi
}


get_unsent_alerts() {
  echo "Retrieving unsent alerts from Elasticsearch..."

  # --- Recupera alert non ancora inviati ---
  alerts=$(curl -s -u "$ES_USER:$ES_PASS" -X GET "$ES_URL/$INDEX/_search?size=50" -H 'Content-Type: application/json' -d '{
    "_source": ["@timestamp","host.name","event.dataset","system.network.in.bytes","system.network.out.bytes"],
    "query": {
      "bool": {
        "must_not": {
          "exists": { "field": "sent" }
        }
      }
    }
  }')
}


# --- Loop sugli alert ---
echo "$alerts" | jq -c '.hits.hits[]' | while read alert; do
    id=$(echo "$alert" | jq -r '._id')
    timestamp=$(echo "$alert" | jq -r '._source["@timestamp"]')
    host=$(echo "$alert" | jq -r '._source.host.name')
    event=$(echo "$alert" | jq -r '._source.event.dataset')
    in_bytes=$(echo "$alert" | jq -r '._source.system.network.in.bytes // 0')
    out_bytes=$(echo "$alert" | jq -r '._source.system.network.out.bytes // 0')

    # --- Adaptive Card JSON ---
    adaptive_card=$(cat <<'EOF'
{
  "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
  "type": "AdaptiveCard",
  "version": "1.5",
  "body": [
    {
      "type": "Container",
      "style": "emphasis",
      "bleed": true,
      "items": [
        {
          "type": "TextBlock",
          "text": "🔔 Metricbeat Alert!",
          "weight": "Bolder",
          "size": "Large",
          "color": "Attention"
        },
        {
          "type": "TextBlock",
          "text": "Host: PLACEHOLDER_HOST",
          "wrap": true,
          "weight": "Bolder",
          "color": "Good"
        },
        {
          "type": "FactSet",
          "facts": [
            {"title": "Event:", "value": "PLACEHOLDER_EVENT"},
            {"title": "Timestamp:", "value": "PLACEHOLDER_TIMESTAMP"},
            {"title": "In Bytes:", "value": "PLACEHOLDER_IN"},
            {"title": "Out Bytes:", "value": "PLACEHOLDER_OUT"}
          ]
        }
      ]
    }
  ]
}
EOF
)

    # Sostituisci placeholder con valori reali
    adaptive_card=$(echo "$adaptive_card" | sed \
        -e "s/PLACEHOLDER_HOST/$host/" \
        -e "s/PLACEHOLDER_EVENT/$event/" \
        -e "s/PLACEHOLDER_TIMESTAMP/$timestamp/" \
        -e "s/PLACEHOLDER_IN/$in_bytes/" \
        -e "s/PLACEHOLDER_OUT/$out_bytes/")

    # --- Crea payload per Teams ---
    payload=$(cat <<EOF
{
  "attachments": [
    {
      "contentType": "application/vnd.microsoft.card.adaptive",
      "content": $adaptive_card
    }
  ]
}
EOF
)

    # --- Invia alert a Teams ---
    curl -s -X POST -H "Content-Type: application/json" -d "$payload" "$WEBHOOK_URL"

    # --- Aggiorna l'alert in Elasticsearch come "inviato" ---
    curl -s -u "$ES_USER:$ES_PASS" -X POST "$ES_URL/$INDEX/_update/$id" -H 'Content-Type: application/json' -d '{
      "doc": {
        "sent": true
      }
    }'

done

#!/usr/bin/env python3

import traceback
import requests
import json
import os, re
from datetime import datetime
from filelock import FileLock
from adaptivecards import icons_base64
import pendulum

# imposta lingua italiana
pendulum.set_locale('it')

# import sys
# sys.exit(0)


# --- Configurazioni ---
KIBANA_URL = "http://127.0.0.1:5601"
ES_URL = "http://127.0.0.1:9200"
ES_USER = "elastic"
ES_PASS = "RX+tdMrgfnDpsKaukNd6"
INDEX = "alerts-metricbeat"

WEBHOOK_URL={
    "Riunione con GM": "https://defaultc187ee014e4e40c8b342f82c8d6994.21.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/41955eb22a2644ba90fb27ff4368a850/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=dQYSAtmMm-ijfRB_ZwrATvxELZwp7zSvuI0r1Jd-iSk",
    "ELK TML2":        "https://defaultc187ee014e4e40c8b342f82c8d6994.21.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/afe6d721dd254756bbfec11493a603de/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=Hzo4-hAoxTUDLcWdI7jR4PT8NrZJjkdde1C_YMwS00Y",
    "ELK TML":         "https://defaultc187ee014e4e40c8b342f82c8d6994.21.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/230aead804b64939a48eba174be7815b/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=scJ7wy8WUDsvB9Cad5aM_IOV611rZagRrRXXWswj4CQ"
}

def get_cardTypeId(data):
    ret = []
    for field in ("title", "team_group_name", "nodo", "clone"):
        ret.append(data[field].lower().replace(":","").replace(" ", "_"))
    return "-".join(ret)

def load_card(card, data:dict={}) -> json:
    with open(os.path.join(f"{os.path.dirname(os.path.abspath(__file__))}/adaptivecards", f"{card}.json"), "r", encoding="utf-8") as f:
        content = f.read()

    data["cardTypeId"] = get_cardTypeId(data)

    for k,v in data.items():
        # print(k, v)
        if isinstance(v, str):
            print("vvvvvvvvvvvvvvvvvv", k, v, "==============>", v.encode('unicode_escape').decode('utf-8'))
            try:
                content = re.sub(fr'\$\{{\$root.{k}\}}', f'{v.encode('unicode_escape').decode('utf-8')}', content)
            except:
                print(f"??????????????????????? {v}")
                content = re.sub(fr'\$\{{\$root.{k}\}}', f'{v}', content)
        elif isinstance(v, bool):
            content = re.sub(fr'"\$\{{\$root.{k}\}}"', str(v).lower(), content)
        else:
            assert False, f"load_card: {type(v)} non capito!"

    print(content)

    return json.loads(content)

def remove_proxy():
    # Rimuove le variabili di proxy comuni
    for var in ["HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"]:
        if var in os.environ:
            del os.environ[var]

remove_proxy()

def teams_send2(team_group_name: str, card="simplecard", subdescr_visible=False, **kwargs):
    """ nuova versione di adaptive cards"""

    kwargs["icon"] = kwargs["icon"].replace("\n", "")
    kwargs["subdescr_visible"] = subdescr_visible

    # su Teams non funziona isVisible allora:
    kwargs["subdescr"] = kwargs.get("subdescr", "")
    kwargs["subdescr_spacing"] = "Default" if subdescr_visible else "None"

    kwargs["team_group_name"] = team_group_name # per cardTypeId

    if "link" not in kwargs:
        kwargs["link"] = "http://10.27.199.243"

    adaptive_card = load_card(card=card, data=kwargs)

    print(json.dumps(adaptive_card, indent=2)) # , ensure_ascii=False)) # GGG

    payload = {
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": adaptive_card
            }
        ]
    }

    proxies = {
        "http": "http://10.27.199.10:3128",
        "https": "http://10.27.199.10:3128"
    }

    # --- Invia a Teams ---
    r = requests.post(WEBHOOK_URL[team_group_name], json=payload, timeout=10, proxies=proxies)
    print(f"Teams response: {r.status_code}")
    print(f"{datetime.now()}: nuovo Alert inviato a Teams {team_group_name} ✔")


def get_unsent():
    # --- Query: prendi gli alert non ancora inviati ---
    query = {
        "query": {
            "bool": {
                "must_not": {
                    "exists": {"field": "sent"}
                }
            }
        },
        "size": 50
    }
    response = requests.post(
        f"{ES_URL}/{INDEX}/_search",
        auth=(ES_USER, ES_PASS),
        headers={"Content-Type": "application/json"},
        data=json.dumps(query)
    )
    # print(f"Elasticsearch response: {response.status_code}", response.text, response)
    hits = response.json().get("hits", {}).get("hits", [])
    return hits

def cpu_metric_threshold(timestamp, nodo, clone, reason, **resto):
    teams_send2(
        team_group_name="ELK TML", 
        icon=icons_base64.cpu, 
        title="Utilizzo CPU", 
        descr="L'utilizzo della CPU ha superato il 99%", 
        date=timestamp, 
        nodo=nodo, 
        clone=clone
    )

def disc_metric_threshold(timestamp, nodo, clone, disco, reason, groups="_,unknown", **resto):
    teams_send2(
        team_group_name="ELK TML", 
        icon=icons_base64.disco, 
        title="Disco pieno", 
        descr=f"L'occupazione del disco {disco} ha superato il 90%", 
        date=timestamp, 
        nodo=nodo, 
        clone=clone
    )

def raid_maintenance(timestamp, nodo, clone, reason, system_raid_sync_action, system_raid_level, system_raid_name,  **resto):
    teams_send2(
        team_group_name="ELK TML", 
        icon=icons_base64.raid, 
        title=f"RAID in **{system_raid_sync_action.upper()}**", 
        descr=f"I dischi del RAID di livello {system_raid_level} sul dispositivo {system_raid_name} sono in {system_raid_sync_action}, e stanno riallineando i dati o ricostruendo la parità.", 
        date=timestamp, 
        nodo=nodo, 
        clone=clone, 
        link="http://10.27.199.243/app/dashboards#/view/8f8d6d5a-f265-4b61-8034-07594acffb75"
    )

def system_service_failed(timestamp, nodo, clone, reason, system_service_name, **resto):
    if system_service_name.endswith(".service"):
        system_service_name = system_service_name[:-len(".service")]
    system_service_name = system_service_name.upper()

    teams_send2(
        team_group_name="ELK TML", 
        icon=icons_base64.service,
        title=f"**{system_service_name}**", 
        descr=f"Il servizio *{system_service_name}* é fallito",
        date=timestamp, 
        nodo=nodo, 
        clone=clone
    )

def nv_shutdown(timestamp, nodo, clone, reason, log_file_path, debug_message, **resto):
    teams_send2(
        team_group_name="ELK TML", 
        icon=icons_base64.cuore,
        title="Shutdown NV",
        descr=f"Contenuto {log_file_path}:",
        subdescr=debug_message.encode('unicode_escape').decode('utf-8'),
        subdescr_visible=True,
        date=timestamp, 
        nodo=nodo, 
        clone=clone
    )

def main(hits):
    # --- Loop sugli alert ---
    for hit in hits:
        src = hit["_source"]

        # {'rule': 'Memory Metric threshold', '@timestamp': '2025-11-18T23:32:44.020Z', 'host': 'com5-terni', 'date': '2025-11-18T23:32:43.440Z', 'reason': 'system.memory.used.pct is 96.5% in the last 1 min for com5-terni. Alert when above 90%.'}

        # crea un oggetto datetime pendulum per formato pretty
        dt = pendulum.parse(src["timestamp"])
        # src["timestamp"] = dt.format('dddd D MMMM YYYY, HH:mm:ss') # .encode('unicode_escape').decode('utf-8')
        src["timestamp"] = dt.format('D/M/YYYY, HH:mm:ss') # .encode('unicode_escape').decode('utf-8')

        print("hit=", json.dumps(hit, indent=2))

        groups={"subdescr_visible": False}

        if "group" in src:
            for group in eval(src.get("group","") + ","):
                assert "field" in group and "value" in group, f"Invalid group format in alert. {group}"
                locals().update(group)
                groups[group["field"].replace(".", "_")] = group["value"]

        print("groups=", json.dumps(groups, indent=2))

        notify=eval(src.get("rule", "").replace(" ", "_").lower())

        host = src.get("host", "unknown-unknown-unknown")
        if host=="elasticsearch":
            nodo="elasticsearch"
            clone="Mermec"
        else:
            try:
                nodo, clone = host.split("-")[-2:]
            except Exception as e:
                print(e)
                print(host)
                nodo = host
                clone = "unknown"

        clone=clone.upper() # tutto maiuscolo => Gallarate
        nodo=nodo.upper() # tutto maiuscolo => TML0

        try:
            if notify: 
                notify(nodo=nodo, clone=clone, **groups, **src)
            else:
                print(f"Nessuna notifica per la regola: {src.get('rule','')}")
        except Exception as e:
            print(f"Errore durante l'invio della notifica per la regola {src.get('rule','')}: {e}")
            traceback.print_exc()

        # timestamp = src.get("@timestamp", "")
        # host = src.get("host", "unknown")
        # event = src.get("event", {}).get("dataset", "")
        # in_bytes = src.get("system.network.in.bytes", 0)
        # out_bytes = src.get("system.network.out.bytes", 0)
        # # teams_send(host, event, timestamp, in_bytes, out_bytes)
        # # Alert da inviare: Host=com5-terni, Event=, In=0, Out=0
        # print(f"Alert da inviare: Host={host}, Event={event}, In={in_bytes}, Out={out_bytes}")

        clean_alert(hit)

def clean_alert(hit):
        # --- Marca l’alert come inviato ---
        doc_id = hit["_id"]
        requests.post(
            f"{ES_URL}/{INDEX}/_update/{doc_id}",
            auth=(ES_USER, ES_PASS),
            headers={"Content-Type": "application/json"},
            json={"doc": {"sent": True}}
        )

###############################################################

lock = FileLock("/tmp/elastic_notificator.lock")

with lock:
    hits = get_unsent()

    if hits:
        main(hits)
        print(f"{datetime.now()}: Invio completato ✔")

    else:
        print(f"{datetime.now()}: Nessun alert nuovo da inviare")


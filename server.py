import os
import threading
import time
from datetime import datetime

import requests
from flask import Flask, jsonify, send_from_directory

from roblox_tracker import (
    GROUP_ID,
    INTERVALO_SEGUNDOS,
    FUSO_HORARIO,
    carregar_cache,
    salvar_cache,
    formatar_data,
    obter_icones_places,
)

PASTA = os.path.dirname(os.path.abspath(__file__))
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
MAX_EVENTOS = 200
MAX_HISTORICO = 288

app = Flask(__name__)
trava = threading.Lock()
cache = carregar_cache()
eventos = cache.get("_eventos", [])
historico = cache.get("_historico", {})
estado = {
    "jogos": [],
    "atualizado_em": None,
    "proxima": None,
    "erro": None,
    "verificando": False,
}


def agora_texto():
    return datetime.now(FUSO_HORARIO).strftime("%d/%m/%Y %H:%M:%S")


def registrar(tipo, texto, jogo):
    eventos.insert(0, {"quando": agora_texto(), "tipo": tipo, "texto": texto, "jogo": jogo})
    del eventos[MAX_EVENTOS:]


def coletar_place(place, nome_jogo, icones):
    p_id = place.get("id")
    p_name = place.get("name", "Unnamed")
    criado = None
    atualizado = None
    raw_updated = None
    raw_name = p_name
    raw_description = ""

    try:
        res = requests.get(
            f"https://economy.roblox.com/v2/assets/{p_id}/details",
            headers=HEADERS,
            timeout=20,
        )
        if res.status_code == 200:
            dados = res.json()
            raw_updated = dados.get("Updated")
            raw_name = dados.get("Name", p_name)
            raw_description = dados.get("Description", "")
            criado = formatar_data(dados.get("Created", "N/A"))
            atualizado = formatar_data(raw_updated or "N/A")
    except Exception:
        pass

    chave = str(p_id)
    anterior = cache.get(chave)

    if anterior:
        if raw_updated and anterior.get("updated") != raw_updated:
            registrar("patch", f"Novo patch em {raw_name}", nome_jogo)
        if anterior.get("name") != raw_name:
            registrar("nome", f"Nome mudou de \"{anterior.get('name')}\" para \"{raw_name}\"", nome_jogo)
        if anterior.get("description") != raw_description:
            registrar("descricao", f"Descrição de {raw_name} foi alterada", nome_jogo)

    cache[chave] = {"updated": raw_updated, "name": raw_name, "description": raw_description}

    return {
        "id": p_id,
        "nome": raw_name,
        "descricao": raw_description,
        "criado": criado,
        "atualizado": atualizado,
        "imagem": icones.get(p_id),
    }


def coletar():
    url = f"https://games.roblox.com/v2/groups/{GROUP_ID}/games?accessFilter=All&limit=100"
    res = requests.get(url, headers=HEADERS, timeout=20)
    res.raise_for_status()
    jogos = res.json().get("data", [])

    ids = [str(j.get("id")) for j in jogos]
    stats = {}
    if ids:
        res_stats = requests.get(
            f"https://games.roblox.com/v1/games?universeIds={','.join(ids)}",
            headers=HEADERS,
            timeout=20,
        )
        if res_stats.status_code == 200:
            for item in res_stats.json().get("data", []):
                stats[item.get("id")] = item

    resultado = []
    for jogo in jogos:
        uid = jogo.get("id")
        nome = jogo.get("name")
        s = stats.get(uid, {})
        jogando = s.get("playing")
        visitas = s.get("visits")

        chave_visitas = f"visitas_{uid}"
        registro = cache.get(chave_visitas) or {}
        ultima = registro.get("ultima")
        novas = registro.get("novas")
        if visitas is not None:
            anterior_visitas = registro.get("visitas")
            if anterior_visitas is not None and visitas > anterior_visitas:
                ultima = agora_texto()
                novas = visitas - anterior_visitas
            cache[chave_visitas] = {"visitas": visitas, "ultima": ultima, "novas": novas}

        serie = historico.setdefault(str(uid), [])
        if jogando is not None:
            serie.append([int(time.time()), jogando])
            del serie[:-MAX_HISTORICO]

        item = {
            "id": uid,
            "nome": nome,
            "jogando": jogando,
            "visitas": visitas,
            "ultima_visita": ultima,
            "ultima_visita_novas": novas,
            "historico": serie,
            "places": [],
            "erro": None,
        }

        try:
            rp = requests.get(
                f"https://develop.roblox.com/v1/universes/{uid}/places?limit=100",
                headers=HEADERS,
                timeout=20,
            )
            if rp.status_code == 200:
                dados = rp.json()
                places = dados.get("data", []) if isinstance(dados, dict) else []
                icones = obter_icones_places([p.get("id") for p in places], HEADERS)

                for place in places:
                    item["places"].append(coletar_place(place, nome, icones))
                    time.sleep(0.3)

                chave_universo = f"universo_{uid}_places"
                atuais = [str(p.get("id")) for p in places]
                anteriores = cache.get(chave_universo)
                if anteriores is not None:
                    for pid in atuais:
                        if pid not in anteriores:
                            registrar("place+", f"Place {pid} adicionado ao universo", nome)
                    for pid in anteriores:
                        if pid not in atuais:
                            registrar("place-", f"Place {pid} removido do universo", nome)
                cache[chave_universo] = atuais
            else:
                item["erro"] = f"Erro HTTP {rp.status_code} ao buscar os places"
        except Exception as e:
            item["erro"] = str(e)

        resultado.append(item)
        time.sleep(0.5)

    cache["_eventos"] = eventos
    cache["_historico"] = historico
    salvar_cache(cache)
    return resultado


def atualizar():
    if not trava.acquire(blocking=False):
        return
    try:
        estado["verificando"] = True
        estado["jogos"] = coletar()
        estado["atualizado_em"] = agora_texto()
        estado["erro"] = None
    except Exception as e:
        estado["erro"] = str(e)
    finally:
        estado["verificando"] = False
        estado["proxima"] = int(time.time()) + INTERVALO_SEGUNDOS
        trava.release()


def laco():
    while True:
        atualizar()
        time.sleep(INTERVALO_SEGUNDOS)


@app.route("/")
def index():
    return send_from_directory(PASTA, "index.html")


@app.route("/api/dados")
def api_dados():
    return jsonify({**estado, "grupo": GROUP_ID, "eventos": eventos, "agora": int(time.time())})


@app.route("/api/atualizar", methods=["POST"])
def api_atualizar():
    if not estado["verificando"]:
        threading.Thread(target=atualizar, daemon=True).start()
    return jsonify({"ok": True})


if __name__ == "__main__":
    threading.Thread(target=laco, daemon=True).start()
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)

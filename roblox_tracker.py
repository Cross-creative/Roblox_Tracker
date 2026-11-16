import requests
import time
import json
import os
from datetime import datetime, timezone, timedelta

GROUP_ID = 4165692
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache_monitor.json")
INTERVALO_SEGUNDOS = 300

try:
    from zoneinfo import ZoneInfo
    FUSO_HORARIO = ZoneInfo("America/Sao_Paulo")
except Exception:
    FUSO_HORARIO = timezone(timedelta(hours=-3))


def carregar_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def salvar_cache(cache):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Error] Could not save the cache to {CACHE_FILE}: {e}")


def formatar_data(data_str):
    if not data_str or data_str in ("N/A", "Could not retrieve"):
        return data_str
    try:
        texto = data_str.replace("Z", "+00:00")
        if "." in texto:
            base, resto = texto.split(".")
            if "+" in resto:
                frac, tz = resto.split("+")
                tz = "+" + tz
            else:
                frac, tz = resto, ""
            frac = frac[:6]
            texto = f"{base}.{frac}{tz}"
        dt = datetime.fromisoformat(texto)
        dt_local = dt.astimezone(FUSO_HORARIO)
        return dt_local.strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return data_str


def obter_icones_places(place_ids, headers):
    icones = {}
    if not place_ids:
        return icones
    try:
        url = (
            "https://thumbnails.roblox.com/v1/places/gameicons"
            f"?placeIds={','.join(str(p) for p in place_ids)}"
            "&returnPolicy=PlaceHolder&size=512x512&format=Png&isCircular=false"
        )
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            for item in res.json().get("data", []):
                icones[item.get("targetId")] = item.get("imageUrl")
    except Exception:
        pass
    return icones


def formatar_numero(n):
    try:
        return f"{int(n):,}".replace(",", ".")
    except Exception:
        return str(n)


def listar_subplaces_do_grupo(group_id, cache):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    try:
        games_url = f"https://games.roblox.com/v2/groups/{group_id}/games?accessFilter=All&limit=100"
        res_games = requests.get(games_url, headers=headers)

        if res_games.status_code != 200:
            print(f"[Error] Failed to query the group. HTTP code: {res_games.status_code}")
            return

        jogos = res_games.json().get("data", [])
        print(f"TERMINAL API: {group_id}")
        print(f"Total games found: {len(jogos)}\n" + "="*50 + "\n")

        universe_ids = [str(jogo.get("id")) for jogo in jogos]
        game_stats = {}

        if universe_ids:
            stats_url = f"https://games.roblox.com/v1/games?universeIds={','.join(universe_ids)}"
            res_stats = requests.get(stats_url, headers=headers)
            if res_stats.status_code == 200:
                for item in res_stats.json().get("data", []):
                    game_stats[item.get("id")] = item

        for jogo in jogos:
            universe_id = jogo.get("id")
            nome_jogo = jogo.get("name")
            stats = game_stats.get(universe_id, {})
            jogando = formatar_numero(stats.get("playing", "N/A"))
            visitas = formatar_numero(stats.get("visits", "N/A"))

            print(f"INFO: {nome_jogo} (Universe ID: {universe_id})")
            print(f"   ├── Playing now: {jogando}")
            print(f"   ├── Total visits: {visitas}")

            places_url = f"https://develop.roblox.com/v1/universes/{universe_id}/places?limit=100"
            res_places = requests.get(places_url, headers=headers)

            if res_places.status_code == 200:
                data = res_places.json()
                places = data.get("data", []) if isinstance(data, dict) else []
                icones = obter_icones_places([place.get("id") for place in places], headers)

                for place in places:
                    p_id = place.get("id")
                    p_name = place.get("name", "Unnamed")

                    asset_url = f"https://economy.roblox.com/v2/assets/{p_id}/details"
                    res_asset = requests.get(asset_url, headers=headers)

                    created = "Could not retrieve"
                    updated = "Could not retrieve"
                    raw_updated = None
                    raw_name = p_name
                    raw_description = ""

                    if res_asset.status_code == 200:
                        asset_data = res_asset.json()
                        raw_updated = asset_data.get("Updated", "N/A")
                        raw_name = asset_data.get("Name", p_name)
                        raw_description = asset_data.get("Description", "")
                        created = formatar_data(asset_data.get("Created", "N/A"))
                        updated = formatar_data(raw_updated)

                    print(f"   ├── Place: {p_name}")
                    print(f"   │   ├── Place ID: {p_id}")
                    print(f"   │   ├── Image: {icones.get(p_id) or 'Unavailable'}")
                    print(f"   │   ├── Created: {created}")
                    print(f"   │   └── Last Patch: {updated}")

                    chave = str(p_id)
                    anterior = cache.get(chave)

                    if anterior:
                        if anterior.get("updated") != raw_updated:
                            print(f"   │   >> New patch detected (Updated changed)")
                        if anterior.get("name") != raw_name:
                            print(f"   │   >> Name changed from \"{anterior.get('name')}\" to \"{raw_name}\"")
                        if anterior.get("description") != raw_description:
                            print(f"   │   >> Description was changed")
                    else:
                        print(f"   │   >> First check of this place, no history to compare")

                    cache[chave] = {
                        "updated": raw_updated,
                        "name": raw_name,
                        "description": raw_description
                    }

                    time.sleep(0.3)

                chave_universo = f"universo_{universe_id}_places"
                ids_atuais = [str(place.get("id")) for place in places]
                ids_anteriores = cache.get(chave_universo)

                if ids_anteriores is not None:
                    adicionados = [pid for pid in ids_atuais if pid not in ids_anteriores]
                    removidos = [pid for pid in ids_anteriores if pid not in ids_atuais]
                    if adicionados:
                        print(f"   >> Place(s) added to the universe: {', '.join(adicionados)}")
                    if removidos:
                        print(f"   >> Place(s) removed from the universe: {', '.join(removidos)}")
                else:
                    print(f"   >> First check of this universe, no place history to compare")

                cache[chave_universo] = ids_atuais

                print("\n" + "-"*50 + "\n")
            else:
                print(f"   └── [HTTP Error {res_places.status_code}] Could not retrieve sub-places.\n")

            time.sleep(0.5)

    except Exception as e:
        print(f"\n[Unexpected Error]: {e}")


if __name__ == "__main__":
    cache = carregar_cache()
    try:
        while True:
            listar_subplaces_do_grupo(GROUP_ID, cache)
            salvar_cache(cache)
            print(f"Next check in {INTERVALO_SEGUNDOS} seconds. Press Ctrl+C to stop.\n")
            time.sleep(INTERVALO_SEGUNDOS)
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")

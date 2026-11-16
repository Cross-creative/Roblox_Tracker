import json
import os
import time

import server
from roblox_tracker import GROUP_ID, INTERVALO_SEGUNDOS

PASTA = os.path.dirname(os.path.abspath(__file__))

jogos = server.coletar()
agora = int(time.time())

saida = {
    "jogos": jogos,
    "atualizado_em": server.agora_texto(),
    "proxima": agora + INTERVALO_SEGUNDOS,
    "erro": None,
    "verificando": False,
    "grupo": GROUP_ID,
    "eventos": server.eventos,
    "agora": agora,
}

with open(os.path.join(PASTA, "data.json"), "w", encoding="utf-8") as f:
    json.dump(saida, f, ensure_ascii=False)

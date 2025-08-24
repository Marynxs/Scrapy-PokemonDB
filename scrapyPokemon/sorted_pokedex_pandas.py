# sort_pokedex_pandas.py
import json
import pandas as pd

IN_PATH = "data/pokedex.json"
OUT_PATH = "data/pokedex_sorted.json"

def _to_int_id(x):
    """
    Converte ids como "0007" ou "#0007" para inteiro 7.
    Se não der, retorna None (vai para o fim na ordenação).
    """
    if x is None:
        return None
    s = str(x).replace("#", "").strip()
    try:
        return int(s)
    except ValueError:
        return None


# ---------- carregar ----------
with open(IN_PATH, "r", encoding="utf-8") as f:
    arr = json.load(f)  # array de dicts

# ---------- TRATAMENTOS ANTES DO DF (facilita mexer em campos aninhados) ----------
for doc in arr:
    # 1) transformar id em inteiro (e já persistir a mudança)
    int_id = _to_int_id(doc.get("id"))
    if int_id is not None:
        doc["id"] = int_id  # <<-- agora id é inteiro

# ---------- criar DataFrame ----------
df = pd.DataFrame(arr)

# ---------- remover duplicados por id (mantendo o último) ----------
df = df.drop_duplicates(subset="id", keep="last")

# ---------- ordenar por id inteiro ----------
# se algum id virou None por qualquer motivo, empurra pro fim
df["_id_num"] = df["id"].apply(lambda x: x if isinstance(x, int) else 10**9)
df = df.sort_values("_id_num").drop(columns="_id_num")

# ---------- salvar ----------
out = df.to_dict(orient="records")
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print(f"Arquivo ordenado e limpo salvo em {OUT_PATH}")

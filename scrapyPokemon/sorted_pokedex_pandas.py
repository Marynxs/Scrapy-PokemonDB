#pip install pandas

import json
import pandas as pd # type: ignore

IN_PATH = "data/pokedex.json"
OUT_PATH = "data/pokedex_sorted.json"

def _to_int_id(x):
    if x is None:
        return None
    s = str(x).replace("#", "").strip()
    try:
        return int(s)
    except ValueError:
        return None

# Abrir o json
with open(IN_PATH, "r", encoding="utf-8") as f:
    arr = json.load(f)  # array de dicts

# Transformar Id em inteiro
for doc in arr:
    # 1) transformar id em inteiro
    int_id = _to_int_id(doc.get("id"))
    if int_id is not None:
        doc["id"] = int_id 

df = pd.DataFrame(arr)
df = df.drop_duplicates(subset="id", keep="last")

# Ordenar por id inteiro 
df["_id_num"] = df["id"].apply(lambda x: x if isinstance(x, int) else 10**9)
df = df.sort_values("_id_num").drop(columns="_id_num")

# Salva em um novo json
out = df.to_dict(orient="records")
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print(f"Arquivo ordenado e limpo salvo em {OUT_PATH}")

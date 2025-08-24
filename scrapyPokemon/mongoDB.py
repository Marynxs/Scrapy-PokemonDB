#pip install pymongo


import json
from pymongo import MongoClient

mongo_url = "mongodb+srv://senac:MongoDBPokedex@pokedex.mxdv2xi.mongodb.net/?retryWrites=true&w=majority&appName=Pokedex"
client = MongoClient(mongo_url)

# banco de dados
db = client['Pokedex']
coll = db['pokemon']  # nome da coleção

# caminho do JSON já tratado com pandas
json_path = "data/pokedex_sorted.json"

# carregar arquivo
with open(json_path, "r", encoding="utf-8") as f:
    data = json.load(f)

# criar índice para evitar duplicados
coll.create_index("id", unique=True)

# inserir/atualizar em lote
for doc in data:
    coll.update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)

print(f"{len(data)} documentos inseridos/atualizados em 'Pokedex.pokemon'.")

#CONSULTAS
print("== Consulta 1: Quantos Pokémon possuem 2 ou mais tipos? ==")
pipeline1 = [
    {"$match": {"types": {"$exists": True}}},
    {"$project": {"n_types": {"$size": "$types"}}},
    {"$match": {"n_types": {"$gte": 2}}},
    {"$count": "qtd"}
]
print(list(coll.aggregate(pipeline1)))

print("\n== Consulta 2-A: Pokémon do tipo Água que evoluem DEPOIS do level 30 (origem) ==")
pipeline2a = [
    {"$match": {"types": "Water"}},
    {"$unwind": "$evolutions"},
    {"$match": {"evolutions.level": {"$gt": 30}}},
    {"$project": {
        "_id": 0,
        "from_id": "$id",
        "from_name": "$name",
        "to_id": "$evolutions.to_id",
        "to_name": "$evolutions.to_name",
        "level": "$evolutions.level",
        "method": "$evolutions.method"
    }}
]
for doc in coll.aggregate(pipeline2a):
    print(doc)

print("\n== Consulta 2-B: Pokémon que RESULTAM em tipo Água após level > 30 (destino) ==")
pipeline2b = [
    {"$unwind": "$evolutions"},
    {"$match": {"evolutions.level": {"$gt": 30}}},
    {"$lookup": {
        "from": "pokemon",
        "localField": "evolutions.to_id",
        "foreignField": "id",
        "as": "to_doc"
    }},
    {"$unwind": "$to_doc"},
    {"$match": {"to_doc.types": "Water"}},
    {"$project": {
        "_id": 0,
        "from_id": "$id",
        "from_name": "$name",
        "to_id": "$to_doc.id",
        "to_name": "$to_doc.name",
        "to_types": "$to_doc.types",
        "level": "$evolutions.level",
        "method": "$evolutions.method"
    }}
]
for doc in coll.aggregate(pipeline2b):
    print(doc)
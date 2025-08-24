#pip install pymongo
#pip install python-dotenv

import json
import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

mongo_url = os.getenv("MONGODB_URL")
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
        "Id do Pokemon": "$id",
        "Nome do Pokemon": "$name",
        "Evolui para Pokemon do Id": "$evolutions.to_id",
        "Evolui para o Pokemon de nome": "$evolutions.to_name",
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
    {"$addFields": { "to_id_num": { "$toInt": "$evolutions.to_id" } }}, 
    {"$lookup": {
        "from": "pokemon",
        "localField": "to_id_num",
        "foreignField": "id",
        "as": "to_doc"
    }},
    {"$unwind": "$to_doc"},
    {"$match": {"to_doc.types": "Water"}},
    {"$project": {
        "_id": 0,
        "Pokemon evoluido": "$to_doc.name",
        "Pokemon evoluido de": "$name",
        "level": "$evolutions.level",
        "method": "$evolutions.method",
    }},
    {"$sort": {"from_name": 1, "level": 1}}
]
for doc in coll.aggregate(pipeline2b):
    print(doc)
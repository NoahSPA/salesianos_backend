from __future__ import annotations

from bson import ObjectId


def oid(id_str: str) -> ObjectId:
    if not ObjectId.is_valid(id_str):
        raise ValueError("id inválido")
    return ObjectId(id_str)


def str_id(doc: dict) -> dict:
    if "_id" in doc:
        doc = {**doc, "id": str(doc["_id"])}
        doc.pop("_id", None)
    return doc


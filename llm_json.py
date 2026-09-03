"""Parseo tolerante del JSON que devuelven los LLMs en modo json_object.

Algunos modelos (visto con deepseek-v4-flash vía LiteLLM) pegan basura después
del objeto JSON aunque el modo json_object lo fuerce — json.loads revienta con
"Extra data" pese a que el JSON en sí es válido. raw_decode se queda solo con
el primer objeto y descarta lo que sobre.
"""
import json


def parse_json_content(content: str) -> dict:
    return json.JSONDecoder().raw_decode(content.strip())[0]

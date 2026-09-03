"""Self-check mínimo: parseo tolerante a basura final tras el JSON."""
from llm_json import parse_json_content


def test_clean_json():
    assert parse_json_content('{"a": 1}') == {"a": 1}


def test_trailing_garbage_is_discarded():
    # Caso real visto con deepseek-v4-flash vía LiteLLM: el modelo pega
    # basura después del JSON pese al modo json_object.
    assert parse_json_content('{"a": 1}"}') == {"a": 1}


def test_strips_surrounding_whitespace():
    assert parse_json_content('  \n{"a": 1}\n  ') == {"a": 1}


if __name__ == "__main__":
    test_clean_json()
    test_trailing_garbage_is_discarded()
    test_strips_surrounding_whitespace()
    print("OK")

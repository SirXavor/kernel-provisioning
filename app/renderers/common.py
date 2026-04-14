from typing import Any, Dict

from jinja2 import Environment, StrictUndefined


def _deep_render(value: Any, env: Environment, context: Dict[str, Any]) -> Any:
    """
    Render recursivo:
    - str -> template Jinja2
    - list -> render de cada elemento
    - dict -> render de cada valor
    - resto -> se devuelve tal cual
    """
    if isinstance(value, str):
        return env.from_string(value).render(**context)

    if isinstance(value, list):
        return [_deep_render(item, env, context) for item in value]

    if isinstance(value, dict):
        return {k: _deep_render(v, env, context) for k, v in value.items()}

    return value


def render_templates(data: Any, context: Dict[str, Any]) -> Any:
    """
    Renderiza cualquier estructura Python usando Jinja2.

    Usa StrictUndefined para que falle si referencias una variable que no existe,
    en vez de dejarla vacía silenciosamente.
    """
    env = Environment(
        autoescape=False,
        trim_blocks=False,
        lstrip_blocks=False,
        undefined=StrictUndefined,
    )
    return _deep_render(data, env, context)
from typing import Any, Dict

import yaml


def render_ansible_yaml(cfg: Dict[str, Any]) -> str:
    return yaml.safe_dump(
        cfg,
        sort_keys=False,
        allow_unicode=True,
    )
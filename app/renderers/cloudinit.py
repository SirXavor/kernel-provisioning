from typing import Any, Dict

import yaml

from config_engine import normalize_mac


def render_user_data(cfg: Dict[str, Any]) -> str:
    return "#cloud-config\n" + yaml.safe_dump(
        cfg,
        sort_keys=False,
        allow_unicode=True,
    )


def render_meta_data(mac: str, cfg: Dict[str, Any]) -> str:
    normalized_mac = normalize_mac(mac)

    hostname = normalized_mac
    try:
        hostname = cfg.get("autoinstall", {}).get("identity", {}).get(
            "hostname",
            normalized_mac,
        )
    except Exception:
        pass

    return f"instance-id: iid-{normalized_mac}\nlocal-hostname: {hostname}\n"


def render_vendor_data() -> str:
    return ""
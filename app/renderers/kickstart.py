from typing import Any, Dict, List


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _render_lang(cfg: Dict[str, Any]) -> str:
    lang = cfg.get("lang")
    return f"lang {lang}" if lang else ""


def _render_keyboard(cfg: Dict[str, Any]) -> str:
    keyboard = cfg.get("keyboard")
    return f"keyboard {keyboard}" if keyboard else ""


def _render_timezone(cfg: Dict[str, Any]) -> str:
    timezone = cfg.get("timezone")
    return f"timezone {timezone}" if timezone else ""


def _render_network(cfg: Dict[str, Any]) -> str:
    network = cfg.get("network", {})
    if not isinstance(network, dict):
        return "network --bootproto=dhcp --device=link --activate --ipv6=off"

    bootproto = str(network.get("bootproto", "dhcp")).strip().lower()
    device = str(network.get("device", "link")).strip()
    activate = _bool(network.get("activate", True), default=True)
    ipv6 = _bool(network.get("ipv6", False), default=False)

    parts = [
        "network",
        f"--bootproto={bootproto}",
        f"--device={device}",
    ]

    if activate:
        parts.append("--activate")

    if not ipv6:
        parts.append("--ipv6=off")

    return " ".join(parts)


def _render_root(cfg: Dict[str, Any]) -> str:
    root_cfg = cfg.get("root", {})
    if not isinstance(root_cfg, dict):
        return "rootpw --lock"

    if _bool(root_cfg.get("lock", True), default=True):
        return "rootpw --lock"

    password = root_cfg.get("password")
    is_crypted = _bool(root_cfg.get("iscrypted", True), default=True)

    if password:
        if is_crypted:
            return f"rootpw --iscrypted {password}"
        return f"rootpw {password}"

    return "rootpw --lock"


def _render_user(cfg: Dict[str, Any]) -> str:
    user_cfg = cfg.get("user", {})
    if not isinstance(user_cfg, dict):
        return ""

    name = user_cfg.get("name")
    password = user_cfg.get("password")

    if not name or not password:
        return ""

    groups = _as_list(user_cfg.get("groups"))
    groups_str = ",".join(str(x).strip() for x in groups if str(x).strip())

    parts = [
        "user",
        f"--name={name}",
        f"--password={password}",
        "--iscrypted",
    ]

    if groups_str:
        parts.append(f"--groups={groups_str}")

    return " ".join(parts)


def _render_firewall_and_selinux() -> List[str]:
    return [
        "firewall --enabled",
        "selinux --permissive",
    ]


def _render_services(cfg: Dict[str, Any]) -> str:
    ssh_cfg = cfg.get("ssh", {})
    if isinstance(ssh_cfg, dict) and _bool(ssh_cfg.get("enabled", False), default=False):
        return "services --enabled=sshd"
    return ""


def _render_packages(cfg: Dict[str, Any]) -> str:
    packages = _as_list(cfg.get("packages"))
    lines = ["%packages"]

    for pkg in packages:
        pkg_name = str(pkg).strip()
        if pkg_name:
            lines.append(pkg_name)

    lines.append("%end")
    return "\n".join(lines)


def _render_ssh_post(cfg: Dict[str, Any]) -> str:
    ssh_cfg = cfg.get("ssh", {})
    if not isinstance(ssh_cfg, dict):
        return ""

    lines: List[str] = []

    authorized_keys = _as_list(ssh_cfg.get("authorized_keys"))
    user_cfg = cfg.get("user", {})
    username = user_cfg.get("name")

    if username and authorized_keys:
        lines.extend([
            f"mkdir -p /home/{username}/.ssh",
            f"chmod 700 /home/{username}/.ssh",
            f"chown {username}:{username} /home/{username}/.ssh",
            f"cat > /home/{username}/.ssh/authorized_keys <<'EOF_AUTH_KEYS'",
        ])
        for key in authorized_keys:
            lines.append(str(key))
        lines.extend([
            "EOF_AUTH_KEYS",
            f"chmod 600 /home/{username}/.ssh/authorized_keys",
            f"chown {username}:{username} /home/{username}/.ssh/authorized_keys",
        ])

    password_auth = _bool(ssh_cfg.get("password_auth", False), default=False)
    if not password_auth:
        lines.extend([
            r"sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
            r"sed -i 's/^#\?ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' /etc/ssh/sshd_config || true",
            "systemctl enable sshd",
            "systemctl restart sshd || true",
        ])

    return "\n".join(lines)


def _render_post(cfg: Dict[str, Any]) -> str:
    post_blocks = _as_list(cfg.get("post"))
    ssh_post = _render_ssh_post(cfg)

    body_lines: List[str] = [
        "set -euo pipefail",
    ]

    if ssh_post.strip():
        body_lines.append(ssh_post)

    for block in post_blocks:
        text = str(block).strip()
        if text:
            body_lines.append(text)

    return "%post --log=/root/ks-post.log\n" + "\n\n".join(body_lines) + "\n%end"


def _render_storage(cfg: Dict[str, Any]) -> List[str]:
    """
    Primer paso: storage mínimo.
    Si luego modelas storage nativo de RHEL, se amplía aquí.
    """
    storage = cfg.get("storage")
    if not storage:
        return [
            "zerombr",
            "clearpart --all --initlabel",
            "autopart",
        ]

    if isinstance(storage, dict) and storage.get("mode") == "autopart":
        return [
            "zerombr",
            "clearpart --all --initlabel",
            "autopart",
        ]

    # Placeholder controlado para no romper instalaciones mientras defines el modelo RHEL
    return [
        "zerombr",
        "clearpart --all --initlabel",
        "autopart",
    ]


def render_kickstart(cfg: Dict[str, Any]) -> str:
    kickstart = cfg.get("kickstart", {})
    if not isinstance(kickstart, dict):
        kickstart = {}

    lines: List[str] = []

    for item in (
        _render_lang(kickstart),
        _render_keyboard(kickstart),
        _render_timezone(kickstart),
        _render_network(kickstart),
        _render_root(kickstart),
        _render_user(kickstart),
        *_render_firewall_and_selinux(),
        _render_services(kickstart),
    ):
        if item:
            lines.append(item)

    lines.extend(_render_storage(kickstart))

    lines.append(_render_packages(kickstart))
    lines.append(_render_post(kickstart))

    return "\n".join(lines) + "\n"
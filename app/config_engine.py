import copy
import glob
import logging
import os
from typing import Any, Callable, Dict, List

import yaml

CONFIG_DIR = "/data"

# Claves internas SOLO a nivel raíz del documento
TOP_LEVEL_INTERNAL_KEYS = {
    "kind",
    "name",
    "profile",
    "profiles",
    "role",
    "roles",
    "tags",
    "identity",
    "match",
    "provisioning",
}


def load_yaml_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge recursivo:
    - dict + dict => merge
    - list + list => concatena
    - resto => sobrescribe
    """
    for k, v in b.items():
        if k in a:
            if isinstance(a[k], dict) and isinstance(v, dict):
                deep_merge(a[k], v)
            elif isinstance(a[k], list) and isinstance(v, list):
                a[k].extend(copy.deepcopy(v))
            else:
                a[k] = copy.deepcopy(v)
        else:
            a[k] = copy.deepcopy(v)
    return a


def normalize_mac(value: str) -> str:
    """
    Normaliza MAC:
    - minúsculas
    - sustituye ':' por '-'
    - trim
    """
    return str(value).lower().replace(":", "-").strip()


def get_cfg_distro(cfg: Dict[str, Any], default: str = "ubuntu") -> str:
    """
    Extrae la distro desde cfg.provisioning.distro.
    """
    provisioning = cfg.get("provisioning", {})
    if not isinstance(provisioning, dict):
        return default

    distro = str(provisioning.get("distro", default)).strip().lower()
    return distro or default


def normalize_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normaliza claves simples del host según la distro objetivo.

    - Ubuntu: hostname simple -> autoinstall.identity.hostname
    - RHEL/Rocky: hostname simple se conserva para Kickstart
    """
    cfg = copy.deepcopy(cfg)

    hostname = cfg.get("hostname")
    distro = get_cfg_distro(cfg, default="ubuntu")

    if hostname and distro == "ubuntu":
        cfg.pop("hostname", None)
        cfg.setdefault("autoinstall", {})
        cfg["autoinstall"].setdefault("identity", {})
        cfg["autoinstall"]["identity"]["hostname"] = hostname

    return cfg


def strip_internal_keys_top_level(
    cfg: Dict[str, Any],
    extra_keys: set[str] | None = None,
) -> Dict[str, Any]:
    """
    Elimina SOLO claves internas del nivel superior.
    No toca estructuras hijas.
    """
    cleaned = copy.deepcopy(cfg)
    keys_to_strip = set(TOP_LEVEL_INTERNAL_KEYS)
    if extra_keys:
        keys_to_strip.update(extra_keys)

    for key in keys_to_strip:
        cleaned.pop(key, None)

    return cleaned


def load_all_documents(logger: logging.Logger | None = None) -> List[Dict[str, Any]]:
    """
    Carga todos los YAML de /data en plano.
    """
    docs: List[Dict[str, Any]] = []

    for path in sorted(glob.glob(os.path.join(CONFIG_DIR, "*.yaml"))):
        try:
            doc = load_yaml_file(path)
            if isinstance(doc, dict) and doc:
                doc["_source_file"] = os.path.basename(path)
                docs.append(doc)
        except Exception as e:
            if logger:
                logger.exception("Error cargando %s: %s", path, e)

    return docs


def classify_documents(
    docs: List[Dict[str, Any]],
    logger: logging.Logger | None = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Clasifica documentos por kind.
    """
    classified = {
        "base": [],
        "profile": [],
        "host": [],
    }

    for doc in docs:
        kind = doc.get("kind")
        if kind in classified:
            classified[kind].append(doc)
        else:
            if logger:
                logger.warning(
                    "Ignorando documento sin kind válido: %s (%s)",
                    doc.get("name"),
                    doc.get("_source_file"),
                )

    return classified


def extract_host_macs(doc: Dict[str, Any]) -> List[str]:
    """
    Extrae y normaliza las MACs válidas de un host desde identity.mac.
    """
    identity = doc.get("identity", {})

    if not isinstance(identity, dict):
        return []

    macs = identity.get("mac", [])

    if isinstance(macs, str):
        macs = [macs]
    elif not isinstance(macs, list):
        return []

    result = []
    for value in macs:
        normalized = normalize_mac(value)
        if normalized:
            result.append(normalized)

    return result


def host_matches_mac(doc: Dict[str, Any], mac: str) -> bool:
    """
    Compatibilidad dual:
    1. Modelo nuevo: identity.mac contiene la MAC
    2. Modelo antiguo: name == mac
    """
    wanted_mac = normalize_mac(mac)

    host_macs = extract_host_macs(doc)
    if wanted_mac in host_macs:
        return True

    host_name = str(doc.get("name", "")).strip().lower()
    if host_name == wanted_mac:
        return True

    return False


def find_host_doc(host_docs: List[Dict[str, Any]], mac: str) -> Dict[str, Any]:
    """
    Busca primero host específico por MAC.
    Si no existe, usa host=default.
    """
    wanted_mac = normalize_mac(mac)

    specific = None
    default = None

    for doc in host_docs:
        name = str(doc.get("name", "")).lower().strip()

        if name == "default":
            default = doc

        if host_matches_mac(doc, wanted_mac):
            specific = doc
            break

    if specific:
        return copy.deepcopy(specific)
    if default:
        return copy.deepcopy(default)

    return {}


def find_specific_host_doc(host_docs: List[Dict[str, Any]], mac: str) -> Dict[str, Any]:
    """
    Busca SOLO un host específico por MAC.
    No devuelve 'default'.
    """
    wanted_mac = normalize_mac(mac)

    for doc in host_docs:
        if host_matches_mac(doc, wanted_mac):
            return copy.deepcopy(doc)

    return {}


def host_exists(mac: str, logger: logging.Logger | None = None) -> bool:
    docs = load_all_documents(logger=logger)
    classified = classify_documents(docs, logger=logger)
    specific = find_specific_host_doc(classified["host"], mac)
    return bool(specific)


def find_profile_docs(
    profile_docs: List[Dict[str, Any]],
    profile_names: List[str],
    logger: logging.Logger | None = None,
) -> List[Dict[str, Any]]:
    result = []
    profile_map = {
        str(doc.get("name", "")).strip(): doc
        for doc in profile_docs
    }

    for profile_name in profile_names:
        doc = profile_map.get(profile_name)
        if doc:
            result.append(copy.deepcopy(doc))
        else:
            if logger:
                logger.warning("Perfil no encontrado: %s", profile_name)

    return result


def resolve_profiles(host_cfg: Dict[str, Any]) -> List[str]:
    profiles = host_cfg.get("profiles")
    profile = host_cfg.get("profile")

    if isinstance(profiles, list):
        cleaned = [str(x).strip() for x in profiles if str(x).strip()]
        return cleaned or ["default"]

    if isinstance(profiles, str) and profiles.strip():
        return [profiles.strip()]

    if isinstance(profile, list):
        cleaned = [str(x).strip() for x in profile if str(x).strip()]
        return cleaned or ["default"]

    if isinstance(profile, str) and profile.strip():
        return [profile.strip()]

    return ["default"]


def doc_matches_distro(doc: Dict[str, Any], distro: str) -> bool:
    """
    Si el documento no define match.distro, se considera global.
    """
    match_cfg = doc.get("match", {})

    if not isinstance(match_cfg, dict):
        return True

    wanted = match_cfg.get("distro")
    if wanted is None:
        return True

    normalized_distro = str(distro).strip().lower()

    if isinstance(wanted, str):
        return wanted.strip().lower() == normalized_distro

    if isinstance(wanted, list):
        accepted = [str(x).strip().lower() for x in wanted if str(x).strip()]
        return normalized_distro in accepted

    return False


def filter_docs_for_distro(docs: List[Dict[str, Any]], distro: str) -> List[Dict[str, Any]]:
    return [doc for doc in docs if doc_matches_distro(doc, distro)]


def sanitize_doc_for_full_config(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Quita solo metadatos de estructura, pero conserva metadatos funcionales
    internos como provisioning y match.
    """
    cleaned = copy.deepcopy(doc)
    cleaned.pop("_source_file", None)

    cleaned.pop("kind", None)
    cleaned.pop("name", None)
    cleaned.pop("profile", None)
    cleaned.pop("profiles", None)
    cleaned.pop("role", None)
    cleaned.pop("roles", None)
    cleaned.pop("tags", None)
    cleaned.pop("identity", None)

    return cleaned


def sanitize_doc_for_cloudinit(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepara el documento para render cloud-init / autoinstall.
    """
    cleaned = copy.deepcopy(doc)
    cleaned.pop("_source_file", None)
    cleaned = strip_internal_keys_top_level(
        cleaned,
        extra_keys={"automation", "kickstart"},
    )
    return cleaned


def sanitize_doc_for_kickstart(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepara el documento para render Kickstart.
    """
    cleaned = copy.deepcopy(doc)
    cleaned.pop("_source_file", None)
    cleaned = strip_internal_keys_top_level(
        cleaned,
        extra_keys={"automation", "autoinstall"},
    )
    return cleaned


def _build_config(
    mac: str,
    sanitize_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    logger: logging.Logger | None = None,
) -> Dict[str, Any]:
    wanted_mac = normalize_mac(mac)

    docs = load_all_documents(logger=logger)
    classified = classify_documents(docs, logger=logger)

    host_cfg = find_host_doc(classified["host"], wanted_mac)
    distro = get_cfg_distro(host_cfg, default="ubuntu")

    base_docs = filter_docs_for_distro(classified["base"], distro)
    profile_docs = filter_docs_for_distro(classified["profile"], distro)

    final_cfg: Dict[str, Any] = {}

    for doc in base_docs:
        final_cfg = deep_merge(final_cfg, sanitize_fn(doc))

    profile_names = resolve_profiles(host_cfg)
    selected_profiles = find_profile_docs(
        profile_docs,
        profile_names,
        logger=logger,
    )

    for profile_doc in selected_profiles:
        final_cfg = deep_merge(final_cfg, sanitize_fn(profile_doc))

    final_cfg = deep_merge(final_cfg, sanitize_fn(host_cfg))
    final_cfg = normalize_config(final_cfg)

    if logger:
        logger.info(
            "MERGED MAC=%s host=%s distro=%s profiles=%s",
            wanted_mac,
            host_cfg.get("name", "default"),
            distro,
            profile_names,
        )

    return final_cfg


def build_full_config(
    mac: str,
    logger: logging.Logger | None = None,
) -> Dict[str, Any]:
    return _build_config(mac, sanitize_doc_for_full_config, logger=logger)


def build_cloudinit_config(
    mac: str,
    logger: logging.Logger | None = None,
) -> Dict[str, Any]:
    return _build_config(mac, sanitize_doc_for_cloudinit, logger=logger)


def build_kickstart_config(
    mac: str,
    logger: logging.Logger | None = None,
) -> Dict[str, Any]:
    return _build_config(mac, sanitize_doc_for_kickstart, logger=logger)


def build_ansible_config(
    mac: str,
    logger: logging.Logger | None = None,
) -> Dict[str, Any]:
    full_cfg = build_full_config(mac, logger=logger)

    ansible_cfg: Dict[str, Any] = {}

    hostname = None
    try:
        hostname = full_cfg.get("autoinstall", {}).get("identity", {}).get("hostname")
    except Exception:
        hostname = None

    if not hostname:
        hostname = full_cfg.get("hostname")

    if hostname:
        ansible_cfg["hostname"] = hostname

    if "automation" in full_cfg:
        ansible_cfg["automation"] = copy.deepcopy(full_cfg["automation"])

    if "network" in full_cfg:
        ansible_cfg["network"] = copy.deepcopy(full_cfg["network"])

    return ansible_cfg


def get_provisioning_config(mac: str, logger: logging.Logger | None = None) -> Dict[str, Any]:
    full_cfg = build_full_config(mac, logger=logger)
    provisioning = full_cfg.get("provisioning", {})

    if isinstance(provisioning, dict):
        return copy.deepcopy(provisioning)

    return {}
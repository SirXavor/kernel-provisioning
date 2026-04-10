import copy
import glob
import logging
import os
from typing import Any, Dict, List

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


def normalize_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convierte claves simples del host en estructura autoinstall válida.
    """
    cfg = copy.deepcopy(cfg)

    hostname = cfg.pop("hostname", None)
    if hostname:
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
    Acepta:
      identity:
        mac:
          - aa-bb-...
          - 11:22:...
    o
      identity:
        mac: aa-bb-...
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
    Busca primero host específico por MAC (modelo nuevo o antiguo).
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


def find_profile_docs(
    profile_docs: List[Dict[str, Any]],
    profile_names: List[str],
    logger: logging.Logger | None = None,
) -> List[Dict[str, Any]]:
    """
    Devuelve los documentos de perfil en el orden pedido.
    """
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
    """
    Resuelve profile/profiles del host.
    - profiles: lista
    - profile: string
    - si no hay nada => ["default"]
    """
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


def sanitize_doc_for_full_config(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Quita metadatos técnicos y claves internas del nivel superior.
    Mantiene 'automation' porque forma parte de la config completa.
    """
    cleaned = copy.deepcopy(doc)
    cleaned.pop("_source_file", None)
    cleaned = strip_internal_keys_top_level(cleaned)
    return cleaned


def sanitize_doc_for_cloudinit(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Igual que sanitize_doc_for_full_config, pero además elimina
    claves que no deben salir en user-data.
    """
    cleaned = copy.deepcopy(doc)
    cleaned.pop("_source_file", None)
    cleaned = strip_internal_keys_top_level(cleaned, extra_keys={"automation"})
    return cleaned


def _build_config(
    mac: str,
    sanitize_fn,
    logger: logging.Logger | None = None,
) -> Dict[str, Any]:
    """
    Constructor genérico de configuración merged.
    """
    wanted_mac = normalize_mac(mac)

    docs = load_all_documents(logger=logger)
    classified = classify_documents(docs, logger=logger)

    final_cfg: Dict[str, Any] = {}

    for doc in classified["base"]:
        final_cfg = deep_merge(final_cfg, sanitize_fn(doc))

    host_cfg = find_host_doc(classified["host"], wanted_mac)

    profile_names = resolve_profiles(host_cfg)
    selected_profiles = find_profile_docs(
        classified["profile"],
        profile_names,
        logger=logger,
    )

    for profile_doc in selected_profiles:
        final_cfg = deep_merge(final_cfg, sanitize_fn(profile_doc))

    final_cfg = deep_merge(final_cfg, sanitize_fn(host_cfg))
    final_cfg = normalize_config(final_cfg)

    if logger:
        logger.info(
            "MERGED MAC=%s host=%s profiles=%s",
            wanted_mac,
            host_cfg.get("name", "default"),
            profile_names,
        )

    return final_cfg


def build_full_config(
    mac: str,
    logger: logging.Logger | None = None,
) -> Dict[str, Any]:
    """
    Construye la configuración merged completa para una MAC dada.
    Incluye automation.
    """
    return _build_config(mac, sanitize_doc_for_full_config, logger=logger)


def build_cloudinit_config(
    mac: str,
    logger: logging.Logger | None = None,
) -> Dict[str, Any]:
    """
    Construye solo la configuración destinada a cloud-init.
    Excluye 'automation'.
    """
    return _build_config(mac, sanitize_doc_for_cloudinit, logger=logger)


def build_ansible_config(
    mac: str,
    logger: logging.Logger | None = None,
) -> Dict[str, Any]:
    """
    Construye la configuración que consumirá Ansible.
    """
    full_cfg = build_full_config(mac, logger=logger)

    ansible_cfg: Dict[str, Any] = {}

    hostname = None
    try:
        hostname = full_cfg.get("autoinstall", {}).get("identity", {}).get("hostname")
    except Exception:
        hostname = None

    if hostname:
        ansible_cfg["hostname"] = hostname

    if "automation" in full_cfg:
        ansible_cfg["automation"] = copy.deepcopy(full_cfg["automation"])

    if "network" in full_cfg:
        ansible_cfg["network"] = copy.deepcopy(full_cfg["network"])

    return ansible_cfg
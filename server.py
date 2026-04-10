from flask import Flask, request, Response
import os
import yaml
import glob
import copy
from typing import Any, Dict, List

app = Flask(__name__)

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
    extra_keys: set[str] | None = None
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


def load_all_documents() -> List[Dict[str, Any]]:
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
            app.logger.exception("Error cargando %s: %s", path, e)

    return docs


def classify_documents(docs: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
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
            app.logger.warning(
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

    # Modelo nuevo
    host_macs = extract_host_macs(doc)
    if wanted_mac in host_macs:
        return True

    # Compatibilidad con modelo antiguo
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
    profile_names: List[str]
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
            app.logger.warning("Perfil no encontrado: %s", profile_name)

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


def build_full_config(mac: str) -> Dict[str, Any]:
    """
    Construye la configuración merged completa para una MAC dada.
    Incluye automation.
    """
    wanted_mac = normalize_mac(mac)

    docs = load_all_documents()
    classified = classify_documents(docs)

    final_cfg: Dict[str, Any] = {}

    # 1. Bases
    for doc in classified["base"]:
        final_cfg = deep_merge(final_cfg, sanitize_doc_for_full_config(doc))

    # 2. Host objetivo
    host_cfg = find_host_doc(classified["host"], wanted_mac)

    # 3. Perfiles del host
    profile_names = resolve_profiles(host_cfg)
    selected_profiles = find_profile_docs(classified["profile"], profile_names)

    for profile_doc in selected_profiles:
        final_cfg = deep_merge(final_cfg, sanitize_doc_for_full_config(profile_doc))

    # 4. Override final del host
    final_cfg = deep_merge(final_cfg, sanitize_doc_for_full_config(host_cfg))

    # 5. Normalización
    final_cfg = normalize_config(final_cfg)

    app.logger.info(
        "FULL MAC=%s host=%s profiles=%s",
        wanted_mac,
        host_cfg.get("name", "default"),
        profile_names,
    )

    return final_cfg


def build_cloudinit_config(mac: str) -> Dict[str, Any]:
    """
    Construye solo la configuración destinada a cloud-init.
    Excluye 'automation'.
    """
    wanted_mac = normalize_mac(mac)

    docs = load_all_documents()
    classified = classify_documents(docs)

    final_cfg: Dict[str, Any] = {}

    # 1. Bases
    for doc in classified["base"]:
        final_cfg = deep_merge(final_cfg, sanitize_doc_for_cloudinit(doc))

    # 2. Host objetivo
    host_cfg = find_host_doc(classified["host"], wanted_mac)

    # 3. Perfiles del host
    profile_names = resolve_profiles(host_cfg)
    selected_profiles = find_profile_docs(classified["profile"], profile_names)

    for profile_doc in selected_profiles:
        final_cfg = deep_merge(final_cfg, sanitize_doc_for_cloudinit(profile_doc))

    # 4. Override final del host
    final_cfg = deep_merge(final_cfg, sanitize_doc_for_cloudinit(host_cfg))

    # 5. Normalización
    final_cfg = normalize_config(final_cfg)

    app.logger.info(
        "CLOUDINIT MAC=%s host=%s profiles=%s",
        wanted_mac,
        host_cfg.get("name", "default"),
        profile_names,
    )

    return final_cfg


def build_ansible_config(mac: str) -> Dict[str, Any]:
    """
    Construye la configuración que consumirá Ansible.
    """
    full_cfg = build_full_config(mac)

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

    # Opcional: si más adelante quieres pasar datos de red a Ansible
    if "network" in full_cfg:
        ansible_cfg["network"] = copy.deepcopy(full_cfg["network"])

    return ansible_cfg


@app.get("/ds/<mac>/user-data")
def user_data_by_mac(mac: str):
    cfg = build_cloudinit_config(mac)
    yaml_text = "#cloud-config\n" + yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True)
    return Response(yaml_text, mimetype="text/yaml")


@app.get("/ds/<mac>/meta-data")
def meta_data_by_mac(mac: str):
    normalized_mac = normalize_mac(mac)
    cfg = build_cloudinit_config(normalized_mac)

    hostname = normalized_mac
    try:
        hostname = cfg.get("autoinstall", {}).get("identity", {}).get("hostname", normalized_mac)
    except Exception:
        pass

    return Response(
        f"instance-id: iid-{normalized_mac}\nlocal-hostname: {hostname}\n",
        mimetype="text/plain"
    )


@app.get("/ds/<mac>/vendor-data")
def vendor_data_by_mac(mac: str):
    return Response("", mimetype="text/plain")


@app.get("/ds/<mac>/ansible")
def ansible_by_mac(mac: str):
    cfg = build_ansible_config(mac)
    yaml_text = yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True)
    return Response(yaml_text, mimetype="text/yaml")


@app.get("/user-data")
def user_data():
    mac = normalize_mac(request.args.get("mac", "default"))
    cfg = build_cloudinit_config(mac)
    yaml_text = "#cloud-config\n" + yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True)
    return Response(yaml_text, mimetype="text/yaml")


@app.get("/meta-data")
def meta_data():
    return Response("instance-id: iid-local01\n", mimetype="text/plain")


@app.get("/debug/configs")
def debug_configs():
    """
    Endpoint opcional para ver qué documentos está cargando el motor.
    """
    docs = load_all_documents()
    summary = []
    for doc in docs:
        summary.append({
            "file": doc.get("_source_file"),
            "kind": doc.get("kind"),
            "name": doc.get("name"),
        })

    yaml_text = yaml.safe_dump(summary, sort_keys=False, allow_unicode=True)
    return Response(yaml_text, mimetype="text/yaml")


@app.get("/debug/hosts")
def debug_hosts():
    """
    Endpoint opcional para ver hosts y sus MACs resueltas.
    """
    docs = load_all_documents()
    classified = classify_documents(docs)

    summary = []
    for doc in classified["host"]:
        summary.append({
            "file": doc.get("_source_file"),
            "name": doc.get("name"),
            "identity": doc.get("identity", {}),
            "normalized_macs": extract_host_macs(doc),
        })

    yaml_text = yaml.safe_dump(summary, sort_keys=False, allow_unicode=True)
    return Response(yaml_text, mimetype="text/yaml")


@app.get("/debug/full-config/<mac>")
def debug_full_config(mac: str):
    """
    Endpoint opcional para ver la config completa merged.
    """
    cfg = build_full_config(mac)
    yaml_text = yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True)
    return Response(yaml_text, mimetype="text/yaml")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

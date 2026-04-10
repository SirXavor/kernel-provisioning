from flask import Flask, Response, request
import yaml

from config_engine import (
    build_ansible_config,
    build_cloudinit_config,
    build_full_config,
    classify_documents,
    extract_host_macs,
    find_specific_host_doc,
    load_all_documents,
    normalize_mac,
)
from renderers.ansible import render_ansible_yaml
from renderers.cloudinit import (
    render_meta_data,
    render_user_data,
    render_vendor_data,
)
from renderers.ipxe import render_host_boot, render_unknown_menu

app = Flask(__name__)

BASE_URL = "http://boot.local"


@app.get("/ds/<mac>/user-data")
def user_data_by_mac(mac: str):
    cfg = build_cloudinit_config(mac, logger=app.logger)
    yaml_text = render_user_data(cfg)
    return Response(yaml_text, mimetype="text/yaml")


@app.get("/ds/<mac>/meta-data")
def meta_data_by_mac(mac: str):
    cfg = build_cloudinit_config(mac, logger=app.logger)
    return Response(render_meta_data(mac, cfg), mimetype="text/plain")


@app.get("/ds/<mac>/vendor-data")
def vendor_data_by_mac(mac: str):
    return Response(render_vendor_data(), mimetype="text/plain")


@app.get("/ds/<mac>/ansible")
def ansible_by_mac(mac: str):
    cfg = build_ansible_config(mac, logger=app.logger)
    yaml_text = render_ansible_yaml(cfg)
    return Response(yaml_text, mimetype="text/yaml")


@app.get("/boot/<mac>")
def boot_by_mac(mac: str):
    """
    Si existe host específico para la MAC, devuelve iPXE automático.
    Si no existe, devuelve menú fallback.
    """
    normalized_mac = normalize_mac(mac)

    docs = load_all_documents(logger=app.logger)
    classified = classify_documents(docs, logger=app.logger)
    host_doc = find_specific_host_doc(classified["host"], normalized_mac)

    if not host_doc:
        app.logger.info("BOOT MAC=%s host=unknown -> fallback menu", normalized_mac)
        return Response(render_unknown_menu(BASE_URL), mimetype="text/plain")

    cfg = build_full_config(normalized_mac, logger=app.logger)
    app.logger.info("BOOT MAC=%s host=known -> automatic render", normalized_mac)
    return Response(render_host_boot(normalized_mac, cfg, BASE_URL), mimetype="text/plain")


@app.get("/user-data")
def user_data():
    mac = normalize_mac(request.args.get("mac", "default"))
    cfg = build_cloudinit_config(mac, logger=app.logger)
    yaml_text = render_user_data(cfg)
    return Response(yaml_text, mimetype="text/yaml")


@app.get("/meta-data")
def meta_data():
    return Response("instance-id: iid-local01\n", mimetype="text/plain")


@app.get("/debug/configs")
def debug_configs():
    """
    Endpoint opcional para ver qué documentos está cargando el motor.
    """
    docs = load_all_documents(logger=app.logger)
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
    docs = load_all_documents(logger=app.logger)
    classified = classify_documents(docs, logger=app.logger)

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
    cfg = build_full_config(mac, logger=app.logger)
    yaml_text = yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True)
    return Response(yaml_text, mimetype="text/yaml")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
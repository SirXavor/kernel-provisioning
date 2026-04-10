from typing import Any, Dict


def infer_installer(distro: str) -> str:
    distro = str(distro).strip().lower()

    if distro == "ubuntu":
        return "autoinstall"

    if distro in {"rhel", "rocky", "almalinux", "centos"}:
        return "kickstart"

    return "unknown"


def render_unknown_menu(base_url: str) -> str:
    """
    Menú fallback para MAC no registrada.
    De momento solo Ubuntu.
    """
    return f"""#!ipxe
dhcp

menu InfraServer Provisioning
item ubuntu  Instalar Ubuntu 24.04
item shell   iPXE shell
choose target && goto ${{target}}

:ubuntu
kernel {base_url}/ubuntu/casper/vmlinuz ip=dhcp url={base_url}/ubuntu/ubuntu-24.04.4-live-server-amd64.iso autoinstall ds=nocloud-net;s={base_url}/ds/default/
initrd {base_url}/ubuntu/casper/initrd
boot

:shell
shell
"""


def render_host_boot(mac: str, cfg: Dict[str, Any], base_url: str) -> str:
    """
    Devuelve el script iPXE final para un host conocido.
    De momento:
    - Ubuntu => autoinstall
    - RHEL/Rocky => placeholder para el siguiente paso
    """
    provisioning = cfg.get("provisioning", {})
    distro = str(provisioning.get("distro", "")).strip().lower()
    version = str(provisioning.get("version", "")).strip()

    if not distro:
        distro = "ubuntu"

    installer = infer_installer(distro)

    if distro == "ubuntu":
        iso_name = "ubuntu-24.04.4-live-server-amd64.iso"
        if version and version != "24.04":
            # Placeholder por si luego quieres cambiar paths por versión.
            pass

        return f"""#!ipxe
dhcp
kernel {base_url}/ubuntu/casper/vmlinuz ip=dhcp url={base_url}/ubuntu/{iso_name} autoinstall ds=nocloud-net;s={base_url}/ds/{mac}/
initrd {base_url}/ubuntu/casper/initrd
boot
"""

    if installer == "kickstart":
        return f"""#!ipxe
echo Kickstart aun no implementado para esta distro
sleep 10
shell
"""

    return render_unknown_menu(base_url)
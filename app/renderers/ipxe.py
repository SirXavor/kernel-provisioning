from typing import Any, Dict


# Para Ubuntu en early boot, mejor no depender de DNS.
# Aquí pones exactamente el endpoint que ya sabes que te funcionaba.
UBUNTU_SERVER = "192.168.1.70:8081"


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
    De momento:
    - Ubuntu usa IP fija porque ya se sabe que funciona en early boot
    - RHEL se podrá añadir luego al menú si quieres
    """
    server = UBUNTU_SERVER
    seed = f"http://{server}/ds/default"

    return f"""#!ipxe
dhcp

menu InfraServer Provisioning
item ubuntu  Instalar Ubuntu 24.04
item shell   iPXE shell
choose target && goto ${{target}}

:ubuntu
kernel http://{server}/vmlinuz ip=dhcp url=http://{server}/ubuntu/ubuntu-24.04.4-live-server-amd64.iso autoinstall ds=nocloud;s={seed}/ ---
initrd http://{server}/initrd
boot

:shell
shell
"""


def render_host_boot(mac: str, cfg: Dict[str, Any], base_url: str) -> str:
    """
    Devuelve el script iPXE final para un host conocido.

    - Ubuntu => vuelve al formato exacto que ya funcionaba
    - RHEL/Rocky/etc => Kickstart real usando base_url
    """
    provisioning = cfg.get("provisioning", {})
    distro = str(provisioning.get("distro", "")).strip().lower()
    version = str(provisioning.get("version", "")).strip()

    if not distro:
        distro = "ubuntu"

    installer = infer_installer(distro)

    if distro == "ubuntu":
        server = UBUNTU_SERVER
        iso_name = "ubuntu-24.04.4-live-server-amd64.iso"
        seed = f"http://{server}/ds/{mac}"

        # Mantener exactamente el estilo que ya te arrancaba:
        # - IP fija
        # - ds=nocloud
        # - ---
        # - vmlinuz/initrd en raíz
        return f"""#!ipxe
dhcp
kernel http://{server}/vmlinuz ip=dhcp url=http://{server}/ubuntu/{iso_name} autoinstall ds=nocloud;s={seed}/ ---
initrd http://{server}/initrd
boot
"""

    if installer == "kickstart":
        distro_path = distro
        version_path = version or "9"

        return f"""#!ipxe
dhcp
kernel {base_url}/{distro_path}/{version_path}/images/pxeboot/vmlinuz ip=dhcp inst.repo={base_url}/repos/{distro_path}/{version_path}/ inst.ks={base_url}/ks/{mac}.cfg
initrd {base_url}/{distro_path}/{version_path}/images/pxeboot/initrd.img
boot
"""

    return render_unknown_menu(base_url)
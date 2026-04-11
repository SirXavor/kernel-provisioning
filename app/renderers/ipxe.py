from typing import Any, Dict


# En early boot mejor no depender de DNS.
PROVISIONING_SERVER = "192.168.1.70:8081"


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
    Ubuntu por defecto, pero deja instalar también RHEL.
    """
    server = PROVISIONING_SERVER
    ubuntu_seed = f"http://{server}/ds/default"
    rhel_version = "9"

    return f"""#!ipxe
dhcp

menu InfraServer Provisioning
item --key u ubuntu  Instalar Ubuntu 24.04
item --key r rhel    Instalar RHEL 9
item --key s shell   iPXE shell
choose --default ubuntu --timeout 5000 target && goto ${{target}}

:ubuntu
kernel http://{server}/vmlinuz ip=dhcp url=http://{server}/content/ubuntu/ubuntu-24.04.4-live-server-amd64.iso autoinstall ds=nocloud;s={ubuntu_seed}/ ---
initrd http://{server}/initrd
boot

:rhel
kernel http://{server}/content/rhel/{rhel_version}/images/pxeboot/vmlinuz ip=dhcp inst.repo=http://{server}/content/repos/rhel/{rhel_version}/ inst.ks=http://{server}/ks/default.cfg
initrd http://{server}/content/rhel/{rhel_version}/images/pxeboot/initrd.img
boot

:shell
shell
"""


def render_host_boot(mac: str, cfg: Dict[str, Any], base_url: str) -> str:
    """
    Devuelve el script iPXE final para un host conocido.

    Reglas:
    - Ubuntu: IP fija + flujo autoinstall ya validado
    - RHEL/Rocky/etc: IP fija + Kickstart
    """
    provisioning = cfg.get("provisioning", {})
    distro = str(provisioning.get("distro", "")).strip().lower()
    version = str(provisioning.get("version", "")).strip()

    if not distro:
        distro = "ubuntu"

    installer = infer_installer(distro)
    server = PROVISIONING_SERVER

    if distro == "ubuntu":
        iso_name = "ubuntu-24.04.4-live-server-amd64.iso"
        seed = f"http://{server}/ds/{mac}"

        return f"""#!ipxe
dhcp
kernel http://{server}/vmlinuz ip=dhcp url=http://{server}/content/ubuntu/{iso_name} autoinstall ds=nocloud;s={seed}/ ---
initrd http://{server}/initrd
boot
"""

    if installer == "kickstart":
        distro_path = distro
        version_path = version or "9"

        return f"""#!ipxe
dhcp
kernel http://{server}/content/{distro_path}/{version_path}/images/pxeboot/vmlinuz ip=dhcp inst.repo=http://{server}/content/repos/{distro_path}/{version_path}/ inst.ks=http://{server}/ks/{mac}.cfg
initrd http://{server}/content/{distro_path}/{version_path}/images/pxeboot/initrd.img
boot
"""

    return render_unknown_menu(base_url)
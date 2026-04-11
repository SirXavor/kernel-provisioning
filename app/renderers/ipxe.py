from typing import Any, Dict


UBUNTU_SERVER = "192.168.1.70:8081"


def infer_installer(distro: str) -> str:
    distro = str(distro).strip().lower()

    if distro == "ubuntu":
        return "autoinstall"

    if distro in {"rhel", "rocky", "almalinux", "centos"}:
        return "kickstart"

    return "unknown"


def render_unknown_menu(base_url: str) -> str:
    server = UBUNTU_SERVER
    seed = f"http://{server}/ds/default"

    return f"""#!ipxe
dhcp

menu InfraServer Provisioning
item ubuntu  Instalar Ubuntu 24.04
item shell   iPXE shell
choose target && goto ${{target}}

:ubuntu
kernel http://{server}/vmlinuz ip=dhcp url=http://{server}/content/ubuntu/ubuntu-24.04.4-live-server-amd64.iso autoinstall ds=nocloud;s={seed}/ ---
initrd http://{server}/initrd
boot

:shell
shell
"""


def render_host_boot(mac: str, cfg: Dict[str, Any], base_url: str) -> str:
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
kernel {base_url}/content/{distro_path}/{version_path}/images/pxeboot/vmlinuz ip=dhcp inst.repo={base_url}/content/repos/{distro_path}/{version_path}/ inst.ks={base_url}/ks/{mac}.cfg
initrd {base_url}/content/{distro_path}/{version_path}/images/pxeboot/initrd.img
boot
"""

    return render_unknown_menu(base_url)
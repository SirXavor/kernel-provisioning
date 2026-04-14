from typing import Any, Dict

from renderers.common import render_templates


def infer_installer(distro: str) -> str:
    distro = str(distro).strip().lower()

    if distro == "ubuntu":
        return "autoinstall"

    if distro in {"rhel", "rocky", "almalinux", "centos"}:
        return "kickstart"

    return "unknown"


def render_unknown_menu(cfg: Dict[str, Any]) -> str:
    template = """#!ipxe
dhcp

menu InfraServer Provisioning
item --key u ubuntu  Instalar Ubuntu
item --key r rhel    Instalar RHEL
item --key s shell   iPXE shell
choose --default ubuntu --timeout 5000 target && goto ${target}

:ubuntu
kernel http://{{ provisioning.server }}/vmlinuz ip=dhcp url=http://{{ provisioning.server }}/content/ubuntu/{{ provisioning.ubuntu_iso }} autoinstall ds=nocloud;s=http://{{ provisioning.server }}/ds/default/ ---
initrd http://{{ provisioning.server }}/initrd
boot

:rhel
kernel http://{{ provisioning.server }}/content/rhel/{{ provisioning.version }}/images/pxeboot/vmlinuz ip=dhcp inst.repo=http://{{ provisioning.server }}/content/repos/rhel/{{ provisioning.version }}/ inst.ks=http://{{ provisioning.server }}/ks/default.cfg
initrd http://{{ provisioning.server }}/content/rhel/{{ provisioning.version }}/images/pxeboot/initrd.img
boot

:shell
shell
"""
    return render_templates(template, cfg)


def render_host_boot(mac: str, cfg: Dict[str, Any]) -> str:
    provisioning = cfg.get("provisioning", {})
    distro = str(provisioning.get("distro", "ubuntu")).strip().lower()
    version = str(provisioning.get("version", "9")).strip()

    installer = infer_installer(distro)

    if distro == "ubuntu":
        template = """#!ipxe
dhcp
kernel http://{{ provisioning.server }}/vmlinuz ip=dhcp url=http://{{ provisioning.server }}/content/ubuntu/{{ provisioning.ubuntu_iso }} autoinstall ds=nocloud;s=http://{{ provisioning.server }}/ds/{{ mac }}/ ---
initrd http://{{ provisioning.server }}/initrd
boot
"""
        return render_templates(template, {**cfg, "mac": mac})

    if installer == "kickstart":
        template = """#!ipxe
dhcp
kernel http://{{ provisioning.server }}/content/{{ provisioning.distro }}/{{ provisioning.version }}/images/pxeboot/vmlinuz ip=dhcp inst.repo=http://{{ provisioning.server }}/content/repos/{{ provisioning.distro }}/{{ provisioning.version }}/ inst.ks=http://{{ provisioning.server }}/ks/{{ mac }}.cfg
initrd http://{{ provisioning.server }}/content/{{ provisioning.distro }}/{{ provisioning.version }}/images/pxeboot/initrd.img
boot
"""
        return render_templates(template, {**cfg, "mac": mac})

    return render_unknown_menu(cfg)
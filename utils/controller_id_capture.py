import re
import subprocess
from typing import Dict, Optional


def _finalize_entry(entry: dict, devices: Dict[str, dict]) -> None:
    """Store the current entry if it has an address."""
    addr = entry.get("address")
    if addr:
        devices[addr] = dict(entry)


def parse_avahi_output(text: str) -> Dict[str, dict]:
    """Parse raw avahi-browse -r _hexfellow._tcp output.

    Returns a dict mapping IP address (string) -> device info dict with keys:
        hostname, port, txt, interface, ip_version
    """
    devices: Dict[str, dict] = {}
    current_entry = None

    for line in text.splitlines():
        # Match resolved entry line: = enp3s0 IPv4 hexfellow-xxx ... _hexfellow._tcp local
        resolved = re.match(
            r"^= (\S+) (IPv[46]) (\S+)\s+_hexfellow\._tcp\s+local", line
        )
        if resolved:
            # Finalize the previous entry before starting a new one
            if current_entry is not None:
                _finalize_entry(current_entry, devices)

            current_entry = {
                "interface": resolved.group(1),
                "ip_version": resolved.group(2),
                "service_name": resolved.group(3),
            }
            continue

        if current_entry is None:
            continue

        # Parse indented detail lines
        hostname_match = re.match(r"\s+hostname = \[(.+)\]", line)
        if hostname_match:
            current_entry["hostname"] = hostname_match.group(1)
            continue

        address_match = re.match(r"\s+address = \[(.+)\]", line)
        if address_match:
            current_entry["address"] = address_match.group(1)
            continue

        port_match = re.match(r"\s+port = \[(\d+)\]", line)
        if port_match:
            current_entry["port"] = int(port_match.group(1))
            continue

        # Match non-empty txt: txt = ["key=val" "key=val"]
        txt_match = re.match(r"\s+txt = \[(.+)\]", line)
        if txt_match:
            raw_txt = txt_match.group(1)
            pairs = re.findall(r'"([^"]+)"', raw_txt)
            txt_dict = {}
            for p in pairs:
                if "=" in p:
                    k, v = p.split("=", 1)
                    txt_dict[k] = v
            current_entry["txt"] = txt_dict
            continue

        # Match empty txt: txt = []
        if re.match(r"\s+txt = \[\]", line):
            current_entry["txt"] = {}

    # Finalize last entry at end of input
    if current_entry is not None:
        _finalize_entry(current_entry, devices)

    return devices


def build_hostname_map(avahi_text: str) -> Dict[str, str]:
    """Build a simple IP -> hostname mapping from avahi-browse output.

    Returns a dict where keys are IP addresses and values are hostnames.
    """
    devices = parse_avahi_output(avahi_text)
    return {ip: info["hostname"] for ip, info in devices.items()}


def find_hostname_by_ip(ip: str, avahi_text: str) -> Optional[str]:
    """Find the hostname for a given IP address from avahi-browse output.

    Args:
        ip: The IP address to look up (e.g. "172.18.27.120" or "fe80::24c4:ebff:fecf:cfef").
        avahi_text: Raw output from `avahi-browse -r _hexfellow._tcp`.

    Returns:
        The hostname string if found, None otherwise.
    """
    hostname_map = build_hostname_map(avahi_text)
    return hostname_map.get(ip)


def find_hostname_by_ip_live(ip: str, interface: Optional[str] = None,
                            collect_seconds: float = 3.0) -> Optional[str]:
    """Find the hostname for a given IP address by running avahi-browse live.

    avahi-browse -r does not exit on its own — it runs as a daemon.  This function
    collects output for *collect_seconds* then kills the process.

    Args:
        ip: The IP address to look up.
        interface: Optional network interface name (e.g. "enp3s0").
        collect_seconds: How many seconds to collect avahi-browse output before
                         killing the process (default: 10).

    Returns:
        The hostname string if found, None otherwise.
    """
    cmd = ["avahi-browse", "-r", "_hexfellow._tcp"]
    if interface:
        cmd.extend(["-i", interface])
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        try:
            stdout, _ = proc.communicate(timeout=collect_seconds)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, _ = proc.communicate()
        return find_hostname_by_ip(ip, stdout)
    except FileNotFoundError:
        return None


def _sample_avahi_output() -> str:
    """Return sample avahi-browse output for testing."""
    return """= enp3s0 IPv6 hexfellow-940d6533331e205e                    _hexfellow._tcp      local
   hostname = [hexfellow-940d6533331e205e.local]
   address = [fe80::24c4:ebff:fecf:cfef]
   port = [3001]
   txt = ["SecondaryRobotType=RtUnknown" "MainRobotType=RtIotaVc1"]
= enp3s0 IPv4 hexfellow-940d6533331e205e                    _hexfellow._tcp      local
   hostname = [hexfellow-940d6533331e205e.local]
   address = [172.18.27.120]
   port = [3001]
   txt = ["SecondaryRobotType=RtUnknown" "MainRobotType=RtIotaVc1"]
= enp3s0 IPv4 hexfellow-f18ff85aba5ad967                    _hexfellow._tcp      local
   hostname = [hexfellow-f18ff85aba5ad967.local]
   address = [172.18.23.197]
   port = [3001]
   txt = []
= enp3s0 IPv4 hexfellow-ba59fe0cd6bb7849                    _hexfellow._tcp      local
   hostname = [hexfellow-ba59fe0cd6bb7849.local]
   address = [172.18.6.162]
   port = [3001]
   txt = ["SecondaryRobotType=RtUnknown" "MainRobotType=RtHelloArcherY6_H1"]
"""

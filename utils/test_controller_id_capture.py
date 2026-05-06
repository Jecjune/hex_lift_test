#!/usr/bin/env python3
# -*- coding:utf-8 -*-

import unittest
from controller_id_capture import (
    parse_avahi_output,
    build_hostname_map,
    find_hostname_by_ip,
)


class TestParseAvahiOutput(unittest.TestCase):
    def setUp(self):
        self.sample = """= enp3s0 IPv6 hexfellow-940d6533331e205e                    _hexfellow._tcp      local
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

    def test_parse_avahi_output_returns_correct_count(self):
        devices = parse_avahi_output(self.sample)
        self.assertEqual(len(devices), 4)

    def test_parse_avahi_output_ipv4_entry(self):
        devices = parse_avahi_output(self.sample)
        info = devices["172.18.27.120"]
        self.assertEqual(info["hostname"], "hexfellow-940d6533331e205e.local")
        self.assertEqual(info["port"], 3001)
        self.assertEqual(info["interface"], "enp3s0")
        self.assertEqual(info["ip_version"], "IPv4")
        self.assertEqual(
            info["txt"],
            {"SecondaryRobotType": "RtUnknown", "MainRobotType": "RtIotaVc1"},
        )

    def test_parse_avahi_output_ipv6_entry(self):
        devices = parse_avahi_output(self.sample)
        info = devices["fe80::24c4:ebff:fecf:cfef"]
        self.assertEqual(info["hostname"], "hexfellow-940d6533331e205e.local")
        self.assertEqual(info["ip_version"], "IPv6")

    def test_parse_avahi_output_empty_txt(self):
        devices = parse_avahi_output(self.sample)
        info = devices["172.18.23.197"]
        self.assertEqual(info["hostname"], "hexfellow-f18ff85aba5ad967.local")
        self.assertEqual(info["txt"], {})

    def test_parse_avahi_output_robot_type(self):
        devices = parse_avahi_output(self.sample)
        info = devices["172.18.6.162"]
        self.assertEqual(info["txt"]["MainRobotType"], "RtHelloArcherY6_H1")

    def test_parse_avahi_output_empty_string(self):
        devices = parse_avahi_output("")
        self.assertEqual(devices, {})

    def test_parse_avahi_output_no_resolved_entries(self):
        devices = parse_avahi_output("+ enp3s0 IPv4 hexfellow _hexfellow._tcp local")
        self.assertEqual(devices, {})


class TestBuildHostnameMap(unittest.TestCase):
    def setUp(self):
        self.sample = """= enp3s0 IPv4 hexfellow-940d6533331e205e                    _hexfellow._tcp      local
   hostname = [hexfellow-940d6533331e205e.local]
   address = [172.18.27.120]
   port = [3001]
   txt = ["MainRobotType=RtIotaVc1"]
= enp3s0 IPv4 hexfellow-ba59fe0cd6bb7849                    _hexfellow._tcp      local
   hostname = [hexfellow-ba59fe0cd6bb7849.local]
   address = [172.18.6.162]
   port = [3001]
   txt = []
"""

    def test_build_hostname_map_keys_are_addresses(self):
        result = build_hostname_map(self.sample)
        self.assertIn("172.18.27.120", result)
        self.assertIn("172.18.6.162", result)

    def test_build_hostname_map_values_are_hostnames(self):
        result = build_hostname_map(self.sample)
        self.assertEqual(result["172.18.27.120"], "hexfellow-940d6533331e205e.local")
        self.assertEqual(result["172.18.6.162"], "hexfellow-ba59fe0cd6bb7849.local")


class TestFindHostnameByIp(unittest.TestCase):
    def setUp(self):
        self.sample = """= enp3s0 IPv4 hexfellow-940d6533331e205e                    _hexfellow._tcp      local
   hostname = [hexfellow-940d6533331e205e.local]
   address = [172.18.27.120]
   port = [3001]
   txt = ["MainRobotType=RtIotaVc1"]
= enp3s0 IPv6 hexfellow-940d6533331e205e                    _hexfellow._tcp      local
   hostname = [hexfellow-940d6533331e205e.local]
   address = [fe80::24c4:ebff:fecf:cfef]
   port = [3001]
   txt = ["MainRobotType=RtIotaVc1"]
"""

    def test_find_by_ipv4_address(self):
        result = find_hostname_by_ip("172.18.27.120", self.sample)
        self.assertEqual(result, "hexfellow-940d6533331e205e.local")

    def test_find_by_ipv6_address(self):
        result = find_hostname_by_ip("fe80::24c4:ebff:fecf:cfef", self.sample)
        self.assertEqual(result, "hexfellow-940d6533331e205e.local")

    def test_find_nonexistent_ip(self):
        result = find_hostname_by_ip("10.0.0.1", self.sample)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

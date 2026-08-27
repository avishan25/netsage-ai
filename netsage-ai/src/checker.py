"""
checker.py — NetSage AI Deterministic Rule Engine
---------------------------------------------------
This module NEVER calls an LLM. It only uses regular expressions and simple
string/logic checks against the `show_outputs` field of a case to detect
well-known Cisco misconfiguration patterns.

Why this exists (see Problem Statement, section 1.1):
  "Pure LLM solutions lack deterministic guarantees, whereas traditional
   rule engines lack semantic reasoning capabilities."

checker.py is the deterministic half of that hybrid design. If a rule here
matches, the diagnosis is 100% reproducible and does not depend on an LLM
call at all — which is why it is checked BEFORE the AI prompt engine runs
(see engine.py and the System Flowchart in the technical documentation).

Each rule returns a dict shaped exactly like the required JSON output
schema:
    root_cause, osi_layer, confidence, evidence, next_command, fix_steps
"""

import re
from typing import Optional, Dict, Any, List

# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------
# Each rule = (name, compiled_regex, builder_function)
# builder_function(match, show_outputs) -> diagnosis dict
# Rules are checked in order; the FIRST match wins (most specific rules
# should be listed first).


def _rule(root_cause, osi_layer, next_command, fix_steps, confidence=0.95):
    """Helper that returns a closure building the standard diagnosis dict."""
    def build(match: re.Match, show_outputs: str) -> Dict[str, Any]:
        return {
            "root_cause": root_cause,
            "osi_layer": osi_layer,
            "confidence": confidence,
            "evidence": match.group(0).strip(),
            "next_command": next_command,
            "fix_steps": fix_steps,
            "source": "rule_engine",
        }
    return build


RULES: List[tuple] = [
    (
        "sub_interface_admin_down",
        re.compile(r"(GigabitEthernet|FastEthernet)\S*\.\d+\s+is\s+administratively down", re.I),
        _rule(
            "Sub-interface administratively down",
            "Layer 2/3",
            "show ip interface brief",
            ["configure terminal", "interface <sub-interface>", "no shutdown"],
        ),
    ),
    (
        "interface_admin_down",
        re.compile(r"(GigabitEthernet|FastEthernet|Vlan|Serial)\S*\s+is\s+administratively down", re.I),
        _rule(
            "Interface administratively down",
            "Layer 2",
            "show ip interface brief",
            ["configure terminal", "interface <interface>", "no shutdown"],
        ),
    ),
    (
        "dhcp_pool_exhausted",
        re.compile(r"total addresses\s+(\d+).*?leased\s+(\d+)", re.I | re.S),
        None,  # handled specially below because it needs numeric comparison
    ),
    (
        "dns_service_disabled",
        re.compile(r"no ip domain-lookup|ip name-server .* not active", re.I),
        _rule(
            "DNS service disabled or unreachable name-server",
            "Layer 7",
            "show running-config | include name-server",
            ["configure terminal", "ip domain-lookup", "ip name-server <dns-ip>"],
        ),
    ),
    (
        "ospf_hello_mismatch",
        re.compile(r"ip ospf hello-interval\s+(\d+).*?ip ospf hello-interval\s+(\d+)", re.I | re.S),
        None,  # numeric comparison
    ),
    (
        "acl_blocking_http",
        re.compile(r"access-list\s+\d+\s+deny\s+tcp.*?eq\s+80", re.I),
        _rule(
            "Extended ACL blocking HTTP (port 80) traffic",
            "Layer 4",
            "show access-lists",
            ["configure terminal", "no access-list <acl-number> deny tcp ... eq 80",
             "access-list <acl-number> permit tcp ... eq 80"],
        ),
    ),
    (
        "acl_missing_ftp_control",
        re.compile(r"access-list\s+\d+\s+permit\s+tcp.*eq\s+20.*missing port 21", re.I),
        _rule(
            "ACL missing FTP control port 21 permit rule",
            "Layer 4",
            "show access-lists",
            ["configure terminal", "access-list <acl-number> permit tcp <src> <dst> eq 21"],
        ),
    ),
    (
        "acl_missing_https",
        re.compile(r"access-list\s+\S+\s+permit\s+tcp\s+any\s+any\s+eq\s+80.*missing port 443", re.I),
        _rule(
            "ACL blocking SSL/TLS (port 443) traffic",
            "Layer 4",
            "show access-lists",
            ["configure terminal", "access-list <acl-name> permit tcp any any eq 443"],
        ),
    ),
    (
        "nat_overload_missing",
        re.compile(r"ip nat inside source list \d+ interface \S+.*missing overload", re.I),
        _rule(
            "NAT Overload/PAT keyword missing",
            "Layer 3",
            "show ip nat translations",
            ["configure terminal", "ip nat inside source list <acl> interface <if> overload"],
        ),
    ),
    (
        "nat_inside_missing",
        re.compile(r"missing ip nat inside", re.I),
        _rule(
            "NAT interface direction (ip nat inside) missing on internal interface",
            "Layer 3",
            "show ip nat statistics",
            ["configure terminal", "interface <internal-interface>", "ip nat inside"],
        ),
    ),
    (
        "acl_overly_permissive",
        re.compile(r"permit ip \d+\.\d+\.\d+\.\d+ [\d.]+ any", re.I),
        _rule(
            "Overly permissive ACL (guest/isolated VLAN can reach any destination)",
            "Layer 3/4",
            "show access-lists GUEST_ACL",
            ["configure terminal", "ip access-list extended GUEST_ACL",
             "deny ip <guest-subnet> <wildcard> <internal-subnet> <wildcard>",
             "permit ip any any"],
        ),
    ),
    (
        "vlan_pruned_from_trunk",
        re.compile(r"switchport trunk allowed vlan\s+([\d,\s]+)\s*\(VLAN\s+(\d+)\s+missing", re.I),
        _rule(
            "Required VLAN missing from trunk allowed list",
            "Layer 2",
            "show interfaces trunk",
            ["configure terminal", "interface <trunk-port>", "switchport trunk allowed vlan add <vlan-id>"],
        ),
    ),
    (
        "host_gateway_misconfig",
        re.compile(r"Default Gateway\s+([\d.]+).*Host", re.I),
        _rule(
            "Host default gateway does not match router-side gateway IP",
            "Layer 3",
            "show running-config interface <gw-svi>",
            ["Correct the PC's default gateway to match the router/SVI IP address"],
        ),
    ),
    (
        "svi_shutdown",
        re.compile(r"interface Vlan1.*?shutdown", re.I | re.S),
        _rule(
            "Management SVI interface in shutdown state",
            "Layer 2",
            "show ip interface brief | include Vlan",
            ["configure terminal", "interface vlan1", "no shutdown"],
        ),
    ),
    (
        "trunk_should_be_access_mismatch",
        re.compile(r"switchport mode access.*switchport mode access", re.I | re.S),
        _rule(
            "Inter-switch link configured as access instead of trunk",
            "Layer 2",
            "show interfaces trunk",
            ["configure terminal", "interface <inter-switch-link>", "switchport mode trunk"],
        ),
    ),
    (
        "ospf_passive_interface",
        re.compile(r"passive-interface\s+(Serial|GigabitEthernet|FastEthernet)\S*", re.I),
        _rule(
            "Passive interface enabled on an active OSPF link (blocks adjacency)",
            "Layer 3",
            "show ip ospf interface brief",
            ["configure terminal", "router ospf <process-id>", "no passive-interface <interface>"],
        ),
    ),
    (
        "wrong_access_vlan",
        re.compile(r"switchport access vlan\s+(\d+)", re.I),
        _rule(
            "Switch port assigned to wrong access VLAN",
            "Layer 2",
            "show vlan brief",
            ["configure terminal", "interface <port>", "switchport access vlan <correct-vlan-id>"],
        ),
    ),
    (
        "dhcp_helper_missing",
        re.compile(r"missing ip helper-address", re.I),
        _rule(
            "Missing ip helper-address for DHCP relay",
            "Layer 7",
            "show running-config interface <if>",
            ["configure terminal", "interface <if>", "ip helper-address <dhcp-server-ip>"],
        ),
    ),
    (
        "invalid_static_route",
        re.compile(r"ip route\s+([\d.]+)\s+([\d.]+)\s+([\d.]+).*unreachable", re.I),
        _rule(
            "Invalid static route next-hop IP address",
            "Layer 3",
            "show ip route",
            ["configure terminal", "no ip route <network> <mask> <bad-next-hop>",
             "ip route <network> <mask> <correct-next-hop>"],
        ),
    ),
    (
        "radius_secret_mismatch",
        re.compile(r"radius-server host \S+ key \S*incorrect\S*", re.I),
        _rule(
            "RADIUS shared secret mismatch between AP/WLC and RADIUS server",
            "Layer 7",
            "show running-config | include radius",
            ["configure terminal", "radius-server host <ip> key <correct-shared-secret>"],
        ),
    ),
    (
        "native_vlan_mismatch",
        re.compile(r"switchport trunk native vlan\s+(\d+).*switchport trunk native vlan\s+(\d+)", re.I | re.S),
        None,  # numeric comparison
    ),
    (
        "gateway_outside_subnet",
        re.compile(r"Gateway\s+[\d.]+\s+\(Outside subnet boundary\)", re.I),
        _rule(
            "Default gateway address is outside the client's subnet range",
            "Layer 3",
            "show ip interface brief",
            ["Recalculate the subnet boundaries and set a gateway address inside the host subnet"],
        ),
    ),
    (
        "ospf_redistribution_missing_subnets",
        re.compile(r"redistribute eigrp \d+.*missing subnets keyword", re.I),
        _rule(
            "OSPF redistribution missing the 'subnets' keyword",
            "Layer 3",
            "show ip route ospf",
            ["configure terminal", "router ospf <process-id>", "redistribute eigrp <as> subnets"],
        ),
    ),
    (
        "duplicate_ip",
        re.compile(r"%IP-4-DUP_ADDR: Duplicate address ([\d.]+)", re.I),
        _rule(
            "Duplicate IP address assigned to two hosts",
            "Layer 3",
            "show arp",
            ["Identify both hosts holding the duplicate IP and reassign a unique static/DHCP address"],
        ),
    ),
    (
        "vtp_domain_mismatch",
        re.compile(r"vtp domain\s+(\S+).*vtp domain\s+(\S+)", re.I | re.S),
        None,  # case-sensitivity comparison
    ),
    (
        "dai_trust_missing",
        re.compile(r"ip arp inspection trust missing", re.I),
        _rule(
            "Uplink trunk port not configured as a DAI-trusted port",
            "Layer 2",
            "show ip arp inspection interfaces",
            ["configure terminal", "interface <uplink>", "ip arp inspection trust"],
        ),
    ),
    (
        "port_security_violation",
        re.compile(r"%PORT_SECURITY-2-PSECURE_VIOLATION", re.I),
        _rule(
            "Port security violation — MAC address limit exceeded, port err-disabled",
            "Layer 2",
            "show port-security interface <port>",
            ["configure terminal", "interface <port>", "shutdown", "no shutdown",
             "(review allowed MAC address count / sticky MACs)"],
        ),
    ),
    (
        "hsrp_timer_mismatch",
        re.compile(r"standby 1 priority\s+\d+\s+hello\s+(\d+).*standby 1 priority\s+\d+\s+hello\s+(\d+)", re.I | re.S),
        None,  # numeric comparison
    ),
    (
        "missing_dot1q_encapsulation",
        re.compile(r"missing encapsulation dot1[qQ] (\d+)", re.I),
        _rule(
            "Missing 802.1Q encapsulation on router sub-interface",
            "Layer 2/3",
            "show running-config interface <sub-interface>",
            ["configure terminal", "interface <sub-interface>", "encapsulation dot1Q <vlan-id>"],
        ),
    ),
    (
        "ipv6_ra_suppressed",
        re.compile(r"ipv6 nd suppress-ra", re.I),
        _rule(
            "IPv6 Router Advertisements suppressed (SLAAC clients get no prefix)",
            "Layer 3",
            "show ipv6 interface <if>",
            ["configure terminal", "interface <if>", "no ipv6 nd suppress-ra"],
        ),
    ),
    (
        "cdp_disabled_globally",
        re.compile(r"no cdp run", re.I),
        _rule(
            "CDP disabled globally on the device",
            "Layer 2",
            "show cdp neighbors",
            ["configure terminal", "cdp run"],
        ),
    ),
]


def _numeric_pair_rule(show_outputs: str) -> Optional[Dict[str, Any]]:
    """Handles rules that require comparing two numbers/strings pulled out of
    show_outputs rather than a single regex match (hello timers, DHCP pool,
    HSRP timers, VTP domain case, native VLAN mismatch)."""

    # DHCP pool exhaustion: total == leased (and > 0)
    m = re.search(r"total addresses\s+(\d+).*?leased\s+(\d+)", show_outputs, re.I | re.S)
    if m and int(m.group(1)) > 0 and int(m.group(1)) == int(m.group(2)):
        return {
            "root_cause": "DHCP scope pool exhaustion (0 addresses available)",
            "osi_layer": "Layer 7",
            "confidence": 0.95,
            "evidence": m.group(0).strip(),
            "next_command": "show ip dhcp pool",
            "fix_steps": ["configure terminal", "ip dhcp pool <pool-name>",
                          "network <larger-network> <mask>",
                          "(or) ip dhcp excluded-address review to free leases"],
            "source": "rule_engine",
        }

    # OSPF hello-interval mismatch
    m = re.search(r"ip ospf hello-interval\s+(\d+).*?ip ospf hello-interval\s+(\d+)", show_outputs, re.I | re.S)
    if m and m.group(1) != m.group(2):
        return {
            "root_cause": "OSPF hello-interval timer mismatch between neighbors",
            "osi_layer": "Layer 3",
            "confidence": 0.95,
            "evidence": m.group(0).strip(),
            "next_command": "show ip ospf interface",
            "fix_steps": ["configure terminal", "interface <if>", "ip ospf hello-interval <match-neighbor-value>"],
            "source": "rule_engine",
        }

    # Native VLAN mismatch
    m = re.search(r"switchport trunk native vlan\s+(\d+).*switchport trunk native vlan\s+(\d+)",
                   show_outputs, re.I | re.S)
    if m and m.group(1) != m.group(2):
        return {
            "root_cause": "Native VLAN mismatch on trunk link",
            "osi_layer": "Layer 2",
            "confidence": 0.9,
            "evidence": m.group(0).strip(),
            "next_command": "show interfaces trunk",
            "fix_steps": ["configure terminal", "interface <trunk-port>", "switchport trunk native vlan <matching-vlan>"],
            "source": "rule_engine",
        }

    # HSRP hello timer mismatch
    m = re.search(r"standby 1 priority\s+\d+\s+hello\s+(\d+).*standby 1 priority\s+\d+\s+hello\s+(\d+)",
                   show_outputs, re.I | re.S)
    if m and m.group(1) != m.group(2):
        return {
            "root_cause": "HSRP hello timer mismatch between peers causes flapping",
            "osi_layer": "Layer 3",
            "confidence": 0.9,
            "evidence": m.group(0).strip(),
            "next_command": "show standby brief",
            "fix_steps": ["configure terminal", "interface <if>", "standby 1 hello <matching-value>", "standby 1 hold <3x-hello>"],
            "source": "rule_engine",
        }

    # VTP domain case-sensitivity mismatch
    m = re.search(r"vtp domain\s+(\S+).*vtp domain\s+(\S+)", show_outputs, re.I | re.S)
    if m and m.group(1) != m.group(2):
        return {
            "root_cause": "VTP domain name mismatch (case-sensitive) between server and client",
            "osi_layer": "Layer 2",
            "confidence": 0.9,
            "evidence": m.group(0).strip(),
            "next_command": "show vtp status",
            "fix_steps": ["configure terminal", "vtp domain <exact-case-matching-domain-name>"],
            "source": "rule_engine",
        }

    return None


def run_checker(show_outputs: str) -> Dict[str, Any]:
    """
    Run every deterministic rule against `show_outputs`.

    Returns:
        {
          "status": "ERRORS_DETECTED" | "NO_MATCH",
          "diagnosis": <dict or None>
        }

    "NO_MATCH" means the deterministic engine could not classify the case
    and it should be handed off to the LLM prompt engine (see engine.py and
    the flowchart: F -->|No| H[Pass to Prompt Engine for LLM Inference]).
    """
    if not show_outputs:
        return {"status": "NO_MATCH", "diagnosis": None}

    # Try the numeric/pairwise comparison rules first (they're the most
    # specific — two values must actually conflict).
    numeric_hit = _numeric_pair_rule(show_outputs)
    if numeric_hit:
        return {"status": "ERRORS_DETECTED", "diagnosis": numeric_hit}

    for name, pattern, builder in RULES:
        if builder is None:
            continue  # handled by _numeric_pair_rule above
        match = pattern.search(show_outputs)
        if match:
            return {"status": "ERRORS_DETECTED", "diagnosis": builder(match, show_outputs)}

    return {"status": "NO_MATCH", "diagnosis": None}


if __name__ == "__main__":
    # Quick self-test against a couple of sample lines
    samples = [
        "GigabitEthernet0/0.30 is administratively down, line protocol is down",
        "ip dhcp pool LAN_POOL; total addresses 10; leased 10; zero available",
        "R1: ip ospf hello-interval 10; R2: ip ospf hello-interval 20",
        "some totally unmatched string with no known pattern",
    ]
    for s in samples:
        print(s, "->", run_checker(s)["status"])

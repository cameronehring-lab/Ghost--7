#!/usr/bin/env python3
"""
OMEGA PROTOCOL — Security Monitor
Detects port scanning and provides a 'panic' switch to block all Ghost-related exposure.

Usage:
    sudo python3 scripts/security_monitor.py --scan-limit 10
    sudo python3 scripts/security_monitor.py --panic
"""

import os
import sys
import subprocess
import argparse
import collections
import time
import re

# Ghost-specific ports to protect/close in panic mode
GHOST_PORTS = [8000, 8080, 8086, 5432, 6379, 8765]
ALLOWLIST = ["127.0.0.1", "::1"]

def run_cmd(cmd: list[str], check=True) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=check)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command {' '.join(cmd)}: {e.stderr}")
        return ""

def get_active_connections():
    """Parse netstat -an to find source IPs and destination ports."""
    output = run_cmd(["netstat", "-an"])
    connections = collections.defaultdict(set)
    
    # regex to match IP addresses and ports
    # tcp4       0      0  127.0.0.1.52114        *.*                    LISTEN
    # tcp4       0      0  192.168.1.102.8000     192.168.1.5.12345      ESTABLISHED
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 5 or "TCP" not in line and "UDP" not in line:
            continue
            
        local_addr = parts[3]
        foreign_addr = parts[4]
        
        if "*" in foreign_addr or "LISTEN" in line:
            continue
            
        try:
            # Extract port from local address (last segment after dot)
            local_port = int(local_addr.split('.')[-1])
            # Extract IP from foreign address (everything before the last dot)
            foreign_ip = '.'.join(foreign_addr.split('.')[:-1])
            
            if foreign_ip and foreign_ip not in ALLOWLIST:
                connections[foreign_ip].add(local_port)
        except (ValueError, IndexError):
            continue
            
    return connections

def block_ip(ip: str, dry_run=False):
    """Add an IP to a PF block list."""
    print(f"!!! ALERT: Blocking port-scanning IP: {ip}")
    if dry_run:
        print(f"[DRY-RUN] sudo pfctl -t ghost_block -T add {ip}")
        return

    # Ensure the anchor and table exist
    pf_config = f'table <ghost_block> persist\nblock in quick from <ghost_block> to any'
    with open("/tmp/omega_pf.conf", "w") as f:
        f.write(pf_config)
    
    run_cmd(["pfctl", "-a", "omega_security", "-f", "/tmp/omega_pf.conf"], check=False)
    run_cmd(["pfctl", "-t", "ghost_block", "-T", "add", ip], check=False)
    run_cmd(["pfctl", "-e"], check=False) # Enable PF if not enabled

def panic_mode(dry_run=False):
    """Block all incoming traffic to Ghost-specific ports."""
    print("!!! PANIC MODE: Closing all OMEGA ports via firewall !!!")
    ports_str = "{" + ",".join(map(str, GHOST_PORTS)) + "}"
    pf_panic = f'block in quick proto tcp from any to any port {ports_str}\n'
    
    if dry_run:
        print(f"[DRY-RUN] Apply PF rule:\n{pf_panic}")
        return

    with open("/tmp/omega_panic.conf", "w") as f:
        f.write(pf_panic)
        
    run_cmd(["pfctl", "-a", "omega_panic", "-f", "/tmp/omega_panic.conf"])
    run_cmd(["pfctl", "-e"], check=False)
    print("All OMEGA ports are now blocked for incoming traffic.")

def main():
    parser = argparse.ArgumentParser(description="OMEGA Security Monitor")
    parser.add_argument("--scan-limit", type=int, default=10, help="Unique port count threshold (default: 10)")
    parser.add_argument("--panic", action="store_true", help="Close all Ghost ports immediately")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without applying firewall rules")
    parser.add_argument("--interval", type=int, default=5, help="Monitor interval in seconds")
    args = parser.parse_args()

    if os.geteuid() != 0 and not args.dry_run:
        print("Warning: This script must be run as root (sudo) to apply firewall changes.")

    if args.panic:
        panic_mode(args.dry_run)
        return

    print(f"Monitoring active connections (threshold: {args.scan_limit} ports)...")
    try:
        while True:
            connections = get_active_connections()
            for ip, ports in connections.items():
                if len(ports) > args.scan_limit:
                    block_ip(ip, args.dry_run)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopping monitor.")

if __name__ == "__main__":
    main()

#!/bin/bash
# Setup Multi-Queue QoS with WFQ/DRR weights on Open vSwitch port s1-eth3

IFACE="s1-eth3"

echo "[*] Cleaning up existing qdiscs and OVS QoS records on ${IFACE}..."

# 1. Strip Mininet's pre-existing tc qdisc from the interface
sudo tc qdisc del dev ${IFACE} root 2>/dev/null

# 2. Clear any lingering OVS QoS and Queue records
sudo ovs-vsctl --all destroy qos 2>/dev/null
sudo ovs-vsctl --all destroy queue 2>/dev/null
sudo ovs-vsctl clear Port ${IFACE} qos 2>/dev/null

# 3. Create OVS QoS (linux-htb) with Queue 0 (80% weight) and Queue 1 (20% weight)
sudo ovs-vsctl -- set Port ${IFACE} qos=@newqos \
  -- --id=@newqos create QoS type=linux-htb other-config:max-rate=10000000 \
     queues:0=@q0 queues:1=@q1 \
  -- --id=@q0 create Queue other-config:min-rate=8000000 other-config:max-rate=10000000 other-config:priority=1 \
  -- --id=@q1 create Queue other-config:min-rate=2000000 other-config:max-rate=10000000 other-config:priority=2

echo "[*] QoS configuration applied. 80/20 HTB Queues Active."
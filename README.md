# SDN-Driven Dynamic Traffic Slicing & Anti-Starvation Scheduling

This repository contains the implementation of a Software-Defined Networking (SDN) traffic management system. It uses OpenFlow 1.3, Ryu, Open vSwitch (OVS), and Mininet to eliminate bufferbloat and prevent queue starvation via Weighted Fair Queuing (WFQ).

## System & Virtual Machine Requirements

To run this project, you need a Linux-based Virtual Machine (preferably Ubuntu 20.04 LTS) with the following dependencies installed:

* **Mininet:** v2.3.0+ (Network emulator)
* **Open vSwitch (OVS):** (For OpenFlow 1.3 hardware queue execution)
* **Ryu SDN Controller:** (Python-based OpenFlow controller)
* **Linux Traffic Control (`tc`):** (Specifically the HTB queuing discipline)
* **Python 3.8+ Packages:** `flask`, `flask-cors`, `matplotlib`
* **VirtualBox / VM Port Forwarding:** Ensure port `8080` is forwarded from the VM to your host machine to view the live dashboard.

## Execution Steps

To reproduce the experiments and launch the live web telemetry dashboard, you will need three separate terminal sessions attached to your Mininet VM (e.g., via SSH).

### 1. Terminal 1: Start the Ryu Controller
Clean up any stale network namespaces and initialize the OpenFlow 1.3 classifier:
```bash
sudo mn -c
ryu-manager qos_controller.py
```

### 2. Terminal 2: Launch the Mininet Topology
Spin up the 3 hosts and 1 switch with the 10 Mbps bottleneck link:
```bash
sudo python3 topo.py
```

### 3. Terminal 3: Configure Queues & Launch Dashboard
Apply the Linux HTB traffic control queues and start the Flask web server:
```bash
chmod +x setup_queues.sh
./setup_queues.sh
python3 dashboard.py
```

### 4. Access the Live Dashboard
Open a browser on your host machine and navigate to:
```text
http://localhost:8080
```
Use the UI buttons to trigger the live `iperf` contention and starvation tests.

---

## Project Architecture

The system follows a decoupled three-plane SDN architecture:

1. **Data Plane:** Mininet network namespaces and Open vSwitch (OVS) forwarding. A 10 Mbps bottleneck egress link (`s1-eth3`) is partitioned into two Hierarchical Token Bucket (HTB) queues.
2. **Control Plane:** A Ryu SDN Controller dynamically inspects Layer 4 headers via `Packet-In` events. It steers interactive/latency-critical traffic (ICMP/UDP) into Queue 0 and bulk file transfers (TCP) into Queue 1 using `OFPActionSetQueue`.
3. **Management & Telemetry Plane:** A Flask backend polls OpenFlow statistics (`ovs-ofctl queue-stats`) and executes real-time ping probes via `mnexec`. It serves a Chart.js dashboard visualizing real-time throughput (Mbps) and latency (RTT).

## Key Features
* **80/20 Bandwidth Slicing:** Queue 0 (Interactive) is guaranteed 8 Mbps, while Queue 1 (Bulk) is guaranteed a 2 Mbps minimum floor.
* **Bufferbloat Elimination:** Protects sub-10 ms interactive ping latency even when bulk TCP downloads saturate the link 100%.
* **Starvation Defense:** Ensures best-effort TCP flows do not experience complete starvation or connection timeouts during aggressive UDP flooding on the priority queue.
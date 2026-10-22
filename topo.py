#!/usr/bin/env python3
"""
SDN-WFQ Topology: 3 Hosts, 1 Switch, 10Mbps Bottleneck
"""
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info

class QoSNetworkTopo(Topo):
    def build(self):
        # 1. Add hosts
        h1 = self.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')
        h2 = self.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')
        h3 = self.addHost('h3', ip='10.0.0.3/24', mac='00:00:00:00:00:03')

        # 2. Add Open vSwitch (s1)
        s1 = self.addSwitch('s1', cls=OVSSwitch, protocols='OpenFlow13')

        # 3. Connect hosts to the switch
        self.addLink(h1, s1, cls=TCLink, bw=100)
        self.addLink(h2, s1, cls=TCLink, bw=100)

        # 4. Bottleneck Link: s1 to h3 throttled to 10 Mbps with 5ms delay
        self.addLink(s1, h3, cls=TCLink, bw=10, delay='5ms', max_queue_size=50)

def run():
    topo = QoSNetworkTopo()
    net = Mininet(
        topo=topo,
        controller=lambda name: RemoteController(name, ip='127.0.0.1', port=6633),
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=True
    )
    
    info('*** Starting Network\n')
    net.start()

    info('*** Entering Mininet Interactive CLI\n')
    CLI(net)

    info('*** Stopping Network\n')
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    run()
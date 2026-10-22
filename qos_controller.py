#!/usr/bin/env python3
"""
Ryu OpenFlow 1.3 Classifier Controller
Classifies Layer 4 flows into distinct egress hardware queues.
"""
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types, ipv4, tcp, udp, icmp, arp

class QoSController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(QoSController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        req = parser.OFPFlowMod(
            datapath=datapath,
            command=ofproto.OFPFC_DELETE,
            out_port=ofproto.OFPP_ANY,
            out_group=ofproto.OFPG_ANY
        )
        datapath.send_msg(req)

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, priority=0, match=match, actions=actions)
        self.logger.info("Switch s1 connected. Default table-miss rule installed.")

    def add_flow(self, datapath, priority, match, actions, queue_id=None, idle_timeout=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        instruction_actions = []
        if queue_id is not None:
            instruction_actions.append(parser.OFPActionSetQueue(queue_id))
        instruction_actions.extend(actions)

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, instruction_actions)]
        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout
        )
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst = eth.dst
        src = eth.src
        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        out_port = self.mac_to_port[dpid][dst] if dst in self.mac_to_port[dpid] else ofproto.OFPP_FLOOD
        actions = [parser.OFPActionOutput(out_port)]

        arp_pkt = pkt.get_protocol(arp.arp)
        if arp_pkt:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_type=ether_types.ETH_TYPE_ARP)
            self.add_flow(datapath, priority=10, match=match, actions=actions, idle_timeout=60)

        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        if ip_pkt and out_port == 3:
            if ip_pkt.proto in (1, 17): # ICMP / UDP
                match = parser.OFPMatch(in_port=in_port, eth_type=ether_types.ETH_TYPE_IP, ipv4_dst=ip_pkt.dst, ip_proto=ip_pkt.proto)
                self.add_flow(datapath, priority=20, match=match, actions=actions, queue_id=0, idle_timeout=30)
                self.logger.info("[Classifier] Routed %s (proto %d) -> Queue 0", ip_pkt.src, ip_pkt.proto)
            elif ip_pkt.proto == 6: # TCP
                match = parser.OFPMatch(in_port=in_port, eth_type=ether_types.ETH_TYPE_IP, ipv4_dst=ip_pkt.dst, ip_proto=6)
                self.add_flow(datapath, priority=20, match=match, actions=actions, queue_id=1, idle_timeout=30)
                self.logger.info("[Classifier] Routed %s (TCP Bulk) -> Queue 1", ip_pkt.src)

        data = None if msg.buffer_id != ofproto.OFP_NO_BUFFER else msg.data
        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id, in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)
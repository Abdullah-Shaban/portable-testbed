import logging
import time
import sys
import zmq
import uuid
import msgpack

from pytc.Qdisc import *
from pytc.Filter import *

__author__ = "Piotr Gawlowicz"
__copyright__ = "Copyright (c) 2015, Technische Universität Berlin"
__version__ = "0.1.0"
__email__ = "gawlowicz@tkn.tu-berlin.de"

class Node(object):
    def __init__(self, uuid, name):
        self.uuid = uuid
        self.name = name

class Controller(object):
    def __init__(self, dl, ul):
        self.log = logging.getLogger("{module}.{name}".format(
            module=self.__class__.__module__, name=self.__class__.__name__))

        self.myUuid = uuid.uuid4()
        self.myUuidStr = str(self.myUuid)

        self.nodes = []

        self.qdisc_config = None
        self.bnChannel = 11

        self.echoMsgInterval = 3
        self.echoTimeOut = 10

        self.context = zmq.Context()
        self.poller = zmq.Poller()

        self.ul_socket = self.context.socket(zmq.SUB) # one SUB socket for uplink communication over topics
        self.ul_socket.setsockopt(zmq.SUBSCRIBE,  "ALL")
        self.ul_socket.setsockopt(zmq.SUBSCRIBE,  "NEW_NODE")
        self.ul_socket.setsockopt(zmq.SUBSCRIBE,  "NODE_EXIT")
        self.ul_socket.setsockopt(zmq.SUBSCRIBE,  "RESPONSE")
        self.ul_socket.bind(ul)

        self.dl_socket = self.context.socket(zmq.PUB) # one PUB socket for downlink communication over topics
        self.dl_socket.bind(dl)

        #register UL socket in poller
        self.poller.register(self.ul_socket, zmq.POLLIN)


    def add_new_node(self, msg):
        self.log.debug("Adding new node with UUID: {} and Name: {}".format(msg['uuid'], msg['name']))
        newNode = Node(msg['uuid'], msg['name'])
        self.nodes.append(newNode)

        #subscribe to node UUID
        self.ul_socket.setsockopt(zmq.SUBSCRIBE,  newNode.uuid)
        time.sleep(1)

        return newNode


    def remove_node(self, msg):
        self.log.debug("Removing node with UUID: {}, Reason: {}".format(msg['uuid'], msg['reason']))
        pass

    def create_qdisc_config_bn_interface(self):
        #create QDisc configuration TODO: create from config file
        qdiscConfig = QdiscConfig()

        prioSched = PrioScheduler(bandNum=6)
        qdiscConfig.set_root_qdisc(prioSched)

        pfifo0 = prioSched.addQueue(PfifoQueue(limit=100))
        pfifo1 = prioSched.addQueue(PfifoQueue(limit=100))
        pfifo2 = prioSched.addQueue(PfifoQueue(limit=100))
        pfifo3 = prioSched.addQueue(PfifoQueue(limit=100))
        pfifo4 = prioSched.addQueue(PfifoQueue(limit=100))
        pfifo5 = prioSched.addQueue(PfifoQueue(limit=100))

        qdiscConfig.add_queue(pfifo0)
        qdiscConfig.add_queue(pfifo1)
        qdiscConfig.add_queue(pfifo2)
        qdiscConfig.add_queue(pfifo3)
        qdiscConfig.add_queue(pfifo4)
        qdiscConfig.add_queue(pfifo5)

        filter0 = Filter(name="Mesh_Control_Traffic")
        filter0.setFiveTuple(src=None, dst=None, prot='udp', srcPort='698', dstPort='698')
        filter0.setTarget(pfifo0)
        filter0.setTos(Filter.VO)
        prioSched.addFilter(filter0)

        filter1 = Filter(name="Testbed_Management_Traffic")
        filter1.setFiveTuple(src='10.0.0.1', dst=None, prot='tcp', srcPort=None, dstPort='1234')
        filter1.setTarget(pfifo1)
        filter1.setTos(Filter.VI)
        prioSched.addFilter(filter1)

        filter2 = Filter(name="BN_Wireless_Control_Traffic")
        filter2.setFiveTuple(src='192.168.0.1', dst=None, prot='tcp', srcPort=None, dstPort='9980')
        filter2.setTarget(pfifo2)
        filter2.setTos(Filter.VI)
        prioSched.addFilter(filter2)

        filter3 = Filter(name="SUT_Control_Traffic")
        filter3.setFiveTuple(src='192.168.1.1', dst=None, prot='tcp', srcPort=None, dstPort=None)
        filter3.setTarget(pfifo3)
        filter3.setTos(Filter.BE)
        prioSched.addFilter(filter3)

        filter4 = Filter(name="SUT_Experiment_Control_Traffic")
        filter4.setFiveTuple(src='192.168.2.1', dst=None, prot='tcp', srcPort=None, dstPort="1111")
        filter4.setTarget(pfifo3)
        filter4.setTos(Filter.BE)
        prioSched.addFilter(filter4)

        filter5 = Filter(name="SUT_Experiment_Data_Traffic")
        filter5.setFiveTuple(src='192.168.2.1', dst=None, prot='tcp', srcPort=None, dstPort="1122")
        filter5.setTarget(pfifo4)
        filter5.setTos(Filter.BE)
        prioSched.addFilter(filter5)

        filter6 = Filter(name="SUT_Experiment_Monitoring_Traffic")
        filter6.setFiveTuple(src=None, dst='192.168.2.1', prot='tcp', srcPort=None, dstPort='2222')
        filter6.setTarget(pfifo4)
        filter6.setTos(Filter.BE)
        prioSched.addFilter(filter6)

        filter7 = Filter(name="Background_Monitoring_Traffic")
        filter7.setFiveTuple(src=None, dst=None, prot='tcp', srcPort='3333', dstPort='4444')
        filter7.setTarget(pfifo5)
        filter7.setTos(Filter.BK)
        prioSched.addFilter(filter7)

        filter8 = Filter(name="Default_filter")
        filter8.setFiveTuple(src=None, dst=None, prot=None, srcPort=None, dstPort=None)
        filter8.setFilterPriority(2)
        filter8.setTarget(pfifo5)
        filter8.setTos(Filter.BK)
        prioSched.addFilter(filter8)

        qdiscConfig.add_filter(filter0)
        qdiscConfig.add_filter(filter1)
        qdiscConfig.add_filter(filter2)
        qdiscConfig.add_filter(filter3)
        qdiscConfig.add_filter(filter4)
        qdiscConfig.add_filter(filter5)
        qdiscConfig.add_filter(filter6)
        qdiscConfig.add_filter(filter7)
        qdiscConfig.add_filter(filter8)

        self.qdisc_config = qdiscConfig


    def install_egress_scheduler(self, node):
        self.log.debug("Sending QDisc config to node with UUID: {}".format(node.uuid))

        if not self.qdisc_config:
            self.create_qdisc_config_bn_interface()

        #send QDisc configuration to agent
        topic = node.uuid
        cmd = "install_egress_scheduler"
        msg = msgpack.packb(self.qdisc_config.serialize())
        self.dl_socket.send("%s %s %s" % (topic, cmd, msg))

    def set_channel(self, node, channel):
        self.log.debug("Set channel {} to node with UUID: {}".format(channel, node.uuid))

        topic = node.uuid
        cmd = "set_channel"
        msg = msgpack.packb(channel)
        self.dl_socket.send("%s %s %s" % (topic, cmd, msg))

    def monitor_transmission_parameters(self, node):
        self.log.debug("Monitor transmission parameters of BN interface in node with UUID: {}".format(node.uuid))

        topic = node.uuid
        cmd = "monitor_transmission_parameters"
        msg = {"parameters" : ["droppedPackets"]}
        msg = msgpack.packb(msg)
        self.dl_socket.send("%s %s %s" % (topic, cmd, msg))

    def monitor_transmission_parameters_response(self, msg):
        self.log.debug("Monitor transmission parameters response : {}".format(msg))

    def process_msgs(self):
        while True:
            socks = dict(self.poller.poll())

            if self.ul_socket in socks and socks[self.ul_socket] == zmq.POLLIN:
                msg = self.ul_socket.recv()
                topic, cmd, msg = msg.split()
                msg = msgpack.unpackb(msg)
                self.log.debug("Controller received cmd : {} on topic {}".format(cmd, topic))
                if topic == "NEW_NODE":
                    node = self.add_new_node(msg)
                    self.install_egress_scheduler(node)
                    self.set_channel(node, self.bnChannel)
                    self.monitor_transmission_parameters(node)
                elif topic == "NODE_EXIT":
                    self.remove_node(msg)
                elif cmd == "monitor_transmission_parameters_response":
                    self.monitor_transmission_parameters_response(msg)
                else:
                    self.log.debug("Operation not supported")


    def run(self):
        self.log.debug("Controller starts".format())
        try:
            self.process_msgs()

        except KeyboardInterrupt:
            self.log.debug("Controller exits")

        except:
             self.log.debug("Unexpected error:".format(sys.exc_info()[0]))
        finally:
            self.log.debug("Exit")
            self.ul_socket.close()
            self.dl_socket.close()
            self.context.term()

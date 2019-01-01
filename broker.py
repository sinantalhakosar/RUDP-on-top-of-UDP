import socket
import time
import sys
import random
import threading

#Maximum packet size to send 
MAX_PACKET_SIZE = 1000

class SendToDest:

    """  
        Constructor for RDT over UDP with given port and window size
    """
    def __init__(self, port=None, windowSize=5):
        self.port = port
        self.windowSize = windowSize
        self.packets = []
        self.nextSequnceNumber = 0
        self.timer = 0.0
        self.setup()

    """  
        Setup socket to send packets from broker to destination
    """
    def setup(self):
        try:
            #Open UDP connection to send packets
            self.localSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            if self.port is not None:
                self.localSocket.bind(('', self.port))
        except socket.error:
            print("Cannot setup the socket.", file=sys.stderr)
            sys.exit(-1)

    TIMEOUT = 5
   
    """  
        Parse packet and return checkSum, receivedSum, sequence number, flag and data
        Sequence number is 2 byte
        Checksum is 1 byte
        Flag is 1 byte
        And the rest is our data
    """
    def parsePacket(self, data):
        # calculate new checksum
        checkSum = self.checksum(data[1:])
        receivedSum = int.from_bytes(data[:1], byteorder='big')
        seqnum = int.from_bytes(data[1:3], byteorder='big')
        flag = int.from_bytes(data[3:4], byteorder='big')
        data = data[4:]

        return checkSum, receivedSum, seqnum, flag, data


    """  
        Make packet with the given seqnum,data and flag then calculate checksum and return packet
        Sequence number is 2 byte
        Checksum is 1 byte
        Flag is 1 byte
        And the rest is our data
    """
    def makePacket(self, seqnum, data, flag=0):
        packet = (seqnum.to_bytes(2, byteorder='big') +
                        flag.to_bytes(1, byteorder='big') +
                        data)
        # calculate checksum of our packet
        checkSum = self.checksum(packet)
        return checkSum.to_bytes(1, byteorder='big') + packet

    """  
        Calculate checksum with getting sum of our data and and it with 0xff to get unsigned value
    """
    def checksum(self, data):
        return sum(data) & 0xff

    """  
        Send all the given packets from Broker to Destination
    """
    def sendAll(self, sendTo):
        for pkt in self.packets:
            self.localSocket.sendto(pkt, sendTo)

    """  
        Send given packet to the destination and add it to the packets to save and if timeout happends send them again
    """
    def sendPacket(self, pkt, sendTo):
        # Add packet to packets to be able to send it again if timeout occurs
        self.packets.append(pkt)
        self.localSocket.sendto(pkt, sendTo)
        # Get nextSequnceNumber and and it with 0xff to get unsigned value
        self.nextSequnceNumber = (self.nextSequnceNumber + 1) & 0xffff
        # if there is one packet in our list start timer to calculate if there is timeout or not
        if len(self.packets) == 1:
            self.startTimer()

    # Start timer
    def startTimer(self):
        self.timer = time.time()

    """  
        Send single packet to given destination with the given flag
        Flag is 0 for first packet
        Flag is 1 for rest of the packets
        Flag is 2 for last packet
    """
    def send(self, data, sendTo, flag=0):
        # get unacked number from our packet list
        unacked = len(self.packets)
        # create new packet with the given seqnum,flag and data
        packet = self.makePacket(self.nextSequnceNumber, data, flag)
        # get oldest unacked and and it with 0xff to get unsigned value
        lastUnacked = (self.nextSequnceNumber - unacked) & 0xffff
        # Set the timeout for socket
        self.localSocket.settimeout(2)
        lastSent = False

        # Send the last packet
        if flag == 2 and unacked < self.windowSize:
            self.sendPacket(packet)
            lastSent = True

        """  
            Wait for ACK for unacked if unackeds are greater then windowSize or
            If the packet is last one and there is still unacked packets wait for ACK        
        """
        while unacked >= self.windowSize or (flag == 2 and unacked > 0):
            try:
                # Receive ACK from Destination
                pkt, address = self.localSocket.recvfrom(MAX_PACKET_SIZE)

            # If timeout happens at the socket Go back N and send all N packets again
            except socket.timeout:
                if time.time() - self.timer < self.TIMEOUT:
                    self.startTimer()
                    self.sendAll(sendTo)
                    print("Go back N")
            else:
                # Parse packet and get checkSums and sequence number
                checkSum, sum, seq, _, _ = self.parsePacket(pkt)

                # Continue if checksum is correct
                if checkSum == sum:
                    # Set Cumulative ACK number
                    cumAcks = seq - lastUnacked + 1
                    # Since our sequence number is 2 bytes its restart from 0 after a while 
                    if cumAcks < 0:
                        cumAcks = seq + 1 + 0xffff - lastUnacked + 1
                    # Remove the already ACKed packet from our list
                    self.packets = self.packets[cumAcks:]
                    print("seq: {},  cum ACK {}".format(seq, cumAcks), end='\r')
                    # Set unacked packets
                    unacked -= cumAcks
                    # Set last unacked and and it with 0xff to get unsigned value
                    lastUnacked = (lastUnacked + cumAcks) & 0xffff

                    # If there is no unacked packets start timer 
                    if unacked != 0:
                        self.startTimer()
                    # Send the last packet
                    if flag == 2 and not lastSent:
                        self.sendPacket(packet, sendTo)
                        lastSent = True

        # Send packets
        if flag != 2:
            self.sendPacket(packet, sendTo)



class ReceiveFromSource():

    """  
        Constructor to receive packets from Source
    """
    def __init__(self, port=None):
        self.port = port
        try:
            # Setup socket to send packets from broker to destination
            self.localSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if port is not None:
                self.localSocket.bind(('', port))
                self.localSocket.listen()
        except socket.error as e:
            print(e)
            print("Cannot setup the socket.", file=sys.stderr)
            sys.exit(-1)


    def getRandom(self):
        return random.uniform(0,1) < 0.5

    def recv(self):
        # Construct sender with given windowsSize 
        sender = SendToDest(windowSize=10)
        # Set timeout for receiver Socket
        self.receiveSocket.settimeout(.1)
        while True:
            try:
                # Receive packets from Source
                data = self.receiveSocket.recv(MAX_PACKET_SIZE - 4)

                """  
                    Start threads to send the data received from Source and send it from broker to destination
                """
                if self.getRandom():
                    # Create thread with given IP and Port
                    thread1 = threading.Thread(target=sender.send,args = (data,(ipToSend,portToSend),))
                    # Start thread
                    thread1.start()
                    # Join thread the work properly
                    thread1.join()

                else :
                    # Create thread with given IP and Port
                    thread2 = threading.Thread(target=sender.send,args = (data,(ipToSend2,portToSend2),))
                    # Start thread
                    thread2.start()
                    # Join thread to work properly
                    thread2.join()

                # All packets received from Source and send to Destination
                if not data:
                    print("\nReceived.")
                    break
                yield data

            except socket.timeout:
                print('Time out')
                break

    def recvPackets(self):
        try:
            self.receiveSocket, addr = self.localSocket.accept()
        except:
            print("error.", file=sys.stderr)
            sys.exit(-1)
        else:
            # Receive packets from Source
            received = self.recv()
            # Save the received packets to the output.txt
            with open("output.txt", 'wb') as file:
                for data in received:
                    file.write(data)
            self.receiveSocket.close()

    """  
        Close the connection
    """
    def shutDown(self):
        try:
            self.localSocket.close()
        except:
            pass


""" 
    args we take from command line
    first one is Port to the Source
    second one is Destination IP for Router 1
    third one is Destination Port
    forth one is Destination IP for Router 1
    fifth one is Destination Port
"""
argv = sys.argv

port = int(argv[1])

ipToSend = argv[2]

portToSend = int(argv[3])

ipToSend2 = argv[4]

portToSend2 = int(argv[5])

# Construct Broker to receive and send packets
broker = ReceiveFromSource(port)

# Receive packets
broker.recvPackets()

# Close the connection
broker.shutDown()
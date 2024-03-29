from socket import *
from constMP import *  # -
import threading
import random
import time
import pickle

# Counter to make sure we have received handshakes from all other processes
handShakeCount = 0

# UDP sockets to send and receive data messages:
# Create send socket
sendSocket = socket(AF_INET, SOCK_DGRAM)
# Create and bind receive socket
recvSocket = socket(AF_INET, SOCK_DGRAM)
recvSocket.bind(("0.0.0.0", PEER_UDP_PORT))

# TCP socket to receive start signal from the comparison server:
serverSock = socket(AF_INET, SOCK_STREAM)
serverSock.bind(("0.0.0.0", PEER_TCP_PORT))
serverSock.listen(1)


class MsgHandler(threading.Thread):
    # Replicated variable (re-initialized at each session to ease comparison)
    balance = 0

    def __init__(self, sock):
        threading.Thread.__init__(self)
        self.sock = sock

    def run(self):
        print("Handler is ready. Waiting for the handshakes...")

        global handShakeCount

        logList = []

        # Wait until handshakes are received from all other processes
        # (to make sure that all processes are synchronized before they start exchanging messages)
        while handShakeCount < N:
            msgPack = self.sock.recv(1024)
            msg = pickle.loads(msgPack)
            # print ('########## unpickled msgPack: ', msg)
            if msg[0] == "READY":

                # To do: send reply of handshake and wait for confirmation

                handShakeCount = handShakeCount + 1
                print("--- Handshake received: ", msg[1])

        print(
            "Secondary Thread: Received all handshakes. Entering the loop to receive messages."
        )

        stopCount = 0
        while True:
            msgPack = self.sock.recv(1024)  # receive data from client
            msg = pickle.loads(msgPack)

            if msg[0] == -1:  # count the 'stop' messages from the other processes
                stopCount = stopCount + 1
                if stopCount == N:
                    break  # stop loop when all other processes have finished
            else:
                print(
                    "Message "
                    + str(msg[1])
                    + " from process "
                    + str(msg[0])
                    + ". It is "
                    + msg[2]
                    + " of "
                    + str(msg[3])
                )

                if msg[2] == "deposit":
                    self.balance = self.balance + msg[3]

                elif msg[2] == "withdraw":
                    self.balance += msg[3]
                else:
                    # Apply interest rate
                    self.balance = self.balance + self.balance * msg[3] / 100

                logList.append(msg)

        # Write log file
        logFile = open("logfile" + str(myself) + ".log", "w")
        logFile.writelines(str(logList))
        logFile.close()

        # Write final value of the replicated variable
        print("======>>>>> Final balance: " + str(round(self.balance, 3)))

        # Send the list of messages to the server (using a TCP socket) for comparison
        print("Sending the list of messages to the server for comparison...")
        clientSock = socket(AF_INET, SOCK_STREAM)
        clientSock.connect((SERVER_ADDR, SERVER_PORT))
        msgPack = pickle.dumps(logList)
        clientSock.send(msgPack)
        clientSock.close()

        # Reset the handshake counter
        handShakeCount = 0

        exit(0)


# Function to wait for start signal from comparison server:
def waitToStart():
    (conn, addr) = serverSock.accept()
    msgPack = conn.recv(1024)
    msg = pickle.loads(msgPack)
    myself = msg[0]
    mode = msg[1]
    nMsgs = msg[2]
    conn.send(pickle.dumps("Peer process " + str(myself) + " started."))
    conn.close()
    return (myself, mode, nMsgs)


# From here, code is executed when program starts:

while 1:
    print("Waiting for signal to start...")
    (myself, mode, nMsgs) = waitToStart()
    print("I am up, and my ID is: ", str(myself))

    if nMsgs == 0:
        print("Terminating.")
        exit(0)

    if mode == "l":
        PEERS = PEERS_SAME_REGION
    else:
        PEERS = PEERS_TWO_REGIONS

    # Wait for other processes to be ready
    # To Do: fix bug that causes a failure when not all processes are started within this time
    # (fully started processes start sending data messages, which the others try to interpret as control messages)
    time.sleep(5)

    # Create receiving message handler
    msgHandler = MsgHandler(recvSocket)
    msgHandler.start()
    print("Handler started")

    # Send handshakes
    # To do: Must continue sending until it gets a reply from each process
    #        Send confirmation of reply
    for addrToSend in PEERS:
        print("Sending handshake to ", addrToSend)
        msg = ("READY", myself)
        msgPack = pickle.dumps(msg)
        sendSocket.sendto(msgPack, (addrToSend, PEER_UDP_PORT))
        # data = recvSocket.recvfrom(128) # Handshadke confirmations have not yet been implemented

    print("Main Thread: Sent all handshakes. handShakeCount=", str(handShakeCount))

    while handShakeCount < N:
        pass  # find a better way to wait for the handshakes

    # Send a sequence of data messages to all other processes
    for msgNumber in range(0, nMsgs):
        # Wait some random time between successive messages
        time.sleep(random.randrange(10, 100) / 1000)

        opNum = random.randrange(0, NUM_OPS)
        if opNum == 0:
            opValue = random.randrange(depositRange[0], depositRange[1] + 1)
        elif opNum == 2:
            opValue = random.randrange(withdrawRange[0], withdrawRange[1] + 1)
        else:
            opValue = random.randrange(interestRange[0], interestRange[1] + 1)

        msg = (myself, msgNumber, ops[opNum], opValue)
        msgPack = pickle.dumps(msg)
        for addrToSend in PEERS:
            sendSocket.sendto(msgPack, (addrToSend, PEER_UDP_PORT))
            print("Sent message " + str(msgNumber))

    # Tell all processes that I have no more messages to send
    for addrToSend in PEERS:
        msg = (-1, -1)
        msgPack = pickle.dumps(msg)
        sendSocket.sendto(msgPack, (addrToSend, PEER_UDP_PORT))

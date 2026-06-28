import os
import sys

# tools/ live one level below the repo root; put the root on the path so the
# flat live packages (hardwares, ...) import whatever directory we're run from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hardwares.ADS1115 import ADS1115
from hardwares.MCP23017 import MCP23017
import time

ADS = ADS1115(1, 0x49)
ADS.setGain(ADS.PGA_2_048V)
ADS.setDataRate(ADS.DR_860SPS)

MCP = MCP23017(0x27, 16)

#set pin 0-3 to input with pull-up
for i in range(4):
    MCP.pinMode(i, MCP.INPUT)
    MCP.pullUp(i, 1)

def read():
    ADS_0 = ADS.readChannel(0)
    ADS_1 = ADS.readChannel(1)
    MCP_0 = MCP.input(0)
    MCP_1 = MCP.input(1)
    MCP_2 = MCP.input(2)
    MCP_3 = MCP.input(3)
    return (ADS_0, ADS_1, MCP_0, MCP_1, MCP_2, MCP_3)

def readADS():
    ADS_0 = ADS.readChannel(0)
    ADS_1 = ADS.readChannel(1)
    # ADS_1 = 0
    return (ADS_0, ADS_1)

def readMCP():
    MCP_0 = MCP.input(0)
    MCP_1 = MCP.input(1)
    MCP_2 = MCP.input(2)
    MCP_3 = MCP.input(3)
    return (MCP_0, MCP_1, MCP_2, MCP_3)


start = time.time()
for i in range(100):
    readADS()
    # time.sleep(0.1)

print(f"ADS time: {time.time()-start}")

start = time.time()
for i in range(100):
    readMCP()
    # time.sleep(0.1)

print(f"MCP time: {time.time()-start}")
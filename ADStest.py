from hardwares.ADS1115 import ADS1115
from hardwares.MCP23017 import
ADS = ADS1115(1, 0x49)
# set gain to 4.096V max
ADS.setGain(ADS.PGA_4_096V)

def read():
    val_0 = ADS.readChannel(0)
    val_1 = ADS.readChannel(1)
    # print("Analog0: {0:d}\t{1:.3f} V".format(val_0, ADS.getVoltage(val_0)))
    print(f"Analog0: {val_0}")
    print(f"Analog1: {val_1}")

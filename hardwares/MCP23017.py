#!/usr/bin/python

from hardwares.Adafruit_I2C import Adafruit_I2C
import time
import math
import threading

MCP23017_IODIRA = 0x00
MCP23017_IODIRB = 0x01
MCP23017_GPINTENA = 0x04
MCP23017_GPINTENB = 0x05
MCP23017_DEFVALA = 0x06
MCP23017_DEFVALB = 0x07
MCP23017_INTCONA = 0x08
MCP23017_INTCONB = 0x09
MCP23017_IOCON = 0x0A  # 0x0B is the same
MCP23017_GPPUA = 0x0C
MCP23017_GPPUB = 0x0D
MCP23017_GPIOA = 0x12
MCP23017_GPIOB = 0x13
MCP23017_OLATA = 0x14
MCP23017_OLATB = 0x15


class MCP23017(object):
    # constants
    OUTPUT = 0
    INPUT = 1
    LOW = 0
    HIGH = 1

    # set defaults
    def __init__(self, address, num_gpios, busnum=-1):
        assert num_gpios >= 0 and num_gpios <= 16, "Number of GPIOs must be between 0 and 16"
        # busnum being negative will have Adafruit_I2C figure out what is appropriate for your Pi
        self.i2c = Adafruit_I2C(address=address, busnum=busnum)
        self.address = address
        self.num_gpios = num_gpios
        # Serialises every runtime I2C access (input/output/currentVal/read_bank_a)
        # so the background footswitch-poll thread and the Qt GUI main thread (LED
        # writes) can never interleave transactions on the shared bus.
        self._lock = threading.Lock()

        # set defaults
        self.i2c.write8(MCP23017_IODIRA, 0xFF)  # all inputs on port A
        self.i2c.write8(MCP23017_IODIRB, 0xFF)  # all inputs on port B
        self.i2c.write8(MCP23017_GPIOA, 0x00)  # output register to 0
        self.i2c.write8(MCP23017_GPIOB, 0x00)  # output register to 0

        # read the current direction of all pins into instance variable
        # self.direction used for assertions in a few methods methods
        self.direction = self.i2c.readU8(MCP23017_IODIRA)
        self.direction |= self.i2c.readU8(MCP23017_IODIRB) << 8

        # disable the pull-ups on all ports
        self.i2c.write8(MCP23017_GPPUA, 0x00)
        self.i2c.write8(MCP23017_GPPUB, 0x00)

        # clear the IOCON configuration register, which is chip default
        self.i2c.write8(MCP23017_IOCON, 0x00)

        ##### interrupt defaults
        # disable interrupts on all pins by default
        self.i2c.write8(MCP23017_GPINTENA, 0x00)
        self.i2c.write8(MCP23017_GPINTENB, 0x00)
        # interrupt on change register set to compare to previous value by default
        self.i2c.write8(MCP23017_INTCONA, 0x00)
        self.i2c.write8(MCP23017_INTCONB, 0x00)
        # interrupt compare value registers
        self.i2c.write8(MCP23017_DEFVALA, 0x00)
        self.i2c.write8(MCP23017_DEFVALB, 0x00)
        # clear any interrupts to start fresh
        self.i2c.readU8(MCP23017_GPIOA)
        self.i2c.readU8(MCP23017_GPIOB)

    # change a specific bit in a byte
    def _changeBit(self, bitmap, bit, value):
        assert value == 1 or value == 0, "Value is %s must be 1 or 0" % value
        if value == 0:
            return bitmap & ~(1 << bit)
        elif value == 1:
            return bitmap | (1 << bit)

    # set an output pin to a specific value
    # pin value is relative to a bank, so must be be between 0 and 7
    def _readAndChangePin(self, register, pin, value, curValue=None):
        assert pin >= 0 and pin < 8, "Pin number %s is invalid, only 0-%s are valid" % (pin, 7)
        # if we don't know what the current register's full value is, get it first
        if not curValue:
            curValue = self.i2c.readU8(register)
        # set the single bit that corresponds to the specific pin within the full register value
        newValue = self._changeBit(curValue, pin, value)
        # write and return the full register value
        self.i2c.write8(register, newValue)
        return newValue

    # used to set the pullUp resistor setting for a pin
    # pin value is relative to the total number of gpio, so 0-15 on mcp23017
    # returns the whole register value
    def pullUp(self, pin, value):
        assert pin >= 0 and pin < self.num_gpios, "Pin number %s is invalid, only 0-%s are valid" % (
        pin, self.num_gpios)
        # if the pin is < 8, use register from first bank
        if (pin < 8):
            return self._readAndChangePin(MCP23017_GPPUA, pin, value)
        else:
            # otherwise use register from second bank
            return self._readAndChangePin(MCP23017_GPPUB, pin - 8, value) << 8

    # Set pin to either input or output mode
    # pin value is relative to the total number of gpio, so 0-15 on mcp23017
    # returns the value of the combined IODIRA and IODIRB registers
    def pinMode(self, pin, mode):
        assert pin >= 0 and pin < self.num_gpios, "Pin number %s is invalid, only 0-%s are valid" % (
        pin, self.num_gpios)
        # split the direction variable into bytes representing each gpio bank
        gpioa = self.direction & 0xff
        gpiob = (self.direction >> 8) & 0xff
        # if the pin is < 8, use register from first bank
        if (pin < 8):
            gpioa = self._readAndChangePin(MCP23017_IODIRA, pin, mode)
        else:
            # otherwise use register from second bank
            # readAndChangePin accepts pin relative to register though, so subtract
            gpiob = self._readAndChangePin(MCP23017_IODIRB, pin - 8, mode)
            # re-set the direction variable using the new pin modes
        self.direction = gpioa + (gpiob << 8)
        return self.direction

    # set an output pin to a specific value
    def output(self, pin, value):
        assert pin >= 0 and pin < self.num_gpios, "Pin number %s is invalid, only 0-%s are valid" % (
        pin, self.num_gpios)
        assert self.direction & (1 << pin) == 0, "Pin %s not set to output" % pin
        with self._lock:
            # if the pin is < 8, use register from first bank
            if (pin < 8):
                self.outputvalue = self._readAndChangePin(MCP23017_GPIOA, pin, value, self.i2c.readU8(MCP23017_OLATA))
            else:
                # otherwise use register from second bank
                # readAndChangePin accepts pin relative to register though, so subtract
                self.outputvalue = self._readAndChangePin(MCP23017_GPIOB, pin - 8, value, self.i2c.readU8(MCP23017_OLATB))
        return self.outputvalue

    # read the value of a pin
    # return a 1 or 0
    def input(self, pin):
        assert pin >= 0 and pin < self.num_gpios, "Pin number %s is invalid, only 0-%s are valid" % (
        pin, self.num_gpios)
        assert self.direction & (1 << pin) != 0, "Pin %s not set to input" % pin
        value = 0
        # reads the whole register then compares the value of the specific pin
        with self._lock:
            if (pin < 8):
                regValue = self.i2c.readU8(MCP23017_GPIOA)
                if regValue & (1 << pin) != 0: value = 1
            else:
                regValue = self.i2c.readU8(MCP23017_GPIOB)
                if regValue & (1 << pin - 8) != 0: value = 1
        # 1 or 0
        return value

    # Read all eight port-A pins in ONE I2C transaction and return the raw byte.
    # Footswitches live on port A (pins 0-3); the caller masks the bits it needs.
    # This replaces four separate input() calls (one per switch) with a single read.
    def read_bank_a(self):
        with self._lock:
            return self.i2c.readU8(MCP23017_GPIOA)
        # Return current value when output mode

    def currentVal(self, pin):
        assert pin >= 0 and pin < self.num_gpios, "Pin number %s is invalid, only 0-%s are valid" % (
        pin, self.num_gpios)
        value = 0
        # reads the whole register then compares the value of the specific pin
        with self._lock:
            if (pin < 8):
                regValue = self.i2c.readU8(MCP23017_GPIOA)
                if regValue & (1 << pin) != 0: value = 1
            else:
                regValue = self.i2c.readU8(MCP23017_GPIOB)
                if regValue & (1 << pin - 8) != 0: value = 1
        # 1 or 0
        return value

    # cleanup function - set values everything to safe values
    # should be called when program is exiting
    def cleanup(self):
        self.i2c.write8(MCP23017_IODIRA, 0xFF)  # all inputs on port A
        self.i2c.write8(MCP23017_IODIRB, 0xFF)  # all inputs on port B
        # make sure the output registers are set to off
        self.i2c.write8(MCP23017_GPIOA, 0x00)
        self.i2c.write8(MCP23017_GPIOB, 0x00)
        # disable the pull-ups on all ports
        self.i2c.write8(MCP23017_GPPUA, 0x00)
        self.i2c.write8(MCP23017_GPPUB, 0x00)
        # clear the IOCON configuration register, which is chip default
        self.i2c.write8(MCP23017_IOCON, 0x00)

        # disable interrupts on all pins
        self.i2c.write8(MCP23017_GPINTENA, 0x00)
        self.i2c.write8(MCP23017_GPINTENB, 0x00)
        # interrupt on change register set to compare to previous value by default
        self.i2c.write8(MCP23017_INTCONA, 0x00)
        self.i2c.write8(MCP23017_INTCONB, 0x00)
        # interrupt compare value registers
        self.i2c.write8(MCP23017_DEFVALA, 0x00)
        self.i2c.write8(MCP23017_DEFVALB, 0x00)
        # clear any interrupts to start fresh
        self.i2c.readU8(MCP23017_GPIOA)
        self.i2c.readU8(MCP23017_GPIOB)
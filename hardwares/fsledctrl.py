import gpiod
from hardwares.MCP23017 import MCP23017
from kivy.clock import Clock

class Footswitch:
    def __init__(self, mcp, pin):
        self.mcp = mcp
        self.pin = pin
        self.mcp.pinMode(self.pin, self.mcp.INPUT)
        self.mcp.pullUp(self.pin, 1)

    def read(self):
        return 1 if self.mcp.input(self.pin) == 0 else 0

    def __call__(self):
        return self.read()

class FootswitchContainer:
    def __init__(self, footswitches):
        self.footswitches = footswitches

    def __getitem__(self, index):
        return self.footswitches[index].read()

    def __call__(self, index):
        return self.footswitches[index].read()


class LED:
    def __init__(self, mcp, red_pin, blue_pin):
        self.mcp = mcp
        self.red_pin = red_pin
        self.blue_pin = blue_pin
        self.mcp.pinMode(self.red_pin, self.mcp.OUTPUT)
        self.mcp.pinMode(self.blue_pin, self.mcp.OUTPUT)
        self.turnOff()
        self._blink_event = None

    def turnOnRed(self):
        self.mcp.output(self.red_pin, 0)  # Active-low LED

    def turnOffRed(self):
        self.mcp.output(self.red_pin, 1)  # Active-low LED

    def turnOnBlue(self):
        self.mcp.output(self.blue_pin, 0)  # Active-low LED

    def turnOffBlue(self):
        self.mcp.output(self.blue_pin, 1)  # Active-low LED

    def turnOff(self):
        self.turnOffRed()
        self.turnOffBlue()

    def set_state(self, state):
        if state & 0b01:
            self.turnOnBlue()
        else:
            self.turnOffBlue()

        if state & 0b10:
            self.turnOnRed()
        else:
            self.turnOffRed()

    def blink(self, color='red', times=3, interval=0.2):
        """
        Blink the LED in the specified color a given number of times.
        Supports 'red', 'blue', and 'purple' (both red and blue).
        """
        # Cancel any existing blink event for this LED
        if self._blink_event:
            Clock.unschedule(self._blink_event)
            self._blink_event = None

        blink_state = [0]  # Mutable counter

        def toggle(dt):
            if blink_state[0] % 2 == 0:
                # Turn LED(s) on based on the selected color
                if color == 'red':
                    self.turnOnRed()
                elif color == 'blue':
                    self.turnOnBlue()
                elif color == 'purple':
                    self.turnOnRed()
                    self.turnOnBlue()
            else:
                # Turn LED(s) off
                if color == 'red':
                    self.turnOffRed()
                elif color == 'blue':
                    self.turnOffBlue()
                elif color == 'purple':
                    self.turnOffRed()
                    self.turnOffBlue()
            blink_state[0] += 1

            # When done, ensure the LED is off and unschedule
            if blink_state[0] >= times * 2:
                if color == 'red':
                    self.turnOffRed()
                elif color == 'blue':
                    self.turnOffBlue()
                elif color == 'purple':
                    self.turnOffRed()
                    self.turnOffBlue()
                Clock.unschedule(self._blink_event)
                self._blink_event = None

        # Schedule the blinking using the event handle
        self._blink_event = Clock.schedule_interval(toggle, interval)


class LEDContainer:
    def __init__(self, leds):
        self.leds = leds  # List of LED instances

    def __getitem__(self, index):
        # Return the combined state of the red and blue LEDs
        red_state = 1 if self.leds[index].mcp.currentVal(self.leds[index].red_pin) == 0 else 0
        blue_state = 1 if self.leds[index].mcp.currentVal(self.leds[index].blue_pin) == 0 else 0
        return (red_state << 1) | blue_state

    def __setitem__(self, index, value):
        if not (0 <= value <= 3):
            raise ValueError("LED value must be between 0 and 3 (inclusive).")
        self.leds[index].set_state(value)

    def get_led(self, index):
        return self.leds[index]

    def stop_all_blinking(self):
        for led in self.leds:
            if led._blink_event:
                Clock.unschedule(led._blink_event)
                led._blink_event = None
            led.turnOff()


class Controller:
    def __init__(self, address=0x27, num_gpios=16, chip_name='gpiochip4'):
        self.mcp = MCP23017(address=address, num_gpios=num_gpios)

        # Initialize footswitches
        footswitches = [Footswitch(self.mcp, pin) for pin in range(4)]
        self.footswitch = FootswitchContainer(footswitches)

        # Initialize LEDs as pairs (red and blue together)
        leds = [LED(self.mcp, red_pin, blue_pin) for red_pin, blue_pin in zip(range(15, 7, -2), range(14, 6, -2))]
        self.LED = LEDContainer(leds)

        # Configure system interrupt on MCP23017
        self.mcp.configSystemInterrupt(self.mcp.INTMIRRORON, self.mcp.INTPOLACTIVEHIGH)
        for fs in footswitches:
            self.mcp.configPinInterrupt(fs.pin, self.mcp.INTERRUPTON, self.mcp.INTERRUPTCOMPAREPREVIOUS)

        # Set up interrupt pin with gpiod
        self.chip = gpiod.Chip(chip_name)
        self.line = self.chip.get_line(5)  # GPIO pin 5
        self.line.request(consumer="my-interrupt-handler", type=gpiod.LINE_REQ_EV_FALLING_EDGE)

        # Store the last interrupt result
        self.last_interrupt = None

        # External interrupt handler function
        self.external_interrupt_handler = None


    def handle_interrupt(self):
        event = self.line.event_read()  # Blocking until the interrupt occurs
        if event:
            pin, value = self.mcp.readInterrupt()
            self.last_interrupt = (pin, value)
            if self.external_interrupt_handler:
                self.external_interrupt_handler(pin, value)
            self.mcp.clearInterrupts()

    def set_interrupt_handler(self, handler=None):
        """Sets an external interrupt handler function."""
        if handler:
            self.external_interrupt_handler = handler

    def get_last_interrupt(self):
        interrupt = self.last_interrupt
        self.last_interrupt = None  # Clear the interrupt after reading
        return interrupt

    def cleanup(self):
        self.mcp.clearInterrupts()
        self.mcp.cleanup()
        self.line.release()  # Release the GPIO line
        self.chip.close()    # Close the GPIO chip

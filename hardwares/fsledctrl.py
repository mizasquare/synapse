import time

from hardwares.MCP23017 import MCP23017

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
    def __init__(self, mcp, red_pin, blue_pin, scheduler):
        self.mcp = mcp
        self.red_pin = red_pin
        self.blue_pin = blue_pin
        self.scheduler = scheduler  # event-loop timer (see scheduler.Scheduler)
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

    def stop_blink(self):
        """Cancel an in-progress blink, if any."""
        if self._blink_event:
            self.scheduler.unschedule(self._blink_event)
            self._blink_event = None

    def blink(self, color='red', times=3, interval=0.2):
        """
        Blink the LED in the specified color a given number of times.
        Supports 'red', 'blue', and 'purple' (both red and blue).
        """
        # Cancel any existing blink event for this LED
        self.stop_blink()

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
                self.scheduler.unschedule(self._blink_event)
                self._blink_event = None

        # Schedule the blinking using the event handle
        self._blink_event = self.scheduler.schedule_interval(toggle, interval)


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
            led.stop_blink()
            led.turnOff()


class Controller:
    def __init__(self, scheduler, address=0x27, num_gpios=16):
        self.mcp = MCP23017(address=address, num_gpios=num_gpios)

        # Initialize footswitches (each Footswitch configures its pin as input + pull-up)
        footswitches = [Footswitch(self.mcp, pin) for pin in range(4)]
        self.footswitch = FootswitchContainer(footswitches)
        # Pin numbers for the batched single-transaction read below.
        # All four footswitches are on port A (pins 0-3).
        self._fs_pins = [fs.pin for fs in footswitches]

        # Initialize LEDs as pairs (red and blue together). The scheduler drives
        # non-blocking blink timing (see scheduler.Scheduler).
        leds = [LED(self.mcp, red_pin, blue_pin, scheduler) for red_pin, blue_pin in zip(range(15, 7, -2), range(14, 6, -2))]
        self.LED = LEDContainer(leds)

    def read_footswitches(self):
        """Read all four footswitches in a single I2C transaction.

        Switches are wired active-low (pressed -> pin reads 0), so the bit is
        inverted: returns [fs0, fs1, fs2, fs3] where 1 == pressed.
        """
        reg = self.mcp.read_bank_a()
        return [0 if (reg >> pin) & 1 else 1 for pin in self._fs_pins]

    # Shutdown LED ceremony: a ~1.5s "power-down" over the 4 LEDs. Each frame is
    # (hold_seconds, [s0, s1, s2, s3]) with per-LED state 0=off 1=blue 2=red
    # 3=purple. Runs BLOCKING (time.sleep) because it fires from aboutToQuit,
    # after the Qt event loop is gone -- the scheduler can no longer tick.
    _SHUTDOWN_FRAMES = [
        # farewell purple flash
        (0.15, [3, 3, 3, 3]), (0.10, [0, 0, 0, 0]), (0.15, [3, 3, 3, 3]),
        (0.10, [0, 0, 0, 0]),
        # red fills up left->right
        (0.10, [2, 0, 0, 0]), (0.10, [2, 2, 0, 0]), (0.10, [2, 2, 2, 0]),
        (0.10, [2, 2, 2, 2]),
        # then drains away right->left into darkness
        (0.10, [2, 2, 2, 0]), (0.10, [2, 2, 0, 0]), (0.10, [2, 0, 0, 0]),
        (0.10, [0, 0, 0, 0]),
        # last blue heartbeat, then off
        (0.15, [0, 1, 1, 0]), (0.0, [0, 0, 0, 0]),
    ]

    def lightshow_shutdown(self):
        """Play the blocking shutdown LED ceremony (see _SHUTDOWN_FRAMES).

        Safe to call from aboutToQuit cleanup: it drives the LEDs directly with
        time.sleep (no scheduler/event loop needed) and swallows any I/O error so
        a flaky bus can never block process exit."""
        try:
            for hold, states in self._SHUTDOWN_FRAMES:
                for idx, state in enumerate(states):
                    self.LED[idx] = state
                if hold:
                    time.sleep(hold)
        except Exception:
            pass  # never let the farewell blink stall shutdown

    def cleanup(self):
        self.mcp.cleanup()

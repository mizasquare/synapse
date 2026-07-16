"""On-metal encoder bring-up: prove both QT Rotary Encoders read and drive RGB.

This is the hardware counterpart to ``oled_bench`` -- it touches real I2C and so
only runs on the Pi with the two seesaw modules wired (0x36, 0x37). It exercises
the exact driver the app uses (``hw.seesaw._Module``) rather than a private copy,
so a green run here is a green run for the real input path.

Mapping (as requested for the bring-up check):
  * encoder 0 (0x36) rotation -> **hue** of *both* modules' NeoPixels
  * encoder 1 (0x37) rotation -> **brightness** of *both* modules' NeoPixels

So one knob sweeps the colour wheel and the other dims/brightens, and you can see
each encoder's detents land on both LEDs at once -- confirming read direction,
the switch, and NeoPixel output in one glance. Press either encoder to quit
(Ctrl-C also works).

Run: venv/bin/python -m ganglion.tools.encoder_bench
"""

import colorsys
import sys
import time

from ganglion.hw.seesaw import _Module

HUE_PER_DETENT = 1.0 / 24        # 24 detents = full colour wheel
BRIGHT_PER_DETENT = 0.08         # ~13 detents floor..ceil
POLL_HZ = 60


def _rgb(hue, bright):
    r, g, b = colorsys.hsv_to_rgb(hue % 1.0, 1.0, max(0.0, min(1.0, bright)))
    return (int(r * 255), int(g * 255), int(b * 255))


def main():
    import board
    import busio

    i2c = busio.I2C(board.SCL, board.SDA)
    # module[0] drives hue, module[1] drives brightness; both LEDs mirror state.
    modules = [_Module(i2c, 0x36), _Module(i2c, 0x37)]

    hue = 0.0
    bright = 0.4
    print("encoder bring-up: enc0 (0x36)=hue, enc1 (0x37)=brightness. "
          "press either knob to quit.")

    def paint():
        color = _rgb(hue, bright)
        for m in modules:
            m.set_rgb(color)
        return color

    last = paint()
    print(f"  hue={hue:4.2f}  bright={bright:4.2f}  rgb={last}")

    period = 1.0 / POLL_HZ
    while True:
        d_hue = modules[0].read_delta()
        d_bright = modules[1].read_delta()
        if modules[0].read_pressed() or modules[1].read_pressed():
            break
        if d_hue or d_bright:
            hue += d_hue * HUE_PER_DETENT
            bright = max(0.0, min(1.0, bright + d_bright * BRIGHT_PER_DETENT))
            color = paint()
            print(f"  enc0 {d_hue:+d} enc1 {d_bright:+d}  ->  "
                  f"hue={hue % 1.0:4.2f}  bright={bright:4.2f}  rgb={color}")
        time.sleep(period)

    for m in modules:
        m.set_rgb(0)
    print("\nquit -- LEDs off.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

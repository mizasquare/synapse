"""Ganglion — headless interface app for GECO1 (desk mini rig).

Sibling to Synapse (GCaMP6s' touchscreen app). Runs on a pisound+rpi with an
I2C 128x128 SH1107 OLED and two rotary-encoder-switch-RGB-LED modules (seesaw).
Shares Synapse's pure layers (model / modepctrl / monitorfeed / plugincatalog)
by import; owns its own display renderer, input layer, and entry points.

See ganglion/docs/design.md for the design.
"""

# Physical display geometry (SH1107 1.12" mono OLED).
WIDTH = 128
HEIGHT = 128

"""On-device hardware layer for GECO1 (I2C: SH1107 display + 2 seesaw encoders).

Mirrors Synapse's ``hardwares/`` seam: real I2C implementations live here and are
injected explicitly at the entry point, never auto-detected. Off-device
development uses the fakes in ``ganglion.input`` (keyboard) and
``ganglion.display`` (terminal) instead -- see ``ganglion/emulator.py``.
"""

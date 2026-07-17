"""GECO1's tunables — the numbers that describe *this rig*, not the app.

design.md §7 decided these belong in ``ganglion/`` and not in synapse's shared
``configs.py`` (that one is the touchscreen box's, and must not learn about our
panel). This is that file, finally built.

**Why it exists**: the panel's address and rotation were living in *two* places —
``runtime.run_device`` and ``tools/oled_probe`` — each with its own copy of the
same paragraph explaining them. Both are values that (a) were already wrong once
(the code said 0x3C for weeks) and (b) can only be checked against glass. Two
copies of a number like that is where drift starts.

Everything here is **measured, not deduced**. That distinction has cost this
project five times now (address, rotation, bus speed, contrast-vs-current, and
contrast-vs-perception), so each constant says how it was arrived at.

Not here yet, and fine where they are: the seesaw's pins/addresses/brightness
(already cohesive at the top of ``hw/seesaw.py``) and ``runtime.LED_RGB``.
"""

# -- panel identity (design.md §0, §2 "실기 확정") ------------------------------
I2C_ADDR = 0x3D
"""Not the 0x3C that every SH1107 example uses — Adafruit strap the 128x128
module to 0x3D. Found by the panel simply not answering (``i2cdetect -y 1`` =>
``36 37 3d``: both encoders and this)."""

ROTATE = 0
"""Read off the glass (``oled_probe --stage orient``). design.md reasoned "mounts
FFC-down, therefore 180°" and wrote rotate=2; the deduction was wrong. It cost
nothing either way — 0 and 180 are both the SH1107's slow axis — which is exactly
why nothing caught it until there was a panel to look at."""

# -- brightness (SYSTEM > Brightness, ENC1 edits it in place) ------------------
BRIGHT_LEVELS = (0x08, 0x2D, 0xFF)
"""Low (night) / mid / high (daylight), as contrast bytes.

Measured by eye on the **real UI**, which is the whole point: design.md §2 filed
contrast as a weak lever nobody could see, but that was judged on full-white test
screens. Full white saturates the charge pump, so contrast has nothing left to
take away; the real ~15%-lit UI has headroom. Sweeping it there, every halving
from 0xFF down to 0x08 is an obvious step, and below 0x08 nothing changes at all.

So the useful range is [0x08, 0xFF] and perception across it is ratio-based, not
linear. These three sit ~5.6x apart, which is what makes them *look* evenly
spaced. Three rather than the six that are distinguishable: the extra resolution
buys nothing on a device you set once [사용자]."""

BRIGHT_DEFAULT = 1
"""Index into BRIGHT_LEVELS — mid. (Not persisted yet: no settings store exists,
so this is also the value every boot starts at. roadmap ①.)"""

# -- radios (SYSTEM > WiFi / Bluetooth) ---------------------------------------
WIFI_STATES = ("on", "hotspot", "off")
WIFI_DEFAULT = "on"
"""``hotspot`` is why WiFi goes through NetworkManager and not rfkill: rfkill can
only kill a radio, it cannot make an access point.

Stored as names, not indices — a settings file has to keep meaning when someone
re-orders this tuple."""

HOTSPOT_CON = "pb-hotspot"
"""A NetworkManager connection profile that **already existed** on this box: AP
mode, SSID ``starry``, wpa-psk, ``ipv4.method=shared`` (172.24.1.1/24 with NM's
own DHCP), ``autoconnect=no``. We only ever bring it up and down — never edit or
create it, which is why the polkit rule can withhold ``settings.modify.*``.

Nothing here names a *client* SSID on purpose. There are several saved
(Florsheim, KBRI_WiFi6, KT_...); leaving ``on`` to NetworkManager's autoconnect
means the rig follows the user to another room, and another house, by itself."""

BT_STATES = ("on", "off")
BT_DEFAULT = "off"
"""on/off only, so rfkill does it — and `miza`'s `netdev` membership is a *group*
grant, which survives the sessionless service context that defeats polkit's
allow_active. No rule needed for this one."""

# -- idle panel power (burn-in — decisions.md S) -------------------------------
CONTRAST_DIM = 0x01
"""Below the perceptible floor (0x08), so dimming costs nothing to look at while
drawing the least current the panel will draw lit. This is wear control, not a
signal — though at BRIGHT_LEVELS[2] the drop to here is plainly visible."""

IDLE_DIM_S = 30.0
IDLE_OFF_S = 300.0
"""Provisional — the number to fix by living with it, not by reasoning."""

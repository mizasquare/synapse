#!/usr/bin/env python3
"""synapse-volume control daemon — the box's *system volume device*.

Owns master-volume authority end to end: it spawns the jack_mix_box gain stage
("synapsevol", audio path insert), listens for volume *commands* as raw linear
MIDI CC (0-127) on its ``control in`` port, applies the perceptual taper
(raw -> dB -> mixer CC), drives the mixer over a private CC7 link, and echoes
the applied value on ``state out`` so controllers can follow (the motorized-
fader MIDI-feedback idiom).

Ports:
  control in  <- commands. Fed by (a) the shared MOD MIDI bus tap
                (mod-midi-merger:out, so the reflex pedal and any MIDI
                controller can drive it) and (b) a direct link from the app's
                master-volume slider. Listens to CC LISTEN_CC on any channel.
  state out   -> echo of the applied raw value (same CC). The app subscribes
                to sync its slider; re-sent on graph changes so a subscriber
                that connects late still gets the current state.
  mix out     -> private CC7 to "synapsevol:midi in". CC7 exists ONLY on this
                point-to-point link, never on the shared bus (reserved CCs on
                the bus can trigger native handling in plugins).

Taper: jack_mix_box's fader is linear in dB (measured: dB ~= 0.5545*CC - 70.4,
CC127 = 0 dB unity, CC0 = mute — recalibrate with tools/measure-cc-gain.py on
new hardware). A raw linear command maps through an amplitude square law
(TAPER_EXP) so half-travel lands at -12 dB instead of the uselessly quiet
-35 dB a linear CC would give. This logic used to live in the app
(mastervolume.py); it moved here so EVERY controller gets the same volume law.
"""
import argparse
import logging
import math
import signal
import subprocess
import sys
import time

log = logging.getLogger("synapse-volume")

CLIENT_NAME = "synapse-volume"
LISTEN_CC   = 102              # raw volume commands (undefined-CC range, see module doc)
MIXER_DEST  = "synapsevol:midi in"
MIXER_CC    = 7                # jack_mix_box's launch-arg CC (private link only)
BUS_SOURCES = ("mod-midi-merger:out",)   # aggregated hardware MIDI (reflex et al.)
BUS_FALLBACK_PATTERN = "GAAD67"          # non-aggregated boxes: tap the amidithru port

JACK_MIX_BOX = ["/usr/bin/jack_mix_box", "--name=synapsevol",
                "--stereo", "--volume=0", str(MIXER_CC)]

# jack_mix_box fader law (see module doc / measure-cc-gain.py).
DB_PER_CC = 0.5545
CC_UNITY  = 127
TAPER_EXP = 2.0    # amplitude square law; 1.0 = linear amp, 3.0 = finer low end


def raw_to_mixer_cc(raw):
    """Map a raw linear command (0-127) to a jack_mix_box CC via the taper."""
    raw = max(0, min(127, int(raw)))
    if raw == 0:
        return 0                                    # full mute
    if raw >= 127:
        return CC_UNITY                             # unity (0 dB)
    amp = (raw / 127.0) ** TAPER_EXP
    db = 20.0 * math.log10(amp)
    return max(0, min(127, round(CC_UNITY + db / DB_PER_CC)))


# Precomputed so the JACK realtime callback does a table lookup, never math.
TAPER_TABLE = tuple(raw_to_mixer_cc(r) for r in range(128))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--listen-cc", type=int, default=LISTEN_CC)
    ap.add_argument("--mixer-dest", default=MIXER_DEST)
    ap.add_argument("--no-spawn", action="store_true",
                    help="don't spawn jack_mix_box (it's already running)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    import jack   # import late so --help works without JACK installed

    mixer = None
    if not args.no_spawn:
        mixer = subprocess.Popen(JACK_MIX_BOX)
        log.info("spawned jack_mix_box (pid %d)", mixer.pid)

    client = jack.Client(CLIENT_NAME, no_start_server=True)
    ctl_in    = client.midi_inports.register("control in")
    state_out = client.midi_outports.register("state out")
    mix_out   = client.midi_outports.register("mix out")

    listen_cc = args.listen_cc & 0x7F
    # RT-callback state: plain ints, written in the callback / reset from the
    # graph callback. -1 forces a (re)send.
    target = [127]          # raw applied value; boot = unity, matches --volume=0
    last_echo = [-1]
    last_mix = [-1]

    @client.set_process_callback
    def _process(_frames):
        state_out.clear_buffer()
        mix_out.clear_buffer()
        for _offset, data in ctl_in.incoming_midi_events():
            if len(data) == 3:
                b = bytes(data)
                if b[0] & 0xF0 == 0xB0 and b[1] == listen_cc:   # any channel
                    target[0] = b[2] & 0x7F
        t = target[0]
        if t != last_echo[0]:
            state_out.write_midi_event(0, bytes([0xB0, listen_cc, t]))
            last_echo[0] = t
        mix = TAPER_TABLE[t]
        if mix != last_mix[0]:
            mix_out.write_midi_event(0, bytes([0xB0, MIXER_CC, mix]))
            last_mix[0] = mix

    @client.set_graph_order_callback
    def _graph_changed():
        # A (re)connected subscriber needs the current state; resending the
        # mixer CC too is harmless and covers a restarted jack_mix_box.
        last_echo[0] = -1
        last_mix[0] = -1

    client.activate()

    def _connect_quiet(src, dst):
        try:
            client.connect(src, dst)
            log.info("connected %s -> %s", src, dst)
        except jack.JackError:
            pass   # already connected

    def _wire():
        """Lazy wiring, retried forever: services come up in any order."""
        try:
            dst = client.get_port_by_name(args.mixer_dest)
            if dst not in mix_out.connections:
                _connect_quiet(mix_out, dst)
        except jack.JackError:
            pass                     # mixer not up yet
        srcs = []
        for name in BUS_SOURCES:
            try:
                srcs.append(client.get_port_by_name(name))
            except jack.JackError:
                pass
        if not srcs:                 # non-aggregated MIDI setup: tap GAAD67 directly
            srcs = client.get_ports(BUS_FALLBACK_PATTERN, is_midi=True, is_output=True)
        for src in srcs:
            if src not in ctl_in.connections:
                _connect_quiet(src, ctl_in)

    stop = []
    signal.signal(signal.SIGTERM, lambda *_: stop.append(1))
    signal.signal(signal.SIGINT, lambda *_: stop.append(1))
    try:
        while not stop:
            _wire()
            if mixer and mixer.poll() is not None:
                log.error("jack_mix_box exited (%s); bailing for systemd restart",
                          mixer.returncode)
                sys.exit(1)
            time.sleep(2)
    finally:
        client.deactivate()
        client.close()
        if mixer and mixer.poll() is None:
            mixer.terminate()
            try:
                mixer.wait(timeout=3)
            except subprocess.TimeoutExpired:
                mixer.kill()


if __name__ == "__main__":
    main()

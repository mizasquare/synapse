"""Qt-free port of synapse's quick-mode serial wiring — the ONE routing core the
memory constraint demands (reference the pedalboard editor, don't reinvent from
the backend alone). Ported verbatim in semantics from ``editor_bridge.py``:

  - ``desired_wiring``  <- ``_quick_wire_keys`` (editor_bridge.py:803) +
                           ``_connect_audio`` port pairing (editor_bridge.py:775)
  - ``reconcile``       <- ``_reconcile_live_quick`` (editor_bridge.py:1784):
                           connect-first, then disconnect; track on host-ack only.

Shared by the live ``GecoAdapter`` (place/move/remove re-wiring) and the
``geco_conform`` pre-flight (force a board into quick-representable shape).

A *node* here is the minimal dict ``{"inst": str, "ain": [sym...], "aout": [sym...]}``
in chain order. Endpoints are graph-namespace strings the backend's
``connect``/``disconnect`` accept: ``/graph/<inst>/<sym>``, ``/graph/capture_N``
(hardware IN), ``/graph/playback_N`` (hardware OUT).
"""


def _graphify(ep):
    """Normalise a dump_graph endpoint (bare ``inst/sym``) to ``/graph/inst/sym``."""
    return ep if ep.startswith("/graph/") else "/graph/" + ep


def _outs(node, in_mode):
    """Audio output endpoints of ``node`` (or the hardware IN's capture ports)."""
    if node == "IN":
        n = 2 if in_mode == "stereo" else 1
        return ["/graph/capture_%d" % (i + 1) for i in range(n)]
    return ["/graph/%s/%s" % (node["inst"], s) for s in node["aout"]]


def _ins(node):
    """Audio input endpoints of ``node`` (or the hardware OUT's playback ports)."""
    if node == "OUT":
        return ["/graph/playback_1", "/graph/playback_2"]
    return ["/graph/%s/%s" % (node["inst"], s) for s in node["ain"]]


def _pair(fo, ti):
    """Channel pairing rule from ``_connect_audio`` (editor_bridge.py:775):
    1->N fans out (mono into stereo), N->1 fans in (stereo summed to mono),
    else index-parallel zip (L->L, R->R)."""
    if not fo or not ti:
        return []
    if len(fo) == 1 and len(ti) > 1:
        return [(fo[0], t) for t in ti]
    if len(fo) > 1 and len(ti) == 1:
        return [(f, ti[0]) for f in fo]
    return [(fo[i], ti[i]) for i in range(min(len(fo), len(ti)))]


def desired_wiring(nodes, in_mode="mono"):
    """The canonical quick-chain wiring as a set of ``(from_ep, to_ep)`` pairs.

    ``nodes`` is the chain in order. Mirrors ``_quick_wire_keys``: a serial trunk
    of inline fx (``ain>0 and aout>0``) IN -> fx -> ... -> OUT; taps (``aout==0``:
    meters/recorders) fed from the nearest prior trunk fx (or IN); sources
    (``ain==0``: metronomes) into OUT.
    """
    pos = {n["inst"]: i for i, n in enumerate(nodes)}
    fx = [n for n in nodes if n["ain"] and n["aout"]]
    edges = []
    prev = "IN"
    for n in fx:
        edges += _pair(_outs(prev, in_mode), _ins(n))
        prev = n
    if fx:
        edges += _pair(_outs(prev, in_mode), _ins("OUT"))
    for n in nodes:
        if n["ain"] and n["aout"]:
            continue
        if n["aout"] == [] and n["ain"]:                       # tap
            prior = [f for f in fx if pos[f["inst"]] < pos[n["inst"]]]
            edges += _pair(_outs(prior[-1] if prior else "IN", in_mode), _ins(n))
        elif n["ain"] == [] and n["aout"]:                     # source
            edges += _pair(_outs(n, in_mode), _ins("OUT"))
    return set(edges)


def host_wiring(be):
    """The board's actual live audio connections as a ``(from_ep, to_ep)`` set."""
    g = be.dump_graph() or {}
    return {(_graphify(c["source"]), _graphify(c["target"]))
            for c in (g.get("connections") or [])}


def reconcile(be, desired, tracked, log=None):
    """Push the graph from ``tracked`` toward ``desired`` (both endpoint sets).

    Connect-first then disconnect (minimise the audio-silence window), and mutate
    ``tracked`` only on host ack — exactly ``_reconcile_live_quick``. Returns
    ``(tracked, errors)`` where errors is a list of ``(op, frm, to, msg)``.
    """
    to_add = desired - tracked
    to_remove = tracked - desired
    errors = []
    for f, t in sorted(to_add):                                # connect-first
        err = be.connect(f, t)
        if err is None:
            tracked.add((f, t))
        else:
            errors.append(("connect", f, t, err))
            if log:
                log("  ! connect fail %s -> %s : %s" % (f, t, err))
    for f, t in sorted(to_remove):                             # then disconnect
        be.disconnect(f, t)                                    # fail == already gone
        tracked.discard((f, t))
    return tracked, errors

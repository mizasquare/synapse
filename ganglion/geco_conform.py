"""Pre-flight conform — force the live MODEP board into ganglion's quick-
representable shape before the app reads it.

Why a pre-flight (not app logic): the web mod-ui may have left the board in any
state (uncatalogued plugins, non-serial wiring). Rather than teach the app to
render arbitrary graphs, we normalise the board once at launch so the app only
ever sees a clean serial chain (+ allowed meter/recorder taps, metronome
sources) — the same class of board synapse's editor calls "quick-representable".

Policy (user decision 2026-07-06): a plugin *not in the geco whitelist* is one
the user deliberately excluded, so conform DESTROYS it (``remove_effect``).
MIDI/CV-only nodes go too (unrepresentable). Survivors are re-wired to the
canonical quick chain via the shared ``geco_routing`` core. Destructive, so it
defaults to a DRY RUN; ``apply=True`` (CLI ``--apply``) actually mutates the host.

Run standalone:
    python3 -m ganglion.geco_conform          # dry run: print the plan
    python3 -m ganglion.geco_conform --apply  # execute (destructive, live graph)
    python3 -m ganglion.geco_conform --apply --save  # ...and persist the bundle
Or call ``conform(be, catalog_uris, apply=..., save=...)`` from the --live entry.
``--apply`` alone is reversible (reload the bundle); ``--save`` overwrites it.
"""

import os
import sys

from ganglion.geco_backend import load_whitelist
from ganglion.geco_routing import desired_wiring, host_wiring, reconcile


def catalog_uris(buckets=None):
    """The whitelist URI set = the plugins the user chose to keep."""
    buckets = buckets if buckets is not None else load_whitelist()
    return {p["uri"] for b in buckets for p in b["plugins"]}


def _classify(be, keep_uris):
    """Read the live board, split into (survivors, remove). survivors keep chain
    order; a node is a routing dict ``{inst, uri, ain, aout, name}``."""
    import model
    pb = model.initialize_modep_pedalboard(be)
    survivors, remove = [], []
    for e in pb.effects:
        node = {"inst": e.instance, "uri": e.uri, "name": e.name,
                "ain": list(e.audio_inputs or []), "aout": list(e.audio_outputs or [])}
        if e.uri in keep_uris and (node["ain"] or node["aout"]):
            survivors.append(node)
        else:
            remove.append(node)
    return survivors, remove


def plan(be, keep_uris, in_mode="mono"):
    """Compute (survivors, remove, desired, current) without mutating anything."""
    survivors, remove = _classify(be, keep_uris)
    desired = desired_wiring(survivors, in_mode)
    current = host_wiring(be)
    return survivors, remove, desired, current


def conform(be, keep_uris=None, in_mode="mono", apply=False, save=False, log=print):
    """Normalise the live board. Dry-run unless ``apply``. Returns the plan tuple
    ``(survivors, remove, to_add, to_remove)`` (wiring deltas as sorted lists)."""
    keep_uris = keep_uris if keep_uris is not None else catalog_uris()
    survivors, remove, desired, current = plan(be, keep_uris, in_mode)

    log("current board: %s" % be.get_current_pedalboard())
    log("keep %d / remove %d  (in_mode=%s)" % (len(survivors), len(remove), in_mode))
    for n in survivors:
        log("  KEEP   %-20s %s" % (n["inst"][:20], n["uri"]))
    for n in remove:
        why = "uncatalogued" if (n["ain"] or n["aout"]) else "MIDI/CV-only"
        log("  DESTROY %-20s %s  (%s)" % (n["inst"][:20], n["uri"], why))

    if apply:
        for n in remove:                                   # host severs its cables
            err = be.remove_effect(n["inst"])
            if err is not None:
                log("  ! remove fail %s : %s" % (n["inst"], err))
        current = host_wiring(be)                           # re-read after removes

    to_add = sorted(desired - current)
    to_remove = sorted(current - desired)
    log("wiring: +%d connect / -%d disconnect" % (len(to_add), len(to_remove)))
    for f, t in to_add:
        log("  + %s -> %s" % (f, t))
    for f, t in to_remove:
        log("  - %s -> %s" % (f, t))

    if apply:
        reconcile(be, desired, current, log=log)
        if save:
            ok = be.save_current_pedalboard()
            log("save_current_pedalboard -> %s" % ok)
        log("conform applied.")
    else:
        log("(dry run — nothing changed; pass --apply to execute)")
    return survivors, remove, to_add, to_remove


def main(argv):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import modepctrl
    apply = "--apply" in argv
    save = "--save" in argv
    conform(modepctrl.get_backend(), apply=apply, save=save)


if __name__ == "__main__":
    main(sys.argv[1:])

"""MODEP backend abstraction (the host seam).

Decouples the logic layers (presenter, the model classes, the pedalboard
builder) from *how* the MODEP host is reached. Those layers depend only on the
``Backend`` surface below; the on-device implementation is ``modepctrl``'s
``ModepController`` (HTTP to mod-host/mod-ui), wired in by default. Running off
device (e.g. the Windows PyQt6 mock) means injecting a different ``Backend``
that serves fixtures -- see ``modepctrl.set_backend`` and ``fakemodep``.

The fake is injected at this *object seam*; the mod-host/mod-ui wire protocol
(HTTP/socket) is deliberately **not** re-implemented. Method names and return
contracts mirror ``ModepController`` exactly, so ``ModepController`` itself is a
structural ``Backend`` (it does not subclass this) and the swap is name/wiring
only -- the same approach as ``scheduler.Scheduler``.

Return contracts worth noting:
- Write calls (``parameter_set``, ``patch_set``, ``bypass_effect``,
  ``set_bpm``, ``set_bpb``) return ``None`` on success or an error string;
  callers branch on ``error_msg is None``.
- ``snapshot_current_idx`` returns an ``int`` (``-1`` when it can't be
  resolved). ``get_snapshot_list`` returns a dict ``{"0": name, ...}`` (or an
  empty list on host failure); callers use ``len(...)`` and ``str(idx) in ...``.
"""


class Backend:
    """Reach the MODEP host. Default implementation is
    ``modepctrl.ModepController``; grouped here by concern. See the module
    docstring for the return contracts shared across methods.
    """

    # -- Pedalboard / bank -----------------------------------------------------
    def get_current_pedalboard(self):
        """Return the current pedalboard's bundle path (str)."""
        raise NotImplementedError

    def get_pedalboard_info(self, pbpath):
        """Return the full pedalboard description (mod-ui JSON dict)."""
        raise NotImplementedError

    def set_pedalboard(self, board):
        """Load the pedalboard at bundle path ``board``. Returns ``True`` if the
        host's current pedalboard is ``board`` afterward, else ``False`` — a
        destroy-then-reseed caller (the live editor switch) must bail on
        ``False`` since /reset already wiped the graph."""
        raise NotImplementedError

    def get_all_pedalboard_entries(self):
        """All pedalboards as ``[{'bundle','title'}]`` (one call, titles included).
        For the editor's live board switcher; ``[]`` on failure."""
        raise NotImplementedError

    def set_next_pedalboard(self):
        """Switch to the next pedalboard in the host's (ASCII) list order.
        NOTE: footswitch NAVIGATE no longer calls this — the presenter resolves
        the target bundle itself so the user's board_order overlay (utils)
        applies; kept as a plain host-order fallback."""
        raise NotImplementedError

    def set_prev_pedalboard(self):
        """Switch to the previous pedalboard in the host's (ASCII) list order.
        Same NOTE as set_next_pedalboard (presenter owns NAVIGATE order)."""
        raise NotImplementedError

    def get_bank_pedalboard_entries(self, bank_id):
        """Bank ``bank_id``'s pedalboards as ``[{'bundle','title'}]`` for the
        mode-2 footswitch strip. ``[]`` if no such bank / it's empty / failure."""
        raise NotImplementedError

    def get_banks(self):
        """All user banks as ``[{'title','pedalboards':[{'bundle','title'}]}]``
        (the host's bank list). Read side of the bank manager; ``[]`` on failure."""
        raise NotImplementedError

    def save_banks(self, banks):
        """Replace the host's whole user bank list with ``banks`` (the full
        ``[{'title','pedalboards':[{'bundle','title'}]}]`` list, not a delta).
        Returns ``True`` on success."""
        raise NotImplementedError

    # -- Effect / parameter ----------------------------------------------------
    def effect_list(self):
        """Return every installed plugin's native mod-ui info (list of dicts, the
        ``get_all_plugins`` shape). Normalised by ``plugincatalog`` for the editor.
        ``[]`` on failure."""
        raise NotImplementedError

    def effect_get_information(self, uri):
        """Return plugin metadata for ``uri`` (mod-ui JSON dict)."""
        raise NotImplementedError

    def parameter_get(self, instance_id, symbol):
        """Return the current value of ``symbol`` on ``instance_id`` -- bool for
        ``:bypass``, else float; ``None`` on failure."""
        raise NotImplementedError

    def parameter_set(self, instance_id, symbol, value):
        """Set ``symbol`` on ``instance_id`` to ``value``. Return ``None`` on
        success, else an error string."""
        raise NotImplementedError

    def bypass_effect(self, instance, value):
        """Set the bypass state of ``instance``. Return ``None`` on success,
        else an error string."""
        raise NotImplementedError

    def patch_get(self, instance, uri):
        """Return the current patch value for ``uri`` on ``instance`` (``None``
        on failure)."""
        raise NotImplementedError

    def patch_set(self, instance, uri, value):
        """Load patch ``value`` for ``uri`` on ``instance``. Return ``None`` on
        success, else an error string."""
        raise NotImplementedError

    def preset_load(self, instance, preset_uri):
        """Apply LV2 preset ``preset_uri`` to ``instance`` (rewrites several of
        its control ports host-side at once; the caller must re-read values
        afterwards). Return ``None`` on success, else an error string."""
        raise NotImplementedError

    # -- Live graph ------------------------------------------------------------
    def dump_graph(self):
        """Return the live in-memory graph as a pedalboard/info-compatible dict
        ``{"plugins": [...], "connections": [...]}`` -- the *running* JACK graph,
        not the on-disk .ttl -- or ``None`` on failure. ``plugins`` entries carry
        ``instance``/``uri``/``bypassed``/``x``/``y``/``ports`` and connection
        endpoints use the bare on-disk form ('BBCstereo/inR', 'capture_2')."""
        raise NotImplementedError

    # -- Graph mutation --------------------------------------------------------
    # Port/instance arguments are in the graph namespace ('/graph/<inst>/<sym>',
    # bare instance name for add/remove). Higher-level concerns (port-symbol
    # resolution, instance minting, self-echo guard) belong to the caller, not
    # here. All four return ``None`` on success, else an error string.
    def add_effect(self, instance, uri, x=0.0, y=0.0):
        """Add plugin ``uri`` as new instance ``instance`` (bare name) at (x, y)."""
        raise NotImplementedError

    def remove_effect(self, instance):
        """Remove instance ``instance`` (bare name) and its connections."""
        raise NotImplementedError

    def connect(self, port_from, port_to):
        """Connect two graph-namespace ports ('/graph/<inst>/<sym>')."""
        raise NotImplementedError

    def disconnect(self, port_from, port_to):
        """Disconnect two graph-namespace ports ('/graph/<inst>/<sym>')."""
        raise NotImplementedError

    # -- Persist (pedalboard save) ---------------------------------------------
    def save_current_pedalboard(self):
        """Save the current pedalboard in place (asNew=0), serializing the live
        host graph to its .ttl bundle. Returns ``True`` on success. Carries the
        app-side dir==symbolify(title) guard that refuses a mismatched save."""
        raise NotImplementedError

    def save_pedalboard_as(self, title):
        """Save the current live graph as a NEW bundle named ``title`` (asNew=1);
        the host mints a fresh dir and switches current to it. Returns
        ``{'bundlepath','title'}`` on success, else ``None``. Corruption-immune
        (new dir derived from title)."""
        raise NotImplementedError

    # -- Snapshot --------------------------------------------------------------
    def snapshot_current_idx(self):
        """Return the current snapshot index (int; ``-1`` if unknown)."""
        raise NotImplementedError

    def get_snapshot_list(self):
        """Return the snapshot map ``{"0": name, ...}`` (or ``[]`` on failure)."""
        raise NotImplementedError

    def load_snapshot(self, idx):
        """Load snapshot ``idx``."""
        raise NotImplementedError

    def snapshot_save(self, save_pb_also=True):
        """Save over the current snapshot. Return ``True`` on success."""
        raise NotImplementedError

    def snapshot_save_as(self, new_name="New Snapshot", save_pb_also=True):
        """Save the current state as a new snapshot named ``new_name``."""
        raise NotImplementedError

    # -- Transport -------------------------------------------------------------
    def set_bpm(self, value):
        """Set transport BPM. Return ``None`` on success, else an error string."""
        raise NotImplementedError

    def set_bpb(self, value):
        """Set transport beats-per-bar. Return ``None`` on success, else error."""
        raise NotImplementedError

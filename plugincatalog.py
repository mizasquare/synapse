"""Live plugin catalog normaliser (M7).

Maps mod-ui's native ``get_plugin_info`` / ``get_all_plugins`` output into the
condensed schema the pedalboard editor consumes (``editor_bridge`` reads
``self.cat``: ``{count, buckets, plugins}``). This faithfully reproduces the old
frozen ``resources/effects-catalog.json`` baker — verified port-for-port against
it (w/scale/ranges/bucket) — but WITHOUT its 16-control truncation and covering
EVERY installed plugin, so the editor can use the full host catalog.

The source is swapped to live at the backend seam (``backend.effect_list``); this
module is backend-agnostic — real (modepctrl) and fake (fakemodep) both return the
same native shape, which this normalises.
"""

# Canonical bucket order for the browser's left rail — verbatim from the design's
# BUCKET map order (mirrors editor_bridge.BUCKET).
BUCKET_ORDER = ['Drive', 'Comp', 'Gate', 'Dynamics', 'EQ', 'Filter', 'Mod',
                'Delay', 'Reverb', 'Pitch', 'Amp·Cab', 'Synth', 'Spatial',
                'Utility', 'CV', 'MIDI']

# LV2 category -> editor bucket. A sub-category (2nd element of ``category``) wins
# over the primary; both tables derived empirically from the 72-plugin frozen dump.
_SUBCAT = {'Gate': 'Gate', 'Compressor': 'Comp', 'Expander': 'Dynamics',
           'Equaliser': 'EQ', 'Pitch Shifter': 'Pitch', 'Phaser': 'Mod',
           'Flanger': 'Mod', 'Analyser': 'Utility', 'Instrument': 'Synth'}
_PRIMARY = {'Distortion': 'Drive', 'Simulator': 'Amp·Cab', 'Spectral': 'Pitch',
            'Reverb': 'Reverb', 'Delay': 'Delay', 'Modulator': 'Mod',
            'Filter': 'Filter', 'ControlVoltage': 'CV', 'MIDI': 'MIDI',
            'Generator': 'Synth', 'Spatial': 'Spatial', 'Dynamics': 'Dynamics',
            'Utility': 'Utility'}

# Designation suffixes that mark a control port as non-user (host plumbing), so it
# must NOT surface as a knob. Combined with the ``notOnGUI`` property flag.
_SKIP_DESIG = ('#enabled', '#freeWheeling', '#latency', '#sampleRate')


def _bucket(category):
    for c in category:
        if c in _SUBCAT:
            return _SUBCAT[c]
    for c in category:
        if c in _PRIMARY:
            return _PRIMARY[c]
    # Unmapped — a newly-installed plugin whose LV2 category we don't curate.
    # Surface its real category (most specific) rather than dumping it into Utility,
    # so a freshly-installed plugin is never lost from the browser. The editor's
    # node colour/abbrev lookup falls back gracefully for these unknown buckets.
    return category[-1] if category else 'Utility'


def _widget(props, has_scalepoints):
    """Control-port widget kind, in the editor's vocabulary. Reproduces the frozen
    baker (verified 0 mismatches / 402 ports): scalePoints OR enumeration => enum,
    tapTempo => button. (This intentionally differs from model.EffectPort.widget_kind,
    which ignores scalePoints — the editor's catalog consumer expects THIS vocab.)"""
    if 'tapTempo' in props:
        return 'button'
    if 'enumeration' in props or has_scalepoints:
        return 'enum'
    if 'toggled' in props:
        return 'toggle'
    if 'logarithmic' in props:
        return 'log'
    if 'integer' in props:
        return 'step'
    return 'knob'


def _is_user_control(port):
    desig = port.get('designation') or ''
    if any(desig.endswith(s) for s in _SKIP_DESIG):
        return False
    if 'notOnGUI' in (port.get('properties') or []):
        return False
    return True


def _ctl(port):
    r = port.get('ranges') or {}
    sps = port.get('scalePoints') or []
    props = port.get('properties') or []
    return {
        'sym': port.get('symbol', ''),
        'name': port.get('name', ''),
        'short': port.get('shortName') or port.get('name', ''),
        'w': _widget(props, bool(sps)),
        'def': r.get('default', 0.0),
        'min': r.get('minimum', 0.0),
        'max': r.get('maximum', 1.0),
        'unit': (port.get('units') or {}).get('symbol') or '',
        'render': '',
        'scale': [sp.get('label') for sp in sps],
    }


def _plugin(p):
    ports = p.get('ports') or {}
    ctrl_in = (ports.get('control') or {}).get('input') or []
    audio = ports.get('audio') or {}
    midi = ports.get('midi') or {}
    cv = ports.get('cv') or {}
    ai = audio.get('input') or []
    ao = audio.get('output') or []
    ctl = [_ctl(c) for c in ctrl_in if _is_user_control(c)]
    cat = p.get('category') or []
    has_bypass = any((c.get('designation') or '').endswith('#enabled') for c in ctrl_in)
    return {
        'uri': p.get('uri', ''),
        'name': p.get('name', ''),
        'label': p.get('label', '') or p.get('name', ''),
        'brand': p.get('brand', ''),
        'sub': '',
        'comment': p.get('comment', ''),
        'bucket': _bucket(cat),
        'cat': cat,
        'ai': len(ai), 'ao': len(ao),
        'mi': len(midi.get('input') or []), 'mo': len(midi.get('output') or []),
        'cv': len(cv.get('input') or []) + len(cv.get('output') or []),
        'hasBypass': has_bypass,
        'presets': len(p.get('presets') or []),
        'ctlTotal': len(ctl),
        'ctl': ctl,
        # M7 additive (not in the frozen dump): real audio port symbols, so the
        # editor can address ports without a separate effect/get fetch + the
        # catalog-count fallback that risked dropping wires (idx >= len(syms)).
        'ains': [pp.get('symbol', '') for pp in ai],
        'aouts': [pp.get('symbol', '') for pp in ao],
    }


def normalize(native_plugins):
    """``native_plugins``: list of mod-ui ``get_plugin_info`` dicts (or a uri->info
    dict, as ``effect/bulk`` returns). Returns the condensed editor catalog
    ``{count, buckets:[{key,count}], plugins:[...]}``."""
    if isinstance(native_plugins, dict):
        native_plugins = list(native_plugins.values())
    plugins = [_plugin(p) for p in native_plugins if p.get('uri')]
    plugins.sort(key=lambda p: p['name'].lower())
    counts = {}
    for p in plugins:
        counts[p['bucket']] = counts.get(p['bucket'], 0) + 1
    buckets = [{'key': b, 'count': counts[b]} for b in BUCKET_ORDER if b in counts]
    for b in counts:                       # future categories outside the canonical order
        if b not in BUCKET_ORDER:
            buckets.append({'key': b, 'count': counts[b]})
    return {'count': len(plugins), 'buckets': buckets, 'plugins': plugins}

"""Single-producer / single-consumer float32 ring buffer.

The JACK process callback (one writer) appends blocks; the DSP thread (one
reader) periodically grabs the most-recent frame. Same daemon-thread idiom as
monitorfeed.py -- no external deps, relies on CPython's GIL making the integer
head/tail load-store atomic (fine here; a free-threaded build would need
explicit fences).

Capacity is rounded up to a power of two so wrap-around is a mask, not a modulo.
The writer never blocks: on overflow it drops the oldest samples and reports how
many, so a stalled reader degrades to "latest audio only" rather than deadlock.
"""
import numpy as np


def _next_pow2(n):
    p = 1
    while p < n:
        p <<= 1
    return p


class RingBuffer:
    def __init__(self, capacity):
        cap = _next_pow2(int(capacity))
        self._buf = np.zeros(cap, dtype=np.float32)
        self._cap = cap
        self._mask = cap - 1
        self._head = 0   # total samples written (monotonic; writer owns)
        self._tail = 0   # total samples dropped/consumed (writer advances on overflow)

    @property
    def capacity(self):
        return self._cap

    def available(self):
        return self._head - self._tail

    def write(self, block):
        """Append samples (called from the JACK callback -- must not block).

        Returns the number of oldest samples dropped to make room."""
        block = np.asarray(block, dtype=np.float32)
        n = block.shape[0]
        if n == 0:
            return 0
        if n >= self._cap:
            # Block bigger than the whole ring: keep only its tail.
            block = block[-self._cap:]
            n = self._cap
        overflow = max(0, (self._head - self._tail) + n - self._cap)
        self._tail += overflow
        start = self._head & self._mask
        end = start + n
        if end <= self._cap:
            self._buf[start:end] = block
        else:
            split = self._cap - start
            self._buf[start:] = block[:split]
            self._buf[:n - split] = block[split:]
        self._head += n
        return overflow

    def read_latest(self, n, out):
        """Copy the most-recent `n` samples into `out` (called from DSP thread).

        Returns False if fewer than `n` samples are buffered, or if the writer
        wrapped over our copy window before we finished (caller retries next
        tick). On False, `out` is left in an indeterminate state."""
        if n > self._cap:
            raise ValueError("read size %d exceeds capacity %d" % (n, self._cap))
        slack = self._cap - n
        for _ in range(3):
            h0 = self._head
            if h0 - self._tail < n:
                return False
            start = (h0 - n) & self._mask
            end = start + n
            if end <= self._cap:
                out[:] = self._buf[start:end]
            else:
                split = self._cap - start
                out[:split] = self._buf[start:]
                out[split:] = self._buf[:n - split]
            # If the writer advanced no more than `slack` while we copied, the
            # window we read cannot have been overwritten -> the copy is clean.
            if self._head - h0 <= slack:
                return True
        return False

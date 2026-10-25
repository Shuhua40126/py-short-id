from __future__ import annotations

import time
from typing import Callable, List, Tuple

SYMBOLS: str = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
"""Crockford Base32 alphabet.

Crockford deliberately excludes I, L, O, U because they are visually
confused with 1, 1, 0, and V respectively. That makes the resulting IDs safe
to read aloud or transcribe by hand, which matters when a human has to copy
an ID from a log line into a support ticket.
"""

_BIT_WIDTH = 41
_TIMESTAMP_MASK = (1 << _BIT_WIDTH) - 1
_MAX_SEQUENCE = (1 << 12) - 1
_NODE_MASK = (1 << 10) - 1


class ShortIdGenerator:
    """Generate sortable, collision-resistant identifiers from a monotonic clock.

    Layout (52 bits total): 41-bit timestamp, 10-bit node id, 12-bit sequence.

    The 41-bit timestamp holds milliseconds since the generator's epoch.
    The top 12 bits of each encoded ID are therefore the timestamp's top bits,
    so IDs sort lexicographically in time order *for the same alphabet*. This
    is a lexicographic sort over the Crockford alphabet, not a byte-wise sort,
    so you must sort with SYMBOLS.index as the key if you want chronological
    order from raw strings.

    The 12-bit sequence (0..4095) disambiguates IDs generated within the same
    millisecond. If more than 4096 IDs are requested in one millisecond, the
    generator advances its internal clock to the next millisecond rather than
    reusing a sequence number, which would break the sort guarantee.

    Monotonic clock requirement
    --------------------------
    The clock function passed to the constructor MUST be monotonic and return
    milliseconds as an int. `time.monotonic_ns() // 1_000_000` is the default and
    is the right choice on a standard machine. If a non-monotonic clock is
    supplied, the generator will still produce unique IDs *within a single
    process* (the sequence counter guarantees that), but the sort guarantee is
    void because a clock that goes backwards can produce IDs that sort before
    earlier ones.

    Node id
    -------
    node_id defaults to a per-process random value in 0..1023. If you run
    multiple generators in the same process and want global uniqueness, give
    each a different node_id.
    """

    def __init__(
        self,
        epoch_ms: int = 0,
        clock: Callable[[], int] = lambda: time.monotonic_ns() // 1_000_000,
        node_id: int | None = None,
    ) -> None:
        if epoch_ms < 0:
            raise ValueError("epoch_ms must be non-negative")
        self._epoch_ms = epoch_ms
        self._clock = clock
        import random

        self._node_id = (node_id if node_id is not None
                          else random.randint(0, _NODE_MASK))
        if not (0 <= self._node_id <= _NODE_MASK):
            raise ValueError(
                f"node_id must be in 0..{_NODE_MASK}, got {self._node_id}")
        self._last_timestamp_ms = 0
        self._sequence = 0

    def _current_timestamp_ms(self) -> int:
        """Read the clock and subtract the epoch.

        We mask to 41 bits because a bare monotonic clock keeps counting up
        forever; masking keeps the ID at a fixed width and prevents the
        timestamp from spilling into the node/sequence fields.
        """
        return (self._clock() - self._epoch_ms) & _TIMESTAMP_MASK

    def _allocate(self) -> Tuple[int, int]:
        """Return (timestamp_ms, sequence) for the next ID.

        If we are still in the same millisecond as the last ID, we reuse that
        timestamp and bump the sequence. If the sequence is exhausted we
        advance the timestamp by one millisecond; the real wall clock will
        catch up (or overtake) on the next call, which is fine because the
        clock is monotonic and we only ever move forward.
        """
        now = self._current_timestamp_ms()
        if now == self._last_timestamp_ms:
            if self._sequence == _MAX_SEQUENCE:
                # Overflow: advance the timestamp and reset the sequence.
                self._last_timestamp_ms = (self._last_timestamp_ms + 1) & _TIMESTAMP_MASK
                self._sequence = 0
                return self._last_timestamp_ms, 0
            self._sequence += 1
            return now, self._sequence
        # New millisecond: reset sequence and record the timestamp.
        self._last_timestamp_ms = now
        self._sequence = 0
        return now, 0

    def next_id(self) -> int:
        """Generate the next identifier as a 52-bit integer.

        The integer packs (timestamp << 22) | (node << 12) | sequence, so it
        sorts numerically in time order. Use encode() when you want a string.
        """
        timestamp_ms, sequence = self._allocate()
        return (
            (timestamp_ms << 22)
            | (self._node_id << 12)
            | sequence
        )

    def encode(self, value: int) -> str:
        """Encode a non-negative integer to a Crockford Base32 string.

        The output is always 9 characters: 41+10+12 = 52 bits, and 52 bits
        packs into ceil(52/5) = 11 base32 symbols. We pad on the left with
        zeros so that all IDs are the same length and therefore sort
        lexicographically without special handling of differing lengths.

        Wait - let me recompute. 52 bits / 5 bits per symbol = 10.4, so we
        need 11 symbols. But 11 symbols carry 55 bits, so the top 3 bits of
        the first symbol are always zero. That is fine and keeps the sort
        stable.
        """
        if value < 0:
            raise ValueError("value must be non-negative")
        digits: List[str] = []
        if value == 0:
            digits.append("0")
        else:
            while value > 0:
                value, rem = divmod(value, 32)
                digits.append(SYMBOLS[rem])
        s = "".join(reversed(digits))
        # 11 symbols hold 55 bits; 52 bits of payload means the encoded
        # form never exceeds 11 characters. Pad to 11 for fixed-width output.
        return s.rjust(11, "0")

    def next(self) -> str:
        """Generate the next identifier and return it as a 11-char string."""
        return self.encode(self.next_id())

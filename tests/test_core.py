import unittest

from py_short_id import ShortIdGenerator, SYMBOLS


class FakeClock:
    """A controllable monotonic clock for deterministic tests.

    Returns an ever-increasing millisecond count so we never have to call
    time.sleep or assert against wall-clock time.
    """

    def __init__(self, start: int = 0, step: int = 0):
        self._value = start
        self._step = step

    def __call__(self) -> int:
        self._value += self._step
        return self._value


class TestShortIdGenerator(unittest.TestCase):

    def test_next_returns_eleven_char_string(self):
        gen = ShortIdGenerator(clock=FakeClock(start=1000, step=1))
        sid = gen.next()
        self.assertIsInstance(sid, str)
        self.assertEqual(len(sid), 11)

    def test_next_id_returns_int(self):
        gen = ShortIdGenerator(clock=FakeClock(start=1000, step=1),
                               node_id=7)
        self.assertIsInstance(gen.next_id(), int)

    def test_ids_are_unique_within_same_millisecond(self):
        # step=0 means the clock never moves: all IDs share one timestamp.
        gen = ShortIdGenerator(clock=FakeClock(start=5000, step=0),
                               node_id=1)
        ids = [gen.next() for _ in range(1000)]
        self.assertEqual(len(set(ids)), 1000)

    def test_sequence_exhaustion_advances_timestamp(self):
        gen = ShortIdGenerator(clock=FakeClock(start=5000, step=0),
                               node_id=1)
        ids_before_overflow = [gen.next_id() for _ in range(4096)]
        self.assertEqual(len(set(ids_before_overflow)), 4096)
        # The 4097th call must NOT reuse sequence 0 of the same timestamp;
        # the generator should have advanced the timestamp by one ms.
        overflow_id = gen.next_id()
        last_good = ids_before_overflow[-1]
        # Extract timestamp (top 41 bits) via shifting.
        last_ts = last_good >> 22
        overflow_ts = overflow_id >> 22
        self.assertGreater(overflow_ts, last_ts)
        # And the sequence should have reset to 0 in the new millisecond.
        self.assertEqual(overflow_id & 0xFFF, 0)

    def test_ids_sort_lexicographically_over_time(self):
        # Clock steps 5ms per call so every ID gets a distinct timestamp.
        gen = ShortIdGenerator(clock=FakeClock(start=1000, step=5),
                               node_id=3)
        ids = [gen.next() for _ in range(50)]
        # Lexicographic sort using the Crockford alphabet ordering.
        key = lambda s: [SYMBOLS.index(c) for c in s]
        self.assertEqual(ids, sorted(ids, key=key))

    def test_encode_fixed_width_and_alphabet(self):
        gen = ShortIdGenerator(clock=FakeClock(start=0, step=0), node_id=0)
        encoded = gen.encode(0)
        self.assertEqual(encoded, "00000000000")
        for c in gen.encode(123456789):
            self.assertIn(c, SYMBOLS)

    def test_encode_rejects_negative(self):
        gen = ShortIdGenerator(clock=FakeClock(), node_id=0)
        with self.assertRaises(ValueError):
            gen.encode(-1)

    def test_node_id_out_of_range_raises(self):
        with self.assertRaises(ValueError):
            ShortIdGenerator(node_id=1024)
        with self.assertRaises(ValueError):
            ShortIdGenerator(node_id=-1)

    def test_negative_epoch_raises(self):
        with self.assertRaises(ValueError):
            ShortIdGenerator(epoch_ms=-1)

    def test_same_id_at_same_timestamp_and_sequence_for_two_generators(self):
        # Two generators with the same node_id and the same clock state must
        # produce identical IDs for their first call (same ts, seq=0).
        gen_a = ShortIdGenerator(clock=FakeClock(start=42, step=0),
                                 node_id=10)
        gen_b = ShortIdGenerator(clock=FakeClock(start=42, step=0),
                                 node_id=10)
        self.assertEqual(gen_a.next_id(), gen_b.next_id())

    def test_distinct_node_ids_produce_distinct_ids_at_same_timestamp(self):
        gen_a = ShortIdGenerator(clock=FakeClock(start=42, step=0),
                                 node_id=1)
        gen_b = ShortIdGenerator(clock=FakeClock(start=42, step=0),
                                 node_id=2)
        self.assertNotEqual(gen_a.next_id(), gen_b.next_id())

    def test_timestamp_does_not_carry_into_node_or_sequence(self):
        # With a large timestamp, the node and sequence fields must still be
        # cleanly separated. We verify by masking.
        gen = ShortIdGenerator(clock=FakeClock(start=1 << 40, step=0),
                               node_id=5)
        raw = gen.next_id()
        self.assertEqual((raw >> 12) & _10BIT, 5)
        self.assertEqual(raw & 0xFFF, 0)


_10BIT = (1 << 10) - 1


if __name__ == "__main__":
    unittest.main()

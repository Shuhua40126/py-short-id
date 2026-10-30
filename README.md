# py-short-id

Sortable, collision-resistant identifiers from a monotonic clock.

```python
from py_short_id import ShortIdGenerator

# clock returns milliseconds; default uses time.monotonic_ns.
gen = ShortIdGenerator(node_id=1)

s = gen.next()       # 11-character Crockford Base32 string, e.g. "0E0000G40000"
n = gen.next_id()     # same value as a 52-bit integer
```

## Why this exists

The problem: you want short IDs you can put in URLs and logs, but they must
sort in creation order and never collide within a process. UUIDs are too long
and unsorted; a bare timestamp collides under load.

`ShortIdGenerator` packs 41 bits of a monotonic-millisecond timestamp, a 10-bit
node id, and a 12-bit per-millisecond sequence into a 52-bit integer, then
encodes it as 11 characters of Crockford Base32. That gives 4096 IDs per
millisecond per node before the generator bumps into the next millisecond, and
the IDs sort chronologically (using Crockford ordering, not ASCII).

The trade-off: these IDs are only globally unique if each generator has a
distinct `node_id`. The default `node_id` is random, which is fine for a single
process but will collide across processes if you are unlucky. If you run
multiple generators, assign each a different `node_id` in 0..1023.

## The awkward edge

If you generate more than 4096 IDs in a single millisecond, the generator
advances its internal timestamp by one millisecond rather than reusing a
sequence number (which would break the sort guarantee). This means the IDs
remain unique and sorted, but their timestamps will be ahead of the real
clock. In practice this only matters if you compare an ID's embedded
timestamp against wall-clock time, which you should not do.

## Exports

- `ShortIdGenerator` — the class. Constructor keyword args:
  - `epoch_ms` (int, default 0): subtracted from the clock value.
  - `clock` (callable returning int milliseconds, default `time.monotonic_ns // 1_000_000`): must be monotonic.
  - `node_id` (int 0..1023, default random): per-node disambiguator.
- `SYMBOLS` — the 32-character Crockford Base32 alphabet.

Methods:
- `next() -> str` — 11-character encoded ID.
- `next_id() -> int` — 52-bit integer ID.
- `encode(value: int) -> str` — encode any non-negative integer.

## Ambiguity note

The sort guarantee is lexicographic over the Crockford alphabet
(`0..9A..Z` minus `I L O U`), not ASCII. To sort raw ID strings
chronologically, use `SYMBOLS.index` as the sort key.

## Performance

The window keeps a bounded buffer, so `push` is constant time and memory does not
grow with the length of the stream. `peak` and `trough` are linear in the window
size, which is the trade that keeps `push` cheap.


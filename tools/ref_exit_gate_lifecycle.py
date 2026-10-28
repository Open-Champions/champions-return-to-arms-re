"""Independent, bounded gate-list and task-lifecycle rules.

Inputs are synthetic names and caller-supplied hub identity. This module does not
select a campaign hub or infer one from a name. See docs/exits-r3-gate-lifecycle.md.
"""
from dataclasses import dataclass, field


SLOTS = 15
STRIDE = 32
LIST_SIZE = SLOTS * STRIDE
RUN_TASK = (0x27DD74, 20, 0x547E10, 0)
DRAW_TASK = (0x27E2D0, 20, 0x547EF8, 1)
GATE_TASKS = (RUN_TASK, DRAW_TASK)


def qualified_name(base, sub):
    return base + ("_" + sub if sub else "")


@dataclass(frozen=True)
class Destinations:
    count: int
    storage: bytes

    def __post_init__(self):
        if not 0 <= self.count <= 255 or len(self.storage) != LIST_SIZE:
            raise ValueError("invalid list representation")

    def name(self, index):
        if not 0 <= index < SLOTS:
            raise ValueError("slot outside bounded model")
        slot = self.storage[index * STRIDE:(index + 1) * STRIDE]
        if 0 not in slot:
            raise ValueError("unterminated slot outside bounded model")
        return slot.split(b"\0", 1)[0].decode("ascii")

    def replace_name(self, index, value):
        payload = value.encode("ascii") + b"\0"
        if len(payload) > STRIDE or not 0 <= index < SLOTS:
            raise ValueError("unsafe append outside bounded model")
        data = bytearray(self.storage)
        start = index * STRIDE
        data[start:start + len(payload)] = payload
        return Destinations(self.count, bytes(data))

    def reset(self, hub, card_latch):
        if card_latch:
            return self
        replaced = self.replace_name(0, hub)
        return Destinations(1, replaced.storage)

    def discover(self, base, sub, hub, discriminator):
        """Duplicate returns early; append removes only the first stale match.

        String writes include NUL but retain the remainder of each fixed slot.
        The model refuses a new append at capacity; this is a model boundary,
        not a safety check attributed to the executable.
        """
        if self.count > SLOTS:
            raise ValueError("invalid active count outside bounded model")
        current = qualified_name(base, sub)
        if any(self.name(i) == current for i in range(self.count)):
            return self
        added = self.replace_name(self.count, current)
        added = Destinations(self.count + 1, added.storage)
        stale = next((i for i in range(added.count)
                      if discriminator in added.name(i) and added.name(i) != hub), None)
        if stale is None:
            return added
        for i in range(stale, added.count - 1):
            added = added.replace_name(i, added.name(i + 1))
        return Destinations(added.count - 1, added.storage)

    def save(self):
        signed_count = self.count if self.count < 128 else self.count - 256
        return signed_count.to_bytes(4, "little", signed=True) + self.storage

    @classmethod
    def restore(cls, packet):
        if len(packet) != LIST_SIZE + 4:
            raise ValueError("unexpected fixed save size")
        return cls(int.from_bytes(packet[:4], "little") & 255, packet[4:])


@dataclass
class Tasks:
    records: list = field(default_factory=list)
    cursor: int = 0

    def add(self, record):
        if any(old[0] == record[0] for old in self.records):
            return
        index = next((i for i, old in enumerate(self.records)
                      if old[1] > record[1]), len(self.records))
        self.records.insert(index, record)
        if self.cursor >= index:
            self.cursor += 1

    def remove(self, function):
        index = next((i for i, old in enumerate(self.records) if old[0] == function), None)
        if index is not None:
            del self.records[index]
            if self.cursor >= index:
                self.cursor -= 1

    def dispatch(self, exclude, include, invoke):
        self.cursor = 0
        while self.cursor < len(self.records):
            fn, _priority, _name, flags = self.records[self.cursor]
            if not flags & exclude and (include == -1 or flags & include):
                invoke(fn)
            self.cursor += 1


def opened_fields(destination, chooser):
    return (0, chooser & 255, 0, destination)


def interaction_opens(mutex, network):
    return not mutex or bool(network)


def cleanup(tasks, travel):
    if travel == 0:
        for record in GATE_TASKS:
            tasks.remove(record[0])


def terminal_tick(state, travel, tasks):
    if state == 6:
        return 7, travel
    if state == 7:
        cleanup(tasks, 0)
        return 7, 0
    raise ValueError("only terminal states are modelled here")

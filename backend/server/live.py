"""Live updates: an in-process publish/subscribe bus with one channel per organisation. The web app reads it over Server-Sent Events
(routes_live.py), so a new message, a new alert or a connector's state shows on every open page within a second.

Anything may publish from any thread (a mailbox connector, a webhook, an API call). Each open browser tab has its own bounded queue on the
server's event loop; a tab that stops reading gets a 'resync' and reloads instead of holding memory.
One server process only. With several processes or servers, put a broker (for example Redis pub/sub) behind publish()."""
import asyncio, itertools, threading, time


class _Sub:
    __slots__ = ("org_id", "loop", "q")

    def __init__(self, org_id, loop):
        self.org_id, self.loop, self.q = org_id, loop, asyncio.Queue(maxsize=500)


def _offer(q: asyncio.Queue, msg: dict):
    if q.full():
        while not q.empty(): q.get_nowait()
        msg = {"seq": msg["seq"], "type": "resync", "data": {}}
    q.put_nowait(msg)


class Bus:
    def __init__(self):
        self._subs, self._lock, self._seq = {}, threading.Lock(), itertools.count(1)

    def subscribe(self, org_id: int) -> _Sub:
        s = _Sub(org_id, asyncio.get_running_loop())
        with self._lock: self._subs.setdefault(org_id, set()).add(s)
        return s

    def unsubscribe(self, s: _Sub):
        with self._lock:
            subs = self._subs.get(s.org_id)
            if subs is not None: subs.discard(s)

    def listeners(self, org_id: int) -> int:
        with self._lock: return len(self._subs.get(org_id, ()))

    def publish(self, org_id: int, event_type: str, /, **data) -> dict:
        """Sends {"seq", "type", "data"} to every open page of the organisation; the stream turns it into 'id:', 'event:' and 'data:' lines."""
        msg = {"seq": next(self._seq), "type": event_type, "data": {**data, "sent_at": time.time()}}
        with self._lock: subs = list(self._subs.get(org_id, ()))
        for s in subs:
            try: s.loop.call_soon_threadsafe(_offer, s.q, msg)
            except RuntimeError: self.unsubscribe(s)          # its event loop has closed
        return msg


bus = Bus()

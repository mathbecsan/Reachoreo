"""A tiny publish/subscribe bus over ZeroMQ: every process publishes on its own port.

Topics: "clock" (conductor), "dancer" (perception), "robot.A" / "robot.B" (agents),
"event" (anyone). Payloads are JSON dicts.
"""
from __future__ import annotations

import json

import zmq


class Publisher:
    def __init__(self, bind_addr: str):
        self.sock = zmq.Context.instance().socket(zmq.PUB)
        self.sock.setsockopt(zmq.SNDHWM, 100)
        self.sock.bind(bind_addr)

    def send(self, topic: str, payload: dict):
        self.sock.send_multipart([topic.encode(), json.dumps(payload).encode()])

    def close(self):
        self.sock.close(linger=0)


class Subscriber:
    def __init__(self, connect_addrs: list[str], topics: list[str]):
        self.sock = zmq.Context.instance().socket(zmq.SUB)
        self.sock.setsockopt(zmq.RCVHWM, 1000)
        for a in connect_addrs:
            self.sock.connect(a)
        for t in topics:
            self.sock.setsockopt(zmq.SUBSCRIBE, t.encode())

    def drain(self) -> list[tuple[str, dict]]:
        """Everything that arrived since the last call, without blocking."""
        out = []
        while True:
            try:
                topic, data = self.sock.recv_multipart(flags=zmq.NOBLOCK)
            except zmq.Again:
                return out
            out.append((topic.decode(), json.loads(data)))

    def close(self):
        self.sock.close(linger=0)

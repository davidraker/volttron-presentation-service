"""An external OpenFMB participant on a real MQTT broker: publishes control profiles, collects reading and control
profiles, as a utility system or another adapter would. Uses paho-mqtt directly and the protobuf bindings; nothing of
the platform's adapters is involved."""
import threading
import time

import paho.mqtt.client as mqtt

from interoperability.codecs.openfmb import decode, encode


class OpenFmbParty:
    def __init__(self, host: str = '127.0.0.1', port: int = 1883, client_id: str = 'e2e-external-openfmb'):
        self.host, self.port = host, port
        self.received: list[tuple[str, bytes, float]] = []
        self._lock = threading.Lock()
        self._connected = threading.Event()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        self._connected.set()

    def _on_message(self, client, userdata, message):
        with self._lock:
            self.received.append((message.topic, bytes(message.payload), time.time()))

    def start(self, subscribe: list[str], timeout: float = 10.0):
        self.client.connect(self.host, self.port, keepalive=30)
        self.client.loop_start()
        if not self._connected.wait(timeout):
            raise RuntimeError(f'MQTT broker at {self.host}:{self.port} did not accept the external party')
        for topic in subscribe:
            self.client.subscribe(topic, qos=1)
        time.sleep(0.5)                       # let the subscriptions settle before anyone publishes

    def stop(self):
        self.client.disconnect()
        self.client.loop_stop()

    def publish(self, topic: str, proto: str, payload: dict):
        info = self.client.publish(topic, encode(proto, payload), qos=1)
        info.wait_for_publish(timeout=10)

    def clear(self):
        with self._lock:
            self.received.clear()

    def wait_for(self, topic: str, proto: str, predicate=None, timeout: float = 30.0):
        """The newest message on ``topic`` (decoded as ``proto``) satisfying ``predicate``, or None after ``timeout``."""
        deadline = time.time() + timeout
        seen = 0
        while time.time() < deadline:
            with self._lock:
                items = list(self.received)
            for received_topic, payload, _ in reversed(items[seen:] if False else items):
                if received_topic != topic:
                    continue
                try:
                    message = decode(proto, payload)
                except Exception:
                    continue
                if predicate is None or predicate(message):
                    return message
            time.sleep(0.2)
        return None

    def messages_on(self, topic: str):
        with self._lock:
            return [p for t, p, _ in self.received if t == topic]

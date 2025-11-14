# udp_receiver.py
import socket
import json
import time

LISTEN_IP = "0.0.0.0"   # listen on all interfaces
LISTEN_PORT = 5005

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((LISTEN_IP, LISTEN_PORT))
print(f"Listening on UDP {LISTEN_IP}:{LISTEN_PORT}")

last_seen = {}

try:
    while True:
        data, addr = sock.recvfrom(1024)  # buffer size
        ts_recv = time.time()
        try:
            txt = data.decode('utf-8')
            obj = json.loads(txt)
            device = obj.get('device', 'unknown')
            ts_device = obj.get('ts', None)
            print(f"[{time.strftime('%H:%M:%S', time.localtime(ts_recv))}] From {device} @ {addr[0]}:{addr[1]}")
            print("  payload:", json.dumps(obj, indent=2))
            last_seen[device] = ts_recv
        except Exception as e:
            print("Received non-JSON or decode error:", e)
            print("Raw:", data)
except KeyboardInterrupt:
    print("Stopped.")

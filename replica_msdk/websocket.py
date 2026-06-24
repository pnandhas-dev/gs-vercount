import json
import socket
import ssl
import base64
import os
import struct
import requests
from urllib.parse import urlparse

class SimpleWebSocket:
    """A minimal, pure-Python WebSocket client with no external dependencies."""
    def __init__(self, url, verify_ssl=True, headers=None):
        self.url = url
        self.verify_ssl = verify_ssl
        self.headers = headers or {}
        self.sock = None
        
    def connect(self):
        parsed = urlparse(self.url)
        host = parsed.hostname
        port = parsed.port
        if not port:
            port = 443 if parsed.scheme == 'wss' else 80
            
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)  # Add timeout for connection
        
        if parsed.scheme == 'wss':
            context = ssl.create_default_context()
            if not self.verify_ssl:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            self.sock = context.wrap_socket(sock, server_hostname=host)
        else:
            self.sock = sock
            
        self.sock.connect((host, port))
        
        # Handshake
        key = base64.b64encode(os.urandom(16)).decode('utf-8')
        path = parsed.path
        if parsed.query:
            path += '?' + parsed.query
        if not path:
            path = '/'
            
        req = [
            f"GET {path} HTTP/1.1",
            f"Host: {host}:{port}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {key}",
            "Sec-WebSocket-Version: 13",
        ]
        for k, v in self.headers.items():
            req.append(f"{k}: {v}")
        req.append("\r\n")
        
        self.sock.sendall(("\r\n".join(req)).encode('utf-8'))
        
        # Read response
        response = b""
        while b"\r\n\r\n" not in response:
            response += self.sock.recv(1024)
            
        if b"101 Switching Protocols" not in response:
            raise Exception(f"WebSocket handshake failed:\\n{response.decode('utf-8', errors='ignore')}")
            
        # Clear timeout for listening
        self.sock.settimeout(None)

    def recv(self):
        """Read a single WebSocket frame."""
        header = self.sock.recv(2)
        if not header:
            return None
            
        b1, b2 = header
        fin = b1 & 0x80
        opcode = b1 & 0x0f
        mask = b2 & 0x80
        payload_len = b2 & 0x7f
        
        if payload_len == 126:
            payload_len = struct.unpack(">H", self.sock.recv(2))[0]
        elif payload_len == 127:
            payload_len = struct.unpack(">Q", self.sock.recv(8))[0]
            
        if mask:
            mask_key = self.sock.recv(4)
            
        data = b""
        while len(data) < payload_len:
            chunk = self.sock.recv(payload_len - len(data))
            if not chunk:
                return None
            data += chunk
            
        if mask:
            data = bytes(b ^ mask_key[i % 4] for i, b in enumerate(data))
            
        if opcode == 8: # Close frame
            return None
        elif opcode == 1: # Text frame
            return data.decode('utf-8')
        return data

    def close(self):
        if self.sock:
            self.sock.close()


class GlueSyncWebSocketClient:
    def __init__(self, base_url: str, token: str, verify_ssl: bool = False):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.verify_ssl = verify_ssl
        self.ws = None
        
        # Determine WebSocket URL from HTTP URL
        parsed = urlparse(self.base_url)
        ws_scheme = 'wss' if parsed.scheme == 'https' else 'ws'
        self.ws_url = f"{ws_scheme}://{parsed.netloc}/ui"

    def subscribe(self, pipeline_id: str, entities: list):
        """Subscribe to the specified entities using REST PUT."""
        url = f"{self.base_url}/ui/entities-metrics-subscription"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        session = requests.Session()
        session.verify = self.verify_ssl
        
        if not self.verify_ssl:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        payload = {
            "pipelineId": pipeline_id,
            "entities": entities
        }
        
        resp = session.put(url, json=payload, headers=headers)
        if resp.status_code in (200, 202, 204):
            return True
            
        raise Exception(f"Failed to subscribe to entities. Last error: [{resp.status_code}] {resp.text}")

    def connect(self, on_message_callback):
        """Connect to the WebSocket and listen for events."""
        headers = {
            "Authorization": f"Bearer {self.token}"
        }
        
        self.ws = SimpleWebSocket(self.ws_url, verify_ssl=self.verify_ssl, headers=headers)
        self.ws.connect()
        
        try:
            while True:
                msg = self.ws.recv()
                if msg is None:
                    break
                
                try:
                    # Parse as JSON if possible, decoding bytes first if needed
                    msg_str = msg.decode('utf-8') if isinstance(msg, bytes) else msg
                    data = json.loads(msg_str)
                    on_message_callback(data)
                except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
                    on_message_callback(msg)
                    
        finally:
            self.ws.close()


def parse_protobuf(data):
    """A lightweight, zero-dependency protobuf parser to recursively extract values"""
    idx = 0
    extracted = {}
    
    def decode_varint():
        nonlocal idx
        result = 0
        shift = 0
        while idx < len(data):
            b = data[idx]
            idx += 1
            result |= (b & 0x7f) << shift
            if not (b & 0x80):
                break
            shift += 7
        return result
        
    while idx < len(data):
        try:
            tag = decode_varint()
            if tag == 0:
                break
            field_num = tag >> 3
            wire_type = tag & 7
            
            if wire_type == 0:  # Varint
                val = decode_varint()
                key = f"Field_{field_num}_varint"
                if key in extracted:
                    if not isinstance(extracted[key], list):
                        extracted[key] = [extracted[key]]
                    extracted[key].append(val)
                else:
                    extracted[key] = val
            elif wire_type == 1:  # 64-bit
                idx += 8
            elif wire_type == 2:  # Length-delimited
                length = decode_varint()
                val_bytes = data[idx:idx+length]
                idx += length
                try:
                    decoded_str = val_bytes.decode('utf-8')
                    import string
                    if any(c < ' ' and c not in ('\\n', '\\r', '\\t') for c in decoded_str):
                        raise UnicodeDecodeError('utf-8', b'', 0, 1, 'Control characters found')
                    extracted[f"Field_{field_num}_string"] = decoded_str
                except UnicodeDecodeError:
                    nested = parse_protobuf(val_bytes)
                    if len(nested) > 0 and "UNKNOWN_WIRE" not in str(nested):
                        extracted[f"Field_{field_num}_message"] = nested
                    else:
                        extracted[f"Field_{field_num}_bytes"] = val_bytes.hex()
            elif wire_type == 5:  # 32-bit
                idx += 4
            else:
                extracted[f"Field_{field_num}_UNKNOWN_WIRE_{wire_type}"] = True
                break
        except Exception:
            break
            
    return extracted

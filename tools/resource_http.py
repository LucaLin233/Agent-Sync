"""Read-only, bounded agentSkills.readResource transport (stdlib only).

No workspace header is sent (key-bound personal scope). No settings files, proxy
discovery, redirect handling, retry or CLI fallback.
"""
import base64
import hashlib
import http.client
import json
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlsplit

# 受批准 origin 只留 sha256 pin（私有域名不进仓库）；缺失或不符即 `configuration`。
APPROVED_ORIGIN_SHA256 = 'b5da30b40617adaffac73c305fadf7268769014bc938d969e22958e1b0e02a0b'
ORIGIN_ENV = 'LOBEHUB_SERVER'
REQUEST_TIMEOUT = 30.0  # I/O wait/cooperative checks, NOT a request wall-clock deadline.
MAX_RESPONSE = 8 * 1024 * 1024  # HTTP envelope only, NOT total process memory.
ENDPOINT = '/trpc/lambda/agentSkills.readResource'


class ResourceError(ValueError):
    """Only fixed classifications; never retain upstream exception text."""


def valid_path(path):
    return (isinstance(path, str) and bool(path) and '\\' not in path
            and not any(ord(c) < 32 or ord(c) == 127 for c in path)
            and all(p not in ('', '.', '..') for p in path.split('/')))


def decode_resource(payload, path, size, digest):
    if not valid_path(path):
        raise ResourceError('path')
    if (not isinstance(payload, dict) or payload.get('path') != path
            or type(payload.get('size')) is not int or payload['size'] != size
            or payload.get('fileHash') != digest
            or not isinstance(payload.get('fileType'), str)
            or not payload['fileType']
            or not isinstance(payload.get('content'), str)):
        raise ResourceError('structure')
    try:
        if payload.get('encoding') == 'utf8':
            data = payload['content'].encode('utf-8', errors='strict')
        elif payload.get('encoding') == 'base64':
            data = base64.b64decode(payload['content'], validate=True)
            if base64.b64encode(data).decode('ascii') != payload['content']:
                raise ResourceError('encoding')
        else:
            raise ResourceError('encoding')
    except (ValueError, UnicodeError):
        raise ResourceError('encoding') from None
    if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
        raise ResourceError('integrity')
    return data


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ResourceError('structure')
        result[key] = value
    return result


def connection_context():
    """Freeze (origin, key) before any CLI/HTTP request; fixed classification on failure.

    Origin must match the sha256 pin. Scope is personal only (no `X-Workspace-Id` is sent), so
    an explicit `LOBEHUB_WORKSPACE_ID` is rejected rather than ignored; the deploy tool runs the
    CLI with an empty HOME/XDG so its persisted workspace cannot differ either.
    """
    origin = os.environ.get(ORIGIN_ENV)
    if not origin:
        raise ResourceError('configuration')
    if hashlib.sha256(origin.encode('utf-8')).hexdigest() != APPROVED_ORIGIN_SHA256:
        raise ResourceError('configuration')
    if os.environ.get('LOBEHUB_WORKSPACE_ID'):
        raise ResourceError('configuration')
    key = os.environ.get('LOBEHUB_CLI_API_KEY')
    if not key or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise ResourceError('authentication')
    return origin, key


class ResourceClient:
    def __init__(self, deadline, context):
        origin, key = context
        parsed = urlsplit(origin)
        self.host = parsed.hostname
        self.headers = {'X-API-Key': key, 'User-Agent': 'curl/8.7.1',
                        'Accept': 'application/json'}
        self.deadline = deadline
        self.local = threading.local()
        self.connections = []
        self.lock = threading.Lock()

    def remaining(self, request_deadline):
        remaining = min(self.deadline, request_deadline) - time.monotonic()
        if remaining <= 0:
            raise ResourceError('budget')
        return remaining

    def read(self, sid, item):
        path, size, digest = item
        if not valid_path(path) or not isinstance(sid, str) or not sid:
            raise ResourceError('path')
        request_deadline = time.monotonic() + REQUEST_TIMEOUT
        response = None
        try:
            conn = getattr(self.local, 'connection', None)
            if conn is None:
                conn = http.client.HTTPSConnection(
                    self.host, timeout=self.remaining(request_deadline))
                self.local.connection = conn
                with self.lock:
                    self.connections.append(conn)
            conn.timeout = self.remaining(request_deadline)
            if conn.sock is not None:
                conn.sock.settimeout(conn.timeout)
            query = quote(json.dumps({'json': {'id': sid, 'path': path}},
                                     ensure_ascii=True, separators=(',', ':')), safe='')
            conn.request('GET', ENDPOINT + '?input=' + query, headers=self.headers)
            response = conn.getresponse()
            if response.status in (401, 403):
                raise ResourceError('authentication')
            if response.status == 429:
                raise ResourceError('rate-limit')
            if response.status != 200:
                raise ResourceError('http-status')  # Includes ALL redirects.
            declared = response.getheader('Content-Length')
            if declared is not None and (not declared.isdigit() or int(declared) > MAX_RESPONSE):
                raise ResourceError('response-limit')
            if response.getheader('Content-Encoding') not in (None, 'identity'):
                raise ResourceError('structure')
            chunks, count = [], 0
            while True:
                if conn.sock is not None:
                    conn.sock.settimeout(self.remaining(request_deadline))
                else:
                    self.remaining(request_deadline)
                chunk = response.read1(min(65536, MAX_RESPONSE + 1 - count))
                if not chunk:
                    break
                chunks.append(chunk)
                count += len(chunk)
                if count > MAX_RESPONSE:
                    raise ResourceError('response-limit')
            if declared is not None and count != int(declared):
                raise ResourceError('truncated')
            self.remaining(request_deadline)
            envelope = json.loads(b''.join(chunks).decode('utf-8'), object_pairs_hook=_object)
            if (not isinstance(envelope, dict) or set(envelope) != {'result'}
                    or not isinstance(envelope['result'], dict)):
                raise ResourceError('structure')
            data = envelope['result']['data']
            if not isinstance(data, dict) or set(data) != {'json'}:
                raise ResourceError('structure')
            return decode_resource(data['json'], path, size, digest)
        except ResourceError:
            raise
        except (TimeoutError, socket.timeout):
            raise ResourceError('timeout') from None
        except (OSError, http.client.HTTPException):
            raise ResourceError('transport') from None
        except (ValueError, KeyError, TypeError, UnicodeError, RecursionError):
            raise ResourceError('structure') from None
        finally:
            if response is not None:
                response.close()

    def close(self):
        for conn in self.connections:
            conn.close()
        self.headers.clear()


def collect(client, sid, planned, workers):
    """One to eight lanes; no queued futures, one reusable connection per lane.

    Allocation/error publication share a lock. After first failure is observed,
    no next item can be allocated; at most workers-1 requests finish in flight.
    """
    lock = threading.Lock()
    pending = iter(planned)
    actual, errors = {}, []

    def lane():
        while True:
            with lock:
                if errors:
                    return
                item = next(pending, None)
                if item is None:
                    return
            try:
                data = client.read(sid, item)
            except Exception as exc:
                with lock:
                    if not errors:
                        errors.append(str(exc) if isinstance(exc, ResourceError) else 'internal')
                return
            with lock:
                actual[item[0]] = data

    try:
        with ThreadPoolExecutor(max_workers=min(8, max(1, workers), len(planned))) as pool:
            futures = [pool.submit(lane) for _ in range(min(8, max(1, workers), len(planned)))]
            for future in futures:
                future.result()
        if errors:
            raise ResourceError(errors[0])
        return actual
    finally:
        client.close()

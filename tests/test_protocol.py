"""Adversarial public-API tests. Run with an already-built tests/test_lib.fin binary.

Runs on every platform zhttp supports: the peer is a loopback socket and the
driver under test dials it, so nothing depends on a descriptor surviving
exec -- which is a POSIX-only mechanism. No fixed ports, external services, or sleeps.
"""
import os
import socket
import struct
import subprocess
import sys
import tempfile

BINARY = os.path.abspath(sys.argv[1])
MAX_BODY = 16 * 1024 * 1024
MAX_HEADERS = 64 * 1024
COUNT = 0


def launch(mode, port=None, url=None):
    env = dict(os.environ, ZHTTP_TEST_MODE=mode)
    if port is not None:
        env["ZHTTP_TEST_PORT"] = str(port)
    if url is not None:
        env["ZHTTP_TEST_URL"] = url
    return subprocess.Popen(
        [BINARY], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def peer_for(ours):
    """The peer end of a connected loopback pair.

    The driver dials the listener itself, so the peer is a plain accepted
    socket on the loopback address rather than a descriptor handed over
    across exec.
    """
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(8)
    return listener


def check(process, expected, label):
    global COUNT
    try:
        out, err = process.communicate(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise AssertionError(f"{label}: blocked after complete framed message")
    assert process.returncode == 0, (label, process.returncode, err.decode())
    assert out.decode().strip() == expected, (label, out.decode(), expected)
    COUNT += 1
    print(f"PASS {label}")


def send(peer, payload):
    try:
        if isinstance(payload, list):
            for part in payload:
                peer.sendall(part)
        else:
            peer.sendall(payload)
    except (BrokenPipeError, ConnectionResetError):
        pass  # A parser may reject a prefix before we finish sending.


def request(label, payload, expected="REJECT", eof=False, upgrade=False):
    with peer_for(None) as listener:
        port = listener.getsockname()[1]
        p = launch("upgrade" if upgrade else "request", port=port)
        peer = None
        try:
            peer, _ = listener.accept()
            peer.settimeout(8)
            send(peer, payload)
            if eof:
                try:
                    peer.shutdown(socket.SHUT_WR)
                except OSError:
                    pass
            check(p, expected, label)
        finally:
            if peer is not None:
                peer.close()
            if p.poll() is None:
                p.kill()
                p.communicate()


def response(label, payload, expected="REJECT", eof=False):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(8)
        p = launch("client", url=f"http://127.0.0.1:{listener.getsockname()[1]}/")
        try:
            peer, _ = listener.accept()
            with peer:
                peer.settimeout(8)
                incoming = b""
                while b"\r\n\r\n" not in incoming:
                    incoming += peer.recv(4096)
                send(peer, payload)
                if eof:
                    try:
                        peer.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass
                # Keep peer open for framed messages: completing must not wait for EOF.
                check(p, expected, label)
        finally:
            if p.poll() is None:
                p.kill()
                p.communicate()


REQ = b"POST / HTTP/1.1\r\n"
RES = b"HTTP/1.1 200 OK\r\n"
CHUNK = RES + b"Transfer-Encoding: chunked\r\n\r\n"
request("empty header block", REQ + b"\r\n", "ACCEPT 0")
request("OWS content length", REQ + b"Content-Length:\t 3 \t\r\n\r\nabc", "ACCEPT 3")
for name, fields in [
    ("duplicate host", b"Host: one\r\nhost: two\r\n"),
    ("duplicate WS key", b"Sec-WebSocket-Key: one\r\nSec-WebSocket-Key: two\r\n"),
    ("duplicate WS version", b"Sec-WebSocket-Version: 13\r\nSec-WebSocket-Version: 13\r\n"),
    ("duplicate WS accept", b"Sec-WebSocket-Accept: one\r\nSec-WebSocket-Accept: two\r\n"),
    ("duplicate identical CL", b"Content-Length: 0\r\nContent-Length: 0\r\n"),
    ("conflicting CL", b"Content-Length: 4\r\ncontent-length: 0\r\n"),
    ("TE with CL", b"Transfer-Encoding: chunked\r\nContent-Length: 0\r\n"),
    ("duplicate TE", b"Transfer-Encoding: chunked\r\nTransfer-Encoding: chunked\r\n"),
    ("unsupported TE", b"Transfer-Encoding: gzip\r\n"),
    ("comma lengths", b"Content-Length: 0, 0\r\n"),
    ("negative length", b"Content-Length: -1\r\n"),
    ("plus length", b"Content-Length: +1\r\n"),
    ("empty length", b"Content-Length:\r\n"),
    ("overflow length", b"Content-Length: 999999999999999999999999\r\n"),
    ("oversized length", b"Content-Length: 16777217\r\n"),
    ("space before colon", b"Content-Length : 0\r\n"),
    ("empty name", b": x\r\n"),
    ("invalid name", b"Bad(Name): x\r\n"),
    ("missing colon", b"not a header\r\n"),
    ("obs-fold", b"X: one\r\n two\r\n"),
    ("bare LF", b"X: a\nb\r\n"),
    ("bare CR", b"X: a\rb\r\n"),
    ("NUL value", b"X: a\x00b\r\n"),
    ("control value", b"X: a\x01b\r\n"),
]:
    request("request " + name, REQ + fields + b"\r\n")
    response("response " + name, RES + fields + b"\r\n", eof=True)
request("request chunked unsupported", REQ + b"Transfer-Encoding: chunked\r\n\r\n")
request("request invalid version", b"GET / HTTP/9.9\r\n\r\n")
request("request invalid method", b"G(ET / HTTP/1.1\r\n\r\n")
request("request extra whitespace", b"GET  / HTTP/1.1\r\n\r\n")
request("request truncated body", REQ + b"Content-Length: 3\r\n\r\nab", eof=True)
request("request upgrade tail", b"GET / HTTP/1.1\r\nUpgrade: websocket\r\n\r\nTAIL", "ACCEPT 0\nTAIL_OK", upgrade=True)
request("request body tail", REQ + b"Content-Length: 3\r\n\r\nabcTAIL", "ACCEPT 3\nTAIL_OK", upgrade=True)
request("request fragmented delimiter", [REQ + b"X: y\r", b"\n\r", b"\nTAIL"], "ACCEPT 0\nTAIL_OK", upgrade=True)
for prefix, runner in [(REQ, request), (RES, response)]:
    kind = "request" if runner is request else "response"
    expected = "ACCEPT 0" if runner is request else "ACCEPT 200 0"
    base = prefix + b"Content-Length: 0\r\nX: "
    for delta in (0, 1):
        payload = base + b"a" * (MAX_HEADERS + delta - len(base) - 4) + b"\r\n\r\n"
        runner(f"{kind} header limit +{delta}", payload, expected if delta == 0 else "REJECT")
    for fields in (256, 257):
        payload = prefix + b"Content-Length: 0\r\n" + b"X: a\r\n" * (fields - 1) + b"\r\n"
        runner(f"{kind} field limit {fields}", payload, expected if fields == 256 else "REJECT")
    for n in (65536, MAX_BODY):
        payload = prefix + f"Content-Length: {n}\r\n\r\n".encode() + b"a" * n
        accepted = f"ACCEPT {n}" if runner is request else f"ACCEPT 200 {n}"
        runner(f"{kind} body {n}", payload, accepted)
response("CL keep-open", RES + b"Content-Length: 2\r\n\r\nok", "ACCEPT 200 2")
response("CL ignores trailing bytes", RES + b"Content-Length: 2\r\n\r\nokTAIL", "ACCEPT 200 2")
response("close delimited", RES + b"\r\nhello", "ACCEPT 200 5", eof=True)
response("close body exact limit", RES + b"\r\n" + b"a" * MAX_BODY, f"ACCEPT 200 {MAX_BODY}", eof=True)
response("close body over limit", RES + b"\r\n" + b"a" * (MAX_BODY + 1), eof=True)
response("truncated CL", RES + b"Content-Length: 3\r\n\r\nab", eof=True)
response("headerless 204", b"HTTP/1.1 204 No Content\r\n\r\n", "ACCEPT 204 0")
response("304 no body despite CL", b"HTTP/1.1 304 Not Modified\r\nContent-Length: 22\r\n\r\n", "ACCEPT 304 0")
response("informational then final", b"HTTP/1.1 100 Continue\r\n\r\n" + RES + b"Content-Length: 0\r\n\r\n", "ACCEPT 200 0")
response("informational limit", b"HTTP/1.1 100 Continue\r\n\r\n" * 17)
response("invalid status protocol", b"BOGUS/1.1 200 OK\r\n\r\n", eof=True)
response("invalid short status", b"HTTP/1.1 20 OK\r\n\r\n", eof=True)
response("chunked keep-open", CHUNK + b"2\r\nok\r\n0\r\n\r\n", "ACCEPT 200 2")
response("chunk extensions and trailers", CHUNK + b"2;foo=\"a\\\"b\";flag\r\nok\r\n0\r\nX-Sum: yes\r\n\r\n", "ACCEPT 200 2")
response("chunk body exact limit", CHUNK + b"1000000\r\n" + b"a" * MAX_BODY + b"\r\n0\r\n\r\n", f"ACCEPT 200 {MAX_BODY}")
response("chunk line exact limit", CHUNK + b"1;x=" + b"a" * (8192 - 6) + b"\r\na\r\n0\r\n\r\n", "ACCEPT 200 1")
response("trailer exact field limit", CHUNK + b"0\r\n" + b"X: a\r\n" * 256 + b"\r\n", "ACCEPT 200 0")
for delta in (0, 1):
    metadata = b"0\r\n" + (b"X: " + b"a" * 8187 + b"\r\n") * 7
    metadata += b"X: " + b"a" * (8182 + delta) + b"\r\n\r\n"
    assert len(metadata) == MAX_HEADERS + delta
    response(f"chunk metadata limit +{delta}", CHUNK + metadata, "ACCEPT 200 0" if delta == 0 else "REJECT", eof=True)
for name, body in [
    ("bad data delimiter", b"1\r\nAXX0\r\n\r\n"),
    ("missing terminal CRLF", b"1\r\nA\r\n0\r\n"),
    ("missing zero chunk", b"1\r\nA\r\n"),
    ("truncated data", b"3\r\na"),
    ("invalid hex", b"G\r\n"),
    ("empty hex", b"\r\n"),
    ("space hex", b" 1\r\nA\r\n0\r\n\r\n"),
    ("overflow hex", b"ffffffffffffffff\r\n"),
    ("oversized chunk", b"1000001\r\n"),
    ("aggregate overflow", b"1000000\r\n" + b"a" * MAX_BODY + b"\r\n1\r\n"),
    ("empty extension", b"1;\r\nA\r\n0\r\n\r\n"),
    ("unterminated quote", b"1;x=\"a\r\nA\r\n0\r\n\r\n"),
    ("malformed trailer", b"0\r\ninvalid\r\n\r\n"),
    ("forbidden trailer CL", b"0\r\nContent-Length: 0\r\n\r\n"),
    ("forbidden trailer TE", b"0\r\nTransfer-Encoding: chunked\r\n\r\n"),
    ("unterminated trailer", b"0\r\nX: a\r\n"),
    ("trailer count", b"0\r\n" + b"X: a\r\n" * 257 + b"\r\n"),
    ("line size limit", b"1;x=" + b"a" * 8192 + b"\r\n"),
    ("metadata limit", b"1\r\na\r\n" * 14000 + b"0\r\n\r\n"),
]:
    response("chunk " + name, CHUNK + body, eof=True)
with peer_for(None) as listener:
    port = listener.getsockname()[1]
    p = launch("response", port=port)
    peer = None
    try:
        peer, _ = listener.accept()
        peer.settimeout(8)
        wire = b""
        while True:
            part = peer.recv(4096)
            if not part:
                break
            wire += part
        assert b"Content-Length:" not in wire and wire.endswith(b"\r\n\r\n"), wire
        assert b"must not be sent" not in wire, wire
        check(p, "SENT", "204 writer emits no body or forbidden length")
    finally:
        if peer is not None:
            peer.close()
        if p.poll() is None:
            p.kill()
            p.communicate()
# The peer closes before the driver writes, so the write must fail rather than
# raise a signal. Linux suppresses the signal with MSG_NOSIGNAL, macOS with
# SO_NOSIGPIPE on the socket, and Windows reports the error.
with peer_for(None) as listener:
    port = listener.getsockname()[1]
    p = launch("write", port=port)
    peer = None
    try:
        peer, _ = listener.accept()
        peer.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        peer.close()
        peer = None
        check(p, "SEND_FAILED", "closed peer does not deliver SIGPIPE")
    finally:
        if peer is not None:
            peer.close()
        if p.poll() is None:
            p.kill()
            p.communicate()
# A peer that closes gracefully leaves the connection half-open: the driver
# reads end of stream, and the write that follows is legal and must succeed.
# This is a different case from the reset above, which must fail.
with peer_for(None) as listener:
    port = listener.getsockname()[1]
    p = launch("write", port=port)
    peer = None
    try:
        peer, _ = listener.accept()
        peer.shutdown(socket.SHUT_WR)
        check(p, "SENT", "graceful peer close still allows a write")
    finally:
        if peer is not None:
            peer.close()
        if p.poll() is None:
            p.kill()
            p.communicate()
# Fault injection is isolated to this subprocess; no process-global handlers.
# Each syscall gets EINTR once, then short send/recv counts exercise retry loops.
SHIM = r'''
#define _GNU_SOURCE
#include <sys/socket.h>
#include <dlfcn.h>
#include <errno.h>
ssize_t send(int fd, const void *p, size_t n, int flags) {
    static int first = 1;
    if (first) { first = 0; errno = EINTR; return -1; }
    ssize_t (*real)(int,const void*,size_t,int) = dlsym(RTLD_NEXT, "send");
    return real(fd, p, n > 7 ? 7 : n, flags);
}
ssize_t recv(int fd, void *p, size_t n, int flags) {
    static int first = 1;
    if (first) { first = 0; errno = EINTR; return -1; }
    ssize_t (*real)(int,void*,size_t,int) = dlsym(RTLD_NEXT, "recv");
    return real(fd, p, n > 5 ? 5 : n, flags);
}
int accept(int fd, struct sockaddr *a, socklen_t *n) {
    static int first = 1;
    if (first) { first = 0; errno = EINTR; return -1; }
    int (*real)(int,struct sockaddr*,socklen_t*) = dlsym(RTLD_NEXT, "accept");
    return real(fd, a, n);
}
'''
with tempfile.TemporaryDirectory(prefix="zhttp-syscalls-") as temp:
    source = os.path.join(temp, "syscalls.c")
    shared = os.path.join(temp, "syscalls.so")
    with open(source, "w", encoding="utf-8") as f:
        f.write(SHIM)
    subprocess.run([os.environ.get("CC", "cc"), "-shared", "-fPIC", source, "-ldl", "-o", shared], check=True)
    env = dict(os.environ, LD_PRELOAD=shared)
    env.pop("ZHTTP_TEST_MODE", None)
    injected = subprocess.run([BINARY], env=env, capture_output=True, timeout=15)
    assert injected.returncode == 0, (injected.stdout, injected.stderr)
    assert b"zhttp: all tests passed" in injected.stdout
    COUNT += 1
    print("PASS EINTR and short send/recv during baseline loopback")
print(f"zhttp protocol: {COUNT} cases passed")

# zhttp

HTTP/1.1 client and server for [Fin](https://github.com/M1778/Fin), on raw blocking
TCP over IPv4 (the same design as `networking::std`).

> **Verified against the released `finc 1.0.0` (contract 3), locally on Linux
> x86_64.** The Fin test suite and the adversarial Python protocol suite build and
> run, at `-O0` and `-O2`, with the same binary CI installs from `FINC_VERSION`.
> CI runs the same suites on Linux, macOS and Windows; see
> [Platform support](#platform-support) for the one case that is Linux-only and
> [Limits](#limits) for what this library deliberately does not do.

## What it does

- Parse `http://` URLs with validation (`http_parse_url`).
- A blocking client: `http_get`, `http_post`, and `*_with_timeout` variants.
- Decode response bodies framed by `Content-Length`, `Transfer-Encoding: chunked`,
  or close-of-connection.
- A blocking server: listen, accept, read one request, write a response.
- Case-insensitive header storage, a status-text table, and a raw byte-level
  socket API for protocols built on top of HTTP (e.g. a WebSocket handshake).

## What it does not do

- **No TLS.** `https://` URLs are rejected with an explicit error.
- **No HTTP/2, no router, no middleware, no WebSocket framing.** The raw socket
  API lets another library implement an upgrade; zhttp stops at HTTP.
- **No keep-alive.** The server answers `Connection: close` and the caller closes
  the socket. A second `http_read_request` on the same connection is refused by
  name rather than parsed (see [Server](#server)).
- **No DNS.** IPv4 dotted-quad hosts only, same as `networking::std`.
- **No redirect following.** `http_get` returns 3xx responses to the caller; a
  redirect loop is therefore impossible in this library, because no request is
  ever issued on the caller's behalf.
- **Bodies are byte strings.** Fin strings are NUL-terminated, so an embedded NUL
  in a body truncates it. Use `http_socket_read_exact` for binary payloads.

## Install

Requires the [`finn`](https://github.com/M1778/finn) package manager:

```sh
finn add --yes M1778/zhttp
```

No registry resolves these names yet, so `--yes` is required: without it `finn add` refuses
a source the register has not vouched for rather than installing it unasked. Drop the flag
once a registry entry exists.

Then `import { http_get } from zhttp::fin;`.

Without `finn`, put the repository's `src/` directory on the compiler's include
path (`-I` takes a directory, not a file):

```sh
finc -I path/to/zhttp/src your_program.fin -o your_program
```

## Complete runnable example

Server and client in one program, so it runs with nothing else installed. It
listens on an ephemeral port, answers one request from a worker thread, and
exits. Save as `example.fin` and run it:

```fin
import {
    HttpServer, HttpConn, HttpReadResult, HttpResponse, HttpResult,
    http_listen, http_server_port, http_accept, http_read_request,
    http_write_response, http_response, http_free_response,
    http_free_read_result, http_close, http_server_close,
    http_get, http_free_result
} from zhttp::fin;
import { Thread } from sync::std;
import { len } from strings::std;

struct Shared {
    port <int>,
    status <int>,
    size <int>,
}

fun main() <noret> {
    let srv <&HttpServer> = http_listen(0);              // 0 = ephemeral port
    let shared <&Shared> = new Shared{port: http_server_port(srv), status: 0, size: 0};

    // The server side runs on a worker thread so the client can connect.
    let worker <Thread> = Thread::spawn(fun () <noret> {
        let conn <&HttpConn> = http_accept(srv);
        let rr <HttpReadResult> = http_read_request(conn);
        if (rr.ok) {
            let resp <&HttpResponse> = http_response(200, "hello from zhttp");
            http_write_response(conn, resp);
            http_free_response(resp);
        }
        http_free_read_result(&rr);
        http_close(conn);
        http_server_close(srv);
    });

    let url <string> = format!("http://127.0.0.1:{}/", shared.port);
    let r <HttpResult> = http_get(url);
    shared.status = r.status;
    shared.size = len(r.body);
    http_free_result(&r);
    worker.join();

    printf("status=%d bytes=%d\n", shared.status, shared.size);
    delete shared;
}
```

```output
status=200 bytes=16
```

```sh
finc -I path/to/zhttp/src example.fin -o example && ./example
```

The two programs in `examples/` are a small router-style server (run it, then
`curl http://127.0.0.1:8080/`) and a matching client.

## Public API

### URL parsing

```fin
fun http_parse_url(s: string) <HttpUrlResult>   // { ok, url, err }
fun http_free_url_result(r: &HttpUrlResult) <noret>
```

`HttpUrl` carries `scheme`, `host`, `port` (default 80), `path` (default `/`), and
`query` (empty when absent). Only `http://` is accepted. A host containing a
control character, a space, or DEL is rejected: it is written into the `Host`
header, where those bytes would inject a header.

### Client

```fin
fun http_get(url: string) <HttpResult>
fun http_post(url: string, content_type: string, body: string) <HttpResult>
fun http_get_with_timeout(url: string, timeout_ms: int) <HttpResult>
fun http_post_with_timeout(url: string, content_type: string, body: string, timeout_ms: int) <HttpResult>
fun http_free_result(r: &HttpResult) <noret>
```

`HttpResult` carries `ok`, `status`, `headers`, `body`, and `err`. Connection
failures, malformed URLs, and read failures are recoverable (`ok == false` with a
message in `err`), never aborts.

Every request has an **idle deadline**: 30 s by default, or `timeout_ms` for the
`*_with_timeout` variants. It bounds each blocking read and write, not the whole
request, so a large body that keeps arriving is not aborted. A peer that opens a
connection and then says nothing produces `ok == false` with an error naming the
timeout. `0` disables the deadline.

The client refuses to send a request whose target or `Content-Type` contains a
control character (including CR and LF) or, for the target, a space. Those bytes
would end the request line or a header and inject another. It refuses before
dialling, so nothing reaches the wire.

### Server

```fin
fun http_listen(port: int) <&HttpServer>        // 0 = ephemeral; aborts on bind failure
fun http_server_port(srv: &HttpServer) <int>
fun http_server_close(srv: &HttpServer) <noret>
fun http_accept(srv: &HttpServer) <&HttpConn>
fun http_read_request(conn: &HttpConn) <HttpReadResult>  // { ok, req, err }
fun http_free_read_result(rr: &HttpReadResult) <noret>
fun http_free_request(q: &HttpRequest) <noret>
fun http_write_response(conn: &HttpConn, resp: &HttpResponse) <bool>
fun http_write_raw(conn: &HttpConn, text: string) <bool>
fun http_close(conn: &HttpConn) <noret>
fun http_detach(conn: &HttpConn) <HttpSocket>
```

`http_read_request` rejects malformed input with `ok == false`; close the
connection after a rejection rather than trying to resynchronise.

**One request per connection.** `http_write_response` sends `Connection: close`,
so there is no keep-alive and no pipelining. `http_read_request` enforces this: a
second call on the same `HttpConn` returns
`connection already served one request (no keep-alive; open a new connection)`
instead of parsing leftover bytes as a new request. If you need concurrency,
accept more connections; the API is blocking and single-reader per connection.

Duplicate `Content-Length` or `Transfer-Encoding`, duplicate `Host`/WebSocket
handshake singletons, `Transfer-Encoding` with `Content-Length`, malformed field
syntax, obs-fold, bare CR or LF, NUL and other control bytes in a field value, and
all request transfer codings are rejected. Chunked **responses** are decoded;
chunked requests are refused.

Header reads consume exactly through CRLFCRLF and a length-delimited body consumes
exactly its declared length, so bytes belonging to an upgraded protocol remain in
the socket. `http_detach` frees the connection wrapper and transfers the fd: after
detaching, do not use the wrapper, and close the returned handle yourself.

`http_listen` and `http_accept` abort (`blame`) on permanent failures; a failed
bind is a configuration error, not a value to retry. Interrupted accept/send/recv
calls are retried.

### Deadlines and raw sockets

```fin
fun http_socket_timeout(fd: HttpSocket, ms: int) <bool>
fun http_socket_invalid() <HttpSocket>
fun http_socket_close(fd: HttpSocket) <bool>
fun http_socket_shutdown(fd: HttpSocket) <bool>
fun http_socket_dial(host: string, port: int) <HttpSocket>
fun http_socket_failed() <bool>
fun http_socket_interrupted() <bool>
fun http_socket_read(fd: HttpSocket, buf: [char], want: int) <int>
fun http_socket_read_at(fd: HttpSocket, buf: [char], offset: int, want: int) <int>
fun http_socket_read_exact(fd: HttpSocket, want: int) <SocketBytes>  // { ok, data, len }
fun http_socket_peek(fd: HttpSocket, buf: [char], want: int) <int>
fun http_socket_peek_at(fd: HttpSocket, buf: [char], offset: int, want: int) <int>
fun http_socket_write(fd: HttpSocket, buf: [char], len: int) <bool>
fun http_socket_write_at(fd: HttpSocket, buf: [char], offset: int, len: int) <bool>
```

`http_socket_timeout` applies a read and a write deadline to any socket handle, for
protocols layered on this transport. `http_socket_read_exact` reads exactly `want`
bytes into a fresh buffer, assembling fragmented reads correctly; free `data` with
`delete`.

These exist so a consumer never redeclares `send`/`recv`: two declarations of the
same linker symbol with different signatures is how the WebSocket library and this
one used to disagree about the ABI.

### Responses, headers, status

```fin
fun http_response(status: int, body: string) <&HttpResponse>
fun http_response_with_type(status: int, content_type: string, body: string) <&HttpResponse>
fun http_free_response(r: &HttpResponse) <noret>

fun http_status_text(code: int) <string>   // static string; do NOT free
fun http_new_headers() <&HttpHeaders>
fun http_free_headers(hdrs: &HttpHeaders) <noret>
fun http_header_has(hdrs: &HttpHeaders, name: string) <bool>
fun http_header_get(hdrs: &HttpHeaders, name: string) <string>  // "" if absent; borrowed
fun http_header_set(hdrs: &HttpHeaders, name: string, value: string) <noret>  // copies both
fun http_header_count(hdrs: &HttpHeaders) <int>
fun http_header_name(hdrs: &HttpHeaders, i: int) <string>   // borrowed
fun http_header_value(hdrs: &HttpHeaders, i: int) <string>  // borrowed
```

`http_response` sets `Content-Type: text/plain; charset=utf-8` and a correct
`Content-Length`, except for 1xx/204 where a length is forbidden. The writer omits
bodies for 1xx, 204 and 304. Header names are matched case-insensitively per
RFC 9110. `http_header_get` returns `""` for a missing header; use
`http_header_has` to tell missing from empty.

## Limits

### Enforced limits

These are not documented aspirations: each has a case in `tests/test_protocol.py`
that passes exactly at the limit and fails one byte over it.

- Request and response header blocks: **64 KiB**, including the start line and the
  final CRLFCRLF, with at most **256 fields**.
- Request and response bodies: **16 MiB**, including aggregate decoded chunk data.
- Chunk-size and trailer lines: **8 KiB** each; aggregate chunk metadata (size
  lines, data delimiters, trailers) **64 KiB**, at most **256 trailer fields**.
  Trailers are validated and discarded; framing and routing fields are forbidden.
- At most **16 informational (1xx) responses** are skipped before a final one.
- Port parsing is bounded to 1–65535.

A peer that sends more is rejected with `ok == false`; nothing is truncated
silently.

### Not implemented

- TLS, HTTP/2, routing, middleware, WebSocket framing (`http_write_raw` and
  `http_detach` let another library implement an upgrade).
- DNS resolution: dotted-quad IPv4 only.
- Keep-alive and pipelining.
- Redirect following.
- Chunked *request* bodies; chunked responses are decoded.
- Deadlines on `connect`: the same `SO_RCVTIMEO`/`SO_SNDTIMEO` values are set on
  the socket before `connect`. Linux applies `SO_SNDTIMEO` to a blocking connect;
  Winsock documents that it does not, so on Windows a dial to a black-holed
  address waits for the OS default. The macOS behaviour was not exercised here.

## Platform support

| | Linux | macOS | Windows |
| --- | --- | --- | --- |
| Build + run test suite in CI | yes | yes | yes |
| Adversarial protocol suite in CI | yes | yes | yes |
| `MSG_NOSIGNAL` / `SO_NOSIGPIPE` SIGPIPE suppression | Linux `MSG_NOSIGNAL` | `SO_NOSIGPIPE` | not applicable; `send` reports the error |
| EINTR/short-read fault injection | yes (`LD_PRELOAD`) | reported SKIP | reported SKIP |
| TLS | no | no | no |

The socket ABI is selected from the compiler's native target at compile time. On
Windows that means `SOCKET` (a pointer-width handle), `send`/`recv` taking an
`int` length, `WSAGetLastError` as the error source, and `WSAStartup` before any
socket call — each socket this library creates balances one startup with exactly
one cleanup, including through `http_detach`. On POSIX the handle is an `int`, the
lengths are `size_t`, and the error source is `errno`.

**The fault-injection case is Linux-only and says so in the log** (`SKIP ... the
LD_PRELOAD shim is Linux-only`). It is never silently absent. All other protocol
cases run on all three platforms.

## Development

```sh
finc -I src tests/test_lib.fin -o test_zhttp && ./test_zhttp
python3 -I tests/test_protocol.py ./test_zhttp
```

The Python suite is a real adversarial peer: it opens loopback sockets, sends
malformed and truncated framing, checks exact limits, and asserts the driver's
exit status and output. It needs no external service and no fixed port. Run the
suite at `-O0` and `-O2`; CI does both.

`finn test` runs the same Fin test program. `finn build` fails by design: this is a
library and has no `main`.

Headers are applied and checked with:

```sh
python3 scripts/fin_header.py --repo zhttp --license MIT src tests examples zhttp.fin scripts .github/scripts
python3 scripts/fin_header.py --repo zhttp --license MIT --check src tests examples zhttp.fin scripts .github/scripts
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

MIT — see [LICENSE](LICENSE).

# zhttp

HTTP/1.1 client and server for [Fin](https://github.com/M1778/Fin). Built on raw
blocking TCP over IPv4 (the same design as `networking::std`).

> **Native verification:** O0/O2 client/server and protocol suites passed on
> Linux, macOS and Windows, each on x86_64 and ARM64, in
> [ecosystem run 40034937084](https://github.com/M1778/fin-sdk/actions/runs/40034937084)
> at zhttp revision `5f6746da3a2294804c42534ba44a066c6b6705c8`.
> Tests include loopback GET/POST, chunked decoding and malformed framed peers.
> The exact compiler candidate is `5360b051b8e82a4f10052c3dbb77bc66cc727cd7`
> from successful CI run `40028977601`, not a released toolchain.

## Install

Requires the `finn` package manager (https://github.com/M1778/finn):

```sh
finn add M1778/zhttp
```


## Quick Example

**Server** (see `examples/server.fin`):

```fin
import {
    HttpRequest, HttpResponse, HttpReadResult,
    http_listen, http_accept, http_read_request,
    http_write_response, http_response,
    http_free_response, http_free_read_result, http_close
} from zhttp::fin;
import { equals } from strings::std;

fun handle(req: &HttpRequest) <&HttpResponse> {
    if (equals(req.target, "/")) {
        return http_response(200, "Hello from zhttp!\n");
    }
    return http_response(404, "not found\n");
}

fun main() <noret> {
    let srv <&HttpServer> = http_listen(8080);
    while (true) {
        let conn <&HttpConn> = http_accept(srv);
        let rr <HttpReadResult> = http_read_request(conn);
        if (rr.ok) {
            let resp <&HttpResponse> = handle(rr.req);
            http_write_response(conn, resp);
            http_free_response(resp);
            http_free_request(rr.req);
        }
        http_close(conn);
    }
}
```

**Client** (see `examples/client.fin`):

```fin
import { HttpResult, http_get, http_free_result } from zhttp::fin;

fun main() <noret> {
    let r <HttpResult> = http_get("http://127.0.0.1:8080/");
    if (!r.ok) {
        printf("request failed: %s\n", r.err);
        http_free_result(r);
        return;
    }
    printf("status: %d\nbody:\n%s\n", r.status, r.body);
    http_free_result(r);
}
```

## API Reference

### URL parsing

```fin
fun http_parse_url(s: string) <HttpUrlResult>   // { ok, url, err }
fun http_free_url_result(r: &HttpUrlResult) <noret>
```

`HttpUrl` carries `scheme`, `host`, `port` (default 80), `path` (default `/`),
and `query` (empty string when absent). Only `http://` is supported in v0.1 —
`https://` is rejected with a clear error (no TLS yet).

### Client

```fin
fun http_get(url: string) <HttpResult>
fun http_post(url: string, content_type: string, body: string) <HttpResult>
fun http_free_result(r: &HttpResult) <noret>
```

`HttpResult` carries `ok`, `status`, `headers`, `body`, and `err`. Connection
failures, malformed URLs, and read errors are recoverable (`ok == false` with a
message in `err`), never aborts. Response bodies are decoded from
`Content-Length`, `Transfer-Encoding: chunked`, or read-until-close.

### Server

```fin
fun http_listen(port: int) <&HttpServer>        // port 0 = ephemeral; aborts on bind failure
fun http_server_port(srv: &HttpServer) <int>    // the bound port
fun http_server_close(srv: &HttpServer) <noret>
fun http_accept(srv: &HttpServer) <&HttpConn>
fun http_read_request(conn: &HttpConn) <HttpReadResult>  // { ok, req, err }
fun http_free_read_result(rr: &HttpReadResult) <noret>
fun http_write_response(conn: &HttpConn, resp: &HttpResponse) <bool>
fun http_write_raw(conn: &HttpConn, text: string) <bool> // raw bytes (e.g. upgrades)
fun http_close(conn: &HttpConn) <noret>
fun http_detach(conn: &HttpConn) <int> // frees wrapper, transfers fd ownership
```

`http_read_request` rejects malformed input with `ok == false`; close the
connection after rejection rather than attempting to resynchronize. Duplicate
Content-Length or Transfer-Encoding fields, duplicate Host/WebSocket handshake
singletons, TE+CL, malformed field syntax, and all request transfer codings are
rejected. Chunked **responses** are supported;
chunked requests are not.

Header reads consume exactly through CRLFCRLF, and length-delimited request
bodies consume exactly their declared length. Bytes for an upgraded protocol
remain in the socket. `http_detach` frees the connection wrapper without closing
the fd; after detaching, do not use the wrapper, and eventually close the returned
fd yourself. Only one reader may access a connection at a time.

`http_listen`/`http_accept` still abort (`blame`) on permanent failures.
Interrupted accept/send/recv calls are retried; Linux `MSG_NOSIGNAL` suppresses
SIGPIPE per send without modifying the application's signal handlers.

### Responses

```fin
fun http_response(status: int, body: string) <&HttpResponse>
fun http_response_with_type(status: int, content_type: string, body: string) <&HttpResponse>
fun http_free_response(r: &HttpResponse) <noret>
fun http_free_request(q: &HttpRequest) <noret>
```

`http_response` sets `Content-Type: text/plain; charset=utf-8` and a correct
`Content-Length` automatically, except for 1xx/204 where length is forbidden.
The writer omits bodies for 1xx, 204, and 304 responses.

### Headers and status codes

```fin
fun http_status_text(code: int) <string>   // static string; do NOT free
fun http_new_headers() <&HttpHeaders>
fun http_free_headers(hdrs: &HttpHeaders) <noret>
fun http_header_has(hdrs: &HttpHeaders, name: string) <bool>
fun http_header_get(hdrs: &HttpHeaders, name: string) <string>  // "" if absent; borrowed, do NOT free
fun http_header_set(hdrs: &HttpHeaders, name: string, value: string) <noret>  // copies both
fun http_header_count(hdrs: &HttpHeaders) <int>
fun http_header_name(hdrs: &HttpHeaders, i: int) <string>   // borrowed
fun http_header_value(hdrs: &HttpHeaders, i: int) <string>  // borrowed
```

Header names are matched case-insensitively per RFC 9110. `http_header_get`
returns `""` for a missing header (finc 0.4.0 cannot return null as a string);
use `http_header_has` to distinguish missing from empty.

## Limitations (v0.1)

- **IPv4 dotted-quad hosts only** — no DNS resolution (`http://127.0.0.1:8080/`
  works; `http://localhost/` does not). Same limitation as `networking::std`.
- **No TLS** — `https://` URLs are rejected with an explicit error.
- **Native transport for Linux, macOS and Windows** — the socket ABI, the
  error source and the buffer types are selected from the compiler's native
  target (ADR 0051 addendum): `SOCKET` is a pointer width on Windows and an
  `int` elsewhere, `send`/`recv` take an `int` length on Windows and a
  `size_t` one elsewhere, and a failure is read from `WSAGetLastError` or from
  `errno` as the target requires. `MSG_NOSIGNAL` is used on Linux only; macOS
  sets `SO_NOSIGPIPE` on the socket instead, and Windows has neither, so a
  write to a closed peer is reported as an error rather than a signal.
  The declarations live here and nowhere else, so a consumer cannot declare
  the same linker symbols with a signature that disagrees: `fin-websocket`
  uses this module's exported raw read and write.
- **Blocking I/O without deadlines** — framed responses return at message
  completion, not EOF, but incomplete messages and close-delimited responses can
  still wait indefinitely. Applications must provide deadlines/concurrency.
- Request and response bodies are capped at **16 MiB**, including aggregate
  decoded chunk data. Port parsing remains independently bounded to 1–65535.
- Request and response header blocks are capped at **64 KiB**, including the
  start line and final CRLFCRLF, with at most **256 fields**.
- Chunk-size/extension and trailer lines are capped at **8 KiB** each; aggregate
  chunk metadata (size lines, data delimiters, and trailers) is capped at **64 KiB**,
  with at most **256 trailer fields**. Trailers are validated then discarded;
  framing/routing fields are forbidden in trailers. At most 16 informational
  responses are skipped before a final response.
- Bodies are byte strings; embedded NUL bytes truncate (Fin strings are
  NUL-terminated). Header NUL bytes are rejected.

## Dependencies

- Fin standard library only (`collection::std`, `strings::std`, `testing::std`
  for tests). The socket bindings are vendored here because only `#[global]`
  externs lower through module imports, and they are selected for the native
  target rather than fixed to one platform's ABI.

## Development

```sh
finc -I src tests/test_lib.fin -o test_zhttp && ./test_zhttp
python3 -I tests/test_protocol.py ./test_zhttp
```

Repeat with `-O2` as well as the default `-O0`. The Python peer suite uses
loopback ephemeral ports/socketpairs to exercise malformed framing, exact
limits, truncation, keep-open responses, upgrade handoff, and peer-close writes.
It also uses `cc` to build a temporary fault-injection shim for EINTR and partial
send/recv coverage. No external service is required.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

MIT — see [LICENSE](LICENSE).

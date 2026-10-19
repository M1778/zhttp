# zhttp

HTTP/1.1 client and server for [Fin](https://github.com/M1778/Fin). Built on raw
blocking TCP over IPv4 (the same design as `networking::std`).

> **Verification status:** ✅ VERIFIED — built with `finc 0.4.0` (contract 3);
> full test suite passes, including real loopback client/server tests (GET, POST
> echo, chunked decoding). CI also builds finc from source and re-runs everything.

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
```

`http_read_request` never aborts on malformed client input — it returns
`ok == false` with a message, so a bad client can't crash the server.
`http_listen`/`http_accept` abort (`blame`) on failure, matching
`networking::std`'s contract: a server that can't bind or accept can't proceed.

### Responses

```fin
fun http_response(status: int, body: string) <&HttpResponse>
fun http_response_with_type(status: int, content_type: string, body: string) <&HttpResponse>
fun http_free_response(r: &HttpResponse) <noret>
fun http_free_request(q: &HttpRequest) <noret>
```

`http_response` sets `Content-Type: text/plain; charset=utf-8` and a correct
`Content-Length` automatically.

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
- **Blocking I/O** — one connection at a time per thread; use one process per
  connection (fork) or add threads for concurrency.
- Request bodies are capped at 16 MiB; request headers at 64 KiB.
- Bodies are byte strings; embedded NUL bytes truncate (Fin strings are
  NUL-terminated).

## Dependencies

- Fin standard library only (`collection::std`, `strings::std`, `testing::std`
  for tests). The socket layer re-declares libc's socket calls with the same
  ABI as `networking::std` (vendored because only `#[global]` externs lower
  through a module import — see `docs/guide/10-modules-and-imports.md`).

## Development

```sh
finc -I src tests/test_lib.fin -o test_zhttp && ./test_zhttp
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

MIT — see [LICENSE](LICENSE).

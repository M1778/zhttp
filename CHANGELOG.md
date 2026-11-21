# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Request deadlines.** Every socket now carries a read and a write deadline,
  30 s by default, applied by `http_socket_dial` and `http_accept`. A peer that
  opens a connection and then stops talking no longer blocks the caller forever.
  A deadline that expires is reported as `timed out reading request headers`,
  `timed out reading request body`, `timed out reading response headers`, or
  `timed out reading response body`, not as a truncation.
- `http_get_with_timeout` and `http_post_with_timeout` for a per-request deadline.
- `http_socket_timeout` to apply a deadline to any socket handle.
- `FINC_VERSION`, `.github/scripts/install_finc.py` and
  `.github/scripts/install_finn.py`: CI installs the pinned released compiler and
  package manager, verifying the published sha256 and refusing a mismatch.
- `scripts/fin_header.py`, and the project header on every source file.
- CI on Linux, macOS and Windows that compiles **and executes** both test suites
  at `-O0` and `-O2`, builds the examples, and proves a `finn` consumer can
  resolve `import { ... } from zhttp::fin`.
- Tests for each new guard, including the ones that must fail without it.

### Changed

- `HttpConn` gained a `served` field. `http_read_request` uses it to refuse a
  second read on the same connection by name, instead of parsing whatever bytes
  remain after the first message as a new request. This is an API change for code
  that constructs `HttpConn` by hand: a literal needs `served: false`.
- `finn.toml` now describes a library, not an application. The `entrypoint` is a
  file with no `main`, so `finn build` fails by design and `finn test` is the
  supported command. The version moves to 0.2.0.
- The package entry module moved from `exports.fin` (which was not valid Fin:
  `export * from "src/zhttp";` is a syntax error) to `zhttp.fin`, a real module
  that publishes the `fin` namespace. `import ... from zhttp::fin` now resolves
  for a `finn` consumer, which it did not before.
- README rewritten: what the library does and does not do, the enforced limits,
  the POSIX/Windows split, and a runnable example whose output is shown.

### Fixed

- **Header injection through a URL.** The request target and `Content-Type` were
  copied to the wire verbatim, so a `\r\n` in either injected a header into the
  request. Both are now refused before the socket is dialled. A host containing a
  control character, a space, or DEL is rejected by `http_parse_url`.
- **`http_socket_read_exact` corrupted fragmented reads.** Each partial read
  overwrote the buffer from index 0, so a message arriving in two segments came
  back as the second segment followed by zeroes. It now reads at the current
  offset.
- A read deadline expiring was indistinguishable from a truncated body. The read
  status is threaded through the parser so callers see which happened.

### Removed

- `exports.fin`, which no Fin compiler could parse.

### Notes on verification

- Local: Linux x86_64, `finc 1.0.0` (contract 3), both suites at `-O0` and `-O2`,
  plus a real `curl` session against `examples/server.fin`.
- The EINTR / short-read fault-injection case uses `LD_PRELOAD` and is therefore
  Linux-only. On macOS and Windows it prints `SKIP` with the reason; it is never
  silently absent.

## [0.1.0] - 2026-10-19

### Added
- Initial release: HTTP/1.1 client (`http_get`, `http_post`) and server
  (`http_listen`, `http_accept`, `http_read_request`, `http_write_response`).
- URL parsing with validation (`http_parse_url`); only `http://` supported.
- Status code table (`http_status_text`), case-insensitive headers
  (`http_header_get`/`http_header_set`).
- Response body decoding: `Content-Length`, `Transfer-Encoding: chunked`,
  read-until-close.
- `http_write_raw` for protocol upgrades (e.g. WebSocket handshakes).
- Recoverable errors for all I/O and client input (never `blame` on the
  wire); `blame` only for programmer errors (bind/accept failures).
- Loopback client/server tests (GET, POST echo, chunked decoding),
  URL/status/header unit tests.
- `examples/server.fin` (routing example), `examples/client.fin`,
  GitHub Actions CI, `finn.toml` manifest, MIT license.

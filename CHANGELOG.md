# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
- Loopback client/server tests using `fork()` (GET, POST echo, chunked
  decoding), URL/status/header unit tests.
- `examples/server.fin` (routing example), `examples/client.fin`,
  GitHub Actions CI, `finn.toml` manifest, MIT license.

### Verification
- ✅ VERIFIED 2026-10-19: built with `finc 0.4.0` (contract 3); the full test
  suite passes (`finc -I src tests/test_lib.fin -o test_zhttp && ./test_zhttp`),
  including real loopback client/server tests (GET, POST echo, chunked
  decoding via `fork()`). `examples/server.fin` + `examples/client.fin`
  verified end-to-end (also against curl).

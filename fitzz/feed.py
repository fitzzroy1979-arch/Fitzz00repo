#!/usr/bin/env python3
"""
feed.py — a live crypto price feed over CoinMarketCap's public price stream.

Unlike the rest of the toolkit (which reads TradingView Desktop through the
`tv` bridge), this tool opens a WebSocket straight to CoinMarketCap and prints
price updates as they arrive:

    fitzz feed                       # BTC + ETH (crypto ids 1 and 1027)
    fitzz feed --symbols BTC,ETH,SOL
    fitzz feed --ids 1,1027,5426
    fitzz feed --json                # raw stream frames, one JSON object/line
    fitzz feed --duration 30         # stop after 30s
    fitzz feed --limit 20            # stop after 20 price updates

On connect it sends the subscribe frame CMC's push endpoint actually accepts:

    {"method": "RSUBSCRIPTION",
     "params": ["main-site@crypto_price_5s@{}@normal", "1,1027"]}

(The `{"method":"subscribe","channel":"market@crypto_latest_price",
"params":{"crypto_ids":[...]}}` shape gets answered with
`{"error":{"code":2201,"msg":"MSG_FORMAT_INVALID"}}` by
push.coinmarketcap.com, and `stream.coinmarketcap.com` does not resolve at
all. Use --channel/--url if CMC changes it again.)

Read-only: this tool never places an order and never sends anything but the
subscribe frame and protocol pongs.

No third-party dependency — the WebSocket client below is a small RFC 6455
implementation over `ssl`/`socket`, enough for a client that sends one text
frame and then reads.
"""

import argparse
import base64
import hashlib
import json
import os
import socket
import ssl
import struct
import sys
import time
from urllib.parse import urlparse

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

DEFAULT_URL = "wss://push.coinmarketcap.com/ws?device=web&client_source=home_page"
# `{}` is filled in by the server with each crypto id. The `@detail` variant
# acknowledges a subscribe but does not push on this endpoint; `@normal` does.
DEFAULT_CHANNEL = "main-site@crypto_price_5s@{}@normal"
DEFAULT_IDS = [1, 1027]  # BTC, ETH

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"  # RFC 6455 handshake constant

# CoinMarketCap crypto ids for the coins people actually ask for. Anything not
# here can still be streamed by passing --ids explicitly.
SYMBOL_IDS = {
    "BTC": 1, "LTC": 2, "XRP": 52, "DOGE": 74, "XLM": 512, "USDT": 825,
    "ETH": 1027, "BCH": 1831, "BNB": 1839, "EOS": 1765, "LINK": 1975,
    "ADA": 2010, "XMR": 328, "TRX": 1958, "ETC": 1321, "USDC": 3408,
    "ATOM": 3794, "AVAX": 5805, "SHIB": 5994, "MATIC": 3890, "POL": 28321,
    "DOT": 6636, "UNI": 7083, "SOL": 5426, "NEAR": 6535, "APT": 21794,
    "ARB": 11841, "OP": 11840, "SUI": 20947, "TON": 11419, "PEPE": 24478,
    "HBAR": 4642, "ICP": 8916, "FIL": 2280, "AAVE": 7278, "INJ": 7226,
    "TAO": 22974, "RNDR": 5690, "IMX": 10603, "SEI": 23149, "TIA": 22861,
}
ID_SYMBOLS = {v: k for k, v in SYMBOL_IDS.items()}

# WebSocket opcodes.
OP_CONT, OP_TEXT, OP_BINARY = 0x0, 0x1, 0x2
OP_CLOSE, OP_PING, OP_PONG = 0x8, 0x9, 0xA


class WebSocketError(Exception):
    """Handshake or framing failure."""


class ConnectionClosed(Exception):
    """The peer sent a close frame (or the socket went away)."""


# --------------------------------------------------------------------------- #
# Minimal RFC 6455 client
# --------------------------------------------------------------------------- #

class WebSocket:
    """A client-side WebSocket good enough to subscribe and read text frames."""

    def __init__(self, sock, timeout=None):
        self.sock = sock
        self.sock.settimeout(timeout)
        self._buf = b""

    # -- connect ----------------------------------------------------------- #

    @classmethod
    def connect(cls, url, origin=None, timeout=30, headers=None):
        parts = urlparse(url)
        if parts.scheme not in ("ws", "wss"):
            raise WebSocketError(f"not a websocket url: {url!r}")
        secure = parts.scheme == "wss"
        port = parts.port or (443 if secure else 80)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query

        raw = socket.create_connection((parts.hostname, port), timeout=timeout)
        if secure:
            ctx = ssl.create_default_context()
            raw = ctx.wrap_socket(raw, server_hostname=parts.hostname)

        key = base64.b64encode(os.urandom(16)).decode()
        host = parts.hostname if port in (80, 443) else f"{parts.hostname}:{port}"
        lines = [
            f"GET {path} HTTP/1.1",
            f"Host: {host}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {key}",
            "Sec-WebSocket-Version: 13",
            "User-Agent: fitzz-feed/0.1",
        ]
        if origin:
            lines.append(f"Origin: {origin}")
        for name, value in (headers or {}).items():
            lines.append(f"{name}: {value}")
        raw.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())

        ws = cls(raw, timeout=timeout)
        ws._handshake(key)
        return ws

    def _handshake(self, key):
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise WebSocketError("connection closed during handshake")
            head += chunk
            if len(head) > 65536:
                raise WebSocketError("handshake response too large")
        head, _, rest = head.partition(b"\r\n\r\n")
        self._buf = rest  # frames may already be riding along behind the header

        text = head.decode("latin-1")
        status = text.split("\r\n", 1)[0]
        if "101" not in status:
            raise WebSocketError(f"upgrade refused: {status}")

        expected = base64.b64encode(
            hashlib.sha1((key + GUID).encode()).digest()
        ).decode()
        for line in text.split("\r\n")[1:]:
            name, _, value = line.partition(":")
            if name.strip().lower() == "sec-websocket-accept":
                if value.strip() != expected:
                    raise WebSocketError("bad Sec-WebSocket-Accept")
                break
        else:
            raise WebSocketError("no Sec-WebSocket-Accept header")

    # -- io ---------------------------------------------------------------- #

    def _read(self, n):
        while len(self._buf) < n:
            chunk = self.sock.recv(max(4096, n - len(self._buf)))
            if not chunk:
                raise ConnectionClosed("socket closed by peer")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def _send_frame(self, opcode, payload=b""):
        # Clients MUST mask every frame they send (RFC 6455 §5.3).
        head = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            head.append(0x80 | length)
        elif length < (1 << 16):
            head.append(0x80 | 126)
            head += struct.pack("!H", length)
        else:
            head.append(0x80 | 127)
            head += struct.pack("!Q", length)
        mask = os.urandom(4)
        head += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(head) + masked)

    def send_text(self, text):
        self._send_frame(OP_TEXT, text.encode())

    def _recv_frame(self):
        b0, b1 = self._read(2)
        fin = bool(b0 & 0x80)
        opcode = b0 & 0x0F
        masked = bool(b1 & 0x80)
        length = b1 & 0x7F
        if length == 126:
            (length,) = struct.unpack("!H", self._read(2))
        elif length == 127:
            (length,) = struct.unpack("!Q", self._read(8))
        mask = self._read(4) if masked else None
        payload = self._read(length) if length else b""
        if mask:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return fin, opcode, payload

    def recv(self):
        """Return the next complete text/binary message as bytes.

        Control frames (ping/close) are handled here and never surface.
        """
        buf = b""
        frame_op = None
        while True:
            fin, opcode, payload = self._recv_frame()
            if opcode == OP_PING:
                self._send_frame(OP_PONG, payload)
                continue
            if opcode == OP_PONG:
                continue
            if opcode == OP_CLOSE:
                code = struct.unpack("!H", payload[:2])[0] if len(payload) >= 2 else None
                reason = payload[2:].decode("utf-8", "replace")
                try:
                    self._send_frame(OP_CLOSE, payload[:2])
                except OSError:
                    pass
                raise ConnectionClosed(f"peer closed ({code}) {reason}".strip())
            if opcode in (OP_TEXT, OP_BINARY):
                frame_op = opcode
                buf = payload
            elif opcode == OP_CONT:
                buf += payload
            if fin and frame_op is not None:
                return buf

    def close(self):
        try:
            self._send_frame(OP_CLOSE, struct.pack("!H", 1000))
        except OSError:
            pass
        finally:
            try:
                self.sock.close()
            except OSError:
                pass


# --------------------------------------------------------------------------- #
# CoinMarketCap stream
# --------------------------------------------------------------------------- #

def subscribe_frame(crypto_ids, channel=DEFAULT_CHANNEL):
    """Build the subscribe payload the CMC price stream expects."""
    ids = ",".join(str(int(i)) for i in crypto_ids)
    return {"method": "RSUBSCRIPTION", "params": [channel, ids]}


def _first_number(d, keys):
    for k in keys:
        v = d.get(k)
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                pass
    return None


def parse_ticks(message):
    """Pull price ticks out of a stream frame.

    A tick currently arrives as ``{"d":{"id":1,"p":79628.18,"p24h":0.15,...},
    "t":"1787919817220","c":"main-site@crypto_price_5s@1@normal"}``, but CMC has
    shipped other envelopes for this data, so rather than hard-coding one we walk
    the JSON for any object carrying an id and a price and return those as
    ``{id, symbol, price, change_24h, volume_24h, timestamp}``. Subscribe acks
    and error frames carry no price and yield nothing.
    """
    ticks = []
    seen = set()
    # The millisecond stamp sits on the envelope, one level above the tick body.
    timestamp = None
    if isinstance(message, dict):
        timestamp = _first_number(message, ("t", "timestamp"))

    def walk(node):
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        cid = node.get("id") if isinstance(node.get("id"), (int, str)) else None
        price = _first_number(node, ("p", "price", "pr"))
        if cid is not None and price is not None:
            try:
                cid = int(cid)
            except (TypeError, ValueError):
                cid = None
            if cid is not None and id(node) not in seen:
                seen.add(id(node))
                ticks.append({
                    "id": cid,
                    "symbol": ID_SYMBOLS.get(cid, str(cid)),
                    "price": price,
                    "change_24h": _first_number(node, ("p24h", "percent_change_24h", "pc24h")),
                    "market_cap": _first_number(node, ("mc", "market_cap")),
                    "volume_24h": _first_number(node, ("v", "volume_24h", "v24h")),
                    "timestamp": timestamp,
                })
        for value in node.values():
            walk(value)

    walk(message)
    return ticks


def _fmt_price(price):
    if price >= 1000:
        return f"${price:,.2f}"
    if price >= 1:
        return f"${price:,.4f}"
    return f"${price:.8f}".rstrip("0")


def _fmt_tick(tick, width=6):
    change = tick.get("change_24h")
    if change is None:
        pct = ""
    else:
        pct = f"  {change:+.2f}%"
    ts = tick.get("timestamp")
    # CMC stamps are epoch milliseconds; fall back to the wall clock.
    stamp = (time.strftime("%H:%M:%S", time.localtime(ts / 1000.0))
             if ts and ts > 1e11 else time.strftime("%H:%M:%S"))
    return f"{stamp}  {tick['symbol']:<{width}} {_fmt_price(tick['price']):>16}{pct}"


def stream(crypto_ids, url=DEFAULT_URL, channel=DEFAULT_CHANNEL, timeout=30,
           on_message=None):
    """Connect, subscribe, and yield each decoded stream message."""
    origin = "https://coinmarketcap.com"
    ws = WebSocket.connect(url, origin=origin, timeout=timeout)
    try:
        ws.send_text(json.dumps(subscribe_frame(crypto_ids, channel)))
        while True:
            raw = ws.recv()
            try:
                message = json.loads(raw.decode("utf-8", "replace"))
            except json.JSONDecodeError:
                continue
            if on_message is not None:
                on_message(message)
            yield message
    finally:
        ws.close()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _resolve_ids(args):
    ids = []
    if args.ids:
        for chunk in args.ids.replace(",", " ").split():
            try:
                ids.append(int(chunk))
            except ValueError:
                raise SystemExit(f"fitzz feed: not a numeric crypto id: {chunk!r}")
    if args.symbols:
        unknown = []
        for chunk in args.symbols.replace(",", " ").split():
            sym = chunk.upper().replace("USD", "") or chunk.upper()
            cid = SYMBOL_IDS.get(chunk.upper()) or SYMBOL_IDS.get(sym)
            if cid is None:
                unknown.append(chunk)
            else:
                ids.append(cid)
        if unknown:
            known = ", ".join(sorted(SYMBOL_IDS))
            raise SystemExit(
                f"fitzz feed: unknown symbol(s): {', '.join(unknown)}\n"
                f"  pass --ids with CoinMarketCap crypto ids instead, or use one of:\n  {known}"
            )
    seen, out = set(), []
    for cid in ids or DEFAULT_IDS:
        if cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


def build_parser():
    p = argparse.ArgumentParser(
        prog="fitzz feed",
        description="Live crypto prices from CoinMarketCap's public WebSocket stream.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  fitzz feed\n"
            "  fitzz feed --symbols BTC,ETH,SOL\n"
            "  fitzz feed --ids 1,1027 --json\n"
            "  fitzz feed --duration 30 --reconnect\n"
        ),
    )
    p.add_argument("--symbols", help="comma-separated tickers, e.g. BTC,ETH,SOL")
    p.add_argument("--ids", help="comma-separated CoinMarketCap crypto ids, e.g. 1,1027")
    p.add_argument("--url", default=DEFAULT_URL, help=f"stream URL (default: {DEFAULT_URL})")
    p.add_argument("--channel", default=DEFAULT_CHANNEL,
                   help="channel template to subscribe to "
                        f"(default: {DEFAULT_CHANNEL})")
    p.add_argument("--json", action="store_true",
                   help="print each raw stream frame as one JSON object per line")
    p.add_argument("--limit", type=int, help="stop after N price updates")
    p.add_argument("--duration", type=float, help="stop after N seconds")
    p.add_argument("--timeout", type=float, default=30.0,
                   help="socket timeout in seconds (default: 30)")
    p.add_argument("--reconnect", action="store_true",
                   help="reconnect with backoff when the stream drops")
    p.add_argument("--quiet", action="store_true", help="suppress the connection banner")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    ids = _resolve_ids(args)

    labels = ", ".join(f"{ID_SYMBOLS.get(i, '?')}({i})" for i in ids)
    deadline = time.time() + args.duration if args.duration else None
    count = 0
    backoff = 1.0

    while True:
        if not args.quiet:
            print(f"# connecting to {args.url}", file=sys.stderr)
            print(f"# subscribing to {args.channel} for {labels}", file=sys.stderr)
        timeout = args.timeout
        if deadline:
            timeout = max(1.0, min(timeout, deadline - time.time()))
        try:
            for message in stream(ids, url=args.url, channel=args.channel,
                                  timeout=timeout):
                backoff = 1.0
                if args.json:
                    print(json.dumps(message, separators=(",", ":")), flush=True)
                ticks = parse_ticks(message)
                if not args.json:
                    width = max((len(t["symbol"]) for t in ticks), default=6)
                    for tick in ticks:
                        print(_fmt_tick(tick, width), flush=True)
                count += len(ticks)
                if args.limit and count >= args.limit:
                    return 0
                if deadline and time.time() >= deadline:
                    return 0
        except KeyboardInterrupt:
            print("", file=sys.stderr)
            return 130
        except (ConnectionClosed, WebSocketError, OSError) as exc:
            if deadline and time.time() >= deadline:
                return 0
            if not args.reconnect:
                print(f"fitzz feed: stream ended: {exc}", file=sys.stderr)
                return 1
            print(f"fitzz feed: {exc}; reconnecting in {backoff:.0f}s", file=sys.stderr)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60.0)


if __name__ == "__main__":
    raise SystemExit(main())

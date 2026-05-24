from pathlib import Path
import struct
import zlib
import binascii
import sys

DEFAULT_SRC = Path('/game.exn')
DEFAULT_OUT = Path('/render_exn_all')

src_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SRC
out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT

SRC = src_path.read_bytes()
OUT = out_path
OUT.mkdir(parents=True, exist_ok=True)
SIG = b'\x89PNG\r\n\x1a\n'


def read_bits(buf: bytes, bitpos: int, n: int) -> tuple[int, int]:
    v = 0
    for _ in range(n):
        bidx = bitpos >> 3
        boff = bitpos & 7
        bit = 0
        if bidx < len(buf):
            bit = (buf[bidx] >> (7 - boff)) & 1
        v = (v << 1) | bit
        bitpos += 1
    return v, bitpos


def write_bits(out: bytearray, bitpos: int, val: int, n: int) -> int:
    for i in range(n):
        bit = (val >> (n - 1 - i)) & 1
        idx = (bitpos + i) >> 3
        boff = (bitpos + i) & 7
        if idx >= len(out):
            out.extend(b'\x00' * (idx - len(out) + 1))
        if bit:
            out[idx] |= (1 << (7 - boff))
        else:
            out[idx] &= ~(1 << (7 - boff))
    return bitpos + n


def p432d(h: bytes) -> tuple[int, int]:
    a = ((h[0] & 0x0F) << 28) | (h[1] << 20) | (h[2] << 12) | (h[3] << 4) | ((h[4] & 0xF0) >> 4)
    c = ((h[4] & 0x0F) << 28) | (h[5] << 20) | (h[6] << 12) | (h[7] << 4) | ((h[8] & 0xF0) >> 4)
    return a, c


def sz(h: bytes) -> int:
    a, c = p432d(h)
    return ((a + 7) & ~7) * c


def decode_type5(pay: bytes, out_bytes: int) -> bytes:
    if not pay:
        return b''
    out_len = out_bytes if out_bytes > 0 else int.from_bytes(pay[9:12], 'little')
    buf = bytearray(b'\x00' * out_len)
    src_base = out_len - len(pay) if len(pay) < out_len else 0
    copy_len = min(len(pay), out_len)
    buf[src_base:src_base + copy_len] = pay[:copy_len]
    src_pos = src_base + 13
    dst_pos = 0

    while src_pos + 4 <= len(buf) and dst_pos < out_len:
        token = int.from_bytes(buf[src_pos:src_pos + 4], 'big', signed=True)
        src_pos += 4
        shift = 0xE - (token & 3)
        mask = 0x3FFF >> (token & 3)

        for _ in range(0x1E):
            if token >= 0:
                if dst_pos == src_pos:
                    snap = bytes(buf[src_pos:src_pos + 0x400])
                    if not snap:
                        return bytes(buf[:out_len])
                    buf.extend(snap)
                    src_pos = len(buf) - len(snap)
                if src_pos >= len(buf):
                    return bytes(buf[:out_len])
                buf[dst_pos] = buf[src_pos]
                dst_pos += 1
                src_pos += 1
            else:
                if src_pos + 2 > len(buf):
                    return bytes(buf[:out_len])
                pair = (buf[src_pos] << 8) | buf[src_pos + 1]
                src_pos += 2
                length = (pair >> shift) + 3
                if dst_pos + length > out_len:
                    length = out_len - dst_pos
                dist = (pair & mask) + 1
                for _k in range(length):
                    if dst_pos == src_pos:
                        snap = bytes(buf[src_pos:src_pos + 0x400])
                        if not snap:
                            return bytes(buf[:out_len])
                        buf.extend(snap)
                        src_pos = len(buf) - len(snap)
                    idx = dst_pos - dist
                    if idx < 0:
                        return bytes(buf[:out_len])
                    buf[dst_pos] = buf[idx]
                    dst_pos += 1

            if dst_pos >= out_len:
                return bytes(buf[:out_len])

            token = (token << 1) & 0xFFFFFFFF
            if token & 0x80000000:
                token -= 0x100000000

    return bytes(buf[:out_len])


def decode_type3(pay: bytes, out_bytes: int) -> bytes:
    st = {}
    st['src_bitpos'] = 0x44
    a, c = p432d(pay)
    st['wbits'] = a
    st['h'] = c
    st['base_bits'], st['src_bitpos'] = read_bits(pay, st['src_bitpos'], 4)
    st['mode_bits'], st['src_bitpos'] = read_bits(pay, st['src_bitpos'], 4)
    st['symbol_bits'] = st['base_bits'] * st['mode_bits']
    st['line_bits'] = (((a + 7) >> 3) << 3)
    st['line_bits_cur'] = st['line_bits']
    st['remain_bits'] = st['line_bits'] * c
    if (c & 1) and st['mode_bits'] == 2:
        st['remain_bits'] -= st['line_bits']
    st['table'] = [0] * 10
    for i in range(10):
        acc = 0
        bits = st['symbol_bits']
        while bits >= 8:
            bits -= 8
            v, st['src_bitpos'] = read_bits(pay, st['src_bitpos'], 8)
            acc = (acc << 8) | v
        if bits > 0:
            v, st['src_bitpos'] = read_bits(pay, st['src_bitpos'], bits)
            acc = (acc << bits) | v
        st['table'][i] = acc
    st['src_anchor'] = st['src_bitpos']
    st['row_idx'] = 1
    out = bytearray()
    out_bitpos = 0
    need_bits = out_bytes * 8
    while need_bits > 0 and st['remain_bits'] > 0:
        if st['line_bits_cur'] < st['base_bits']:
            val, st['src_bitpos'] = read_bits(pay, st['src_bitpos'], st['line_bits_cur'] * st['mode_bits'])
            out_bitpos = write_bits(out, out_bitpos, val & ((1 << st['base_bits']) - 1), st['base_bits'])
            need_bits -= st['base_bits']
            st['remain_bits'] -= st['base_bits']
            st['line_bits_cur'] = st['line_bits']
            st['row_idx'] += 1
            continue
        prefix, st['src_bitpos'] = read_bits(pay, st['src_bitpos'], 2)
        if prefix <= 1:
            raw = st['table'][prefix]
        elif prefix == 2:
            idx, st['src_bitpos'] = read_bits(pay, st['src_bitpos'], 3)
            raw = st['table'][idx + 2]
        else:
            raw, st['src_bitpos'] = read_bits(pay, st['src_bitpos'], st['symbol_bits'])
        shift = st['base_bits'] * (st['mode_bits'] - st['row_idx'])
        if shift < 0:
            shift = 0
        out_val = (raw >> shift) & ((1 << st['base_bits']) - 1)
        out_bitpos = write_bits(out, out_bitpos, out_val, st['base_bits'])
        need_bits -= st['base_bits']
        st['remain_bits'] -= st['base_bits']
        st['line_bits_cur'] -= st['base_bits']
        if st['line_bits_cur'] <= 0:
            st['line_bits_cur'] = st['line_bits']
            st['row_idx'] += 1
            if st['row_idx'] > st['mode_bits']:
                st['row_idx'] = 1
                st['src_bitpos'] = st['src_anchor']
    if len(out) < out_bytes:
        out.extend(b'\x00' * (out_bytes - len(out)))
    return bytes(out[:out_bytes])


def decode_type1(pay: bytes, out_bytes: int) -> bytes:
    st = {}
    st['src_bitpos'] = 0x44
    st['pending_bits'] = 0
    st['pending_val'] = 0
    a, c = p432d(pay)
    st['src_cursor'], st['src_bitpos'] = read_bits(pay, st['src_bitpos'], 5)
    st['sym_bits'], st['src_bitpos'] = read_bits(pay, st['src_bitpos'], 5)
    st['table_count'] = st['src_cursor']
    table = [0] * st['table_count']
    out = bytearray()
    out_bitpos = 0
    need_bits = out_bytes * 8
    src_bitpos = st['src_bitpos']
    remaining = sz(pay)
    while remaining >= st['sym_bits'] and need_bits > 0:
        flag, src_bitpos = read_bits(pay, src_bitpos, 1)
        if flag != 1:
            raw, src_bitpos = read_bits(pay, src_bitpos, st['sym_bits'])
            idx_top = st['table_count'] - 1
        else:
            idx, src_bitpos = read_bits(pay, src_bitpos, 5)
            raw = table[idx]
            idx_top = idx
        if idx_top > 0:
            for j in range(idx_top, 0, -1):
                table[j] = table[j - 1]
        table[0] = raw
        remaining -= st['sym_bits']
        if need_bits < st['sym_bits']:
            take = need_bits
            out_bitpos = write_bits(out, out_bitpos, raw >> (st['sym_bits'] - take), take)
            st['pending_bits'] = st['sym_bits'] - take
            st['pending_val'] = raw & ((1 << st['pending_bits']) - 1)
            need_bits = 0
            break
        out_bitpos = write_bits(out, out_bitpos, raw, st['sym_bits'])
        need_bits -= st['sym_bits']
    while remaining >= 8 and need_bits >= 8:
        val, src_bitpos = read_bits(pay, src_bitpos, 8)
        out_bitpos = write_bits(out, out_bitpos, val, 8)
        remaining -= 8
        need_bits -= 8
    if remaining > 0 and need_bits > 0:
        val, src_bitpos = read_bits(pay, src_bitpos, remaining)
        take = min(need_bits, remaining)
        out_bitpos = write_bits(out, out_bitpos, val >> (remaining - take), take)
    if len(out) < out_bytes:
        out.extend(b'\x00' * (out_bytes - len(out)))
    return bytes(out[:out_bytes])


def mk_png4(w: int, h: int, plte: bytes, raw: bytes, path: Path, trns: bytes | None = None) -> None:
    stride = (w + 1) // 2
    raw = (raw + b'\x00' * (h * stride))[:h * stride]
    scan = bytearray()
    p = 0
    for _ in range(h):
        scan.append(0)
        scan += raw[p:p + stride]
        p += stride
    def ch(t: bytes, d: bytes) -> bytes:
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', binascii.crc32(t + d) & 0xFFFFFFFF)
    png = bytearray(b'\x89PNG\r\n\x1a\n')
    png += ch(b'IHDR', struct.pack('>IIBBBBB', w, h, 4, 3, 0, 0, 0))
    png += ch(b'PLTE', plte)
    if trns is not None:
        png += ch(b'tRNS', trns)
    png += ch(b'IDAT', zlib.compress(bytes(scan), 9))
    png += ch(b'IEND', b'')
    path.write_bytes(png)


def mk_png8(w: int, h: int, plte: bytes, raw: bytes, path: Path, trns: bytes | None = None) -> None:
    stride = w
    raw = (raw + b'\x00' * (h * stride))[:h * stride]
    scan = bytearray()
    p = 0
    for _ in range(h):
        scan.append(0)
        scan += raw[p:p + stride]
        p += stride

    def ch(t: bytes, d: bytes) -> bytes:
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', binascii.crc32(t + d) & 0xFFFFFFFF)

    png = bytearray(b'\x89PNG\r\n\x1a\n')
    png += ch(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 3, 0, 0, 0))
    png += ch(b'PLTE', plte)
    if trns is not None:
        png += ch(b'tRNS', trns)
    png += ch(b'IDAT', zlib.compress(bytes(scan), 9))
    png += ch(b'IEND', b'')
    path.write_bytes(png)


def mk_png_t5_4bpp(w: int, h: int, plte: bytes, raw: bytes, path: Path, trns: bytes | None = None) -> None:
    packed = raw[:((w + 1) // 2) * h]
    pixels = [0] * (w * h)
    src_pos = len(packed)
    dst_pos = len(pixels)

    for _ in range(h):
        if w & 1:
            src_pos -= 1
            b = packed[src_pos]
            dst_pos -= 1
            pixels[dst_pos] = (b >> 4) & 0xF

        for _ in range(w >> 1):
            src_pos -= 1
            b = packed[src_pos]
            dst_pos -= 1
            pixels[dst_pos] = b & 0xF
            dst_pos -= 1
            pixels[dst_pos] = (b >> 4) & 0xF

    scan = bytearray()
    idx = 0
    for _ in range(h):
        scan.append(0)
        row = pixels[idx:idx + w]
        idx += w
        scan.extend(row)

    def ch(t: bytes, d: bytes) -> bytes:
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', binascii.crc32(t + d) & 0xFFFFFFFF)

    png = bytearray(b'\x89PNG\r\n\x1a\n')
    png += ch(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 3, 0, 0, 0))
    png += ch(b'PLTE', plte)
    if trns is not None:
        png += ch(b'tRNS', trns)
    png += ch(b'IDAT', zlib.compress(bytes(scan), 9))
    png += ch(b'IEND', b'')
    path.write_bytes(png)


def decode_entry(pay: bytes, out_bytes: int) -> bytes:
    t = pay[0] >> 4 if pay else 0
    if t == 1:
        return decode_type1(pay, out_bytes)
    if t == 3:
        return decode_type3(pay, out_bytes)
    if t == 5:
        return decode_type5(pay, out_bytes)
    return b''

manifest = []
idx = 0
count = 0
while True:
    off = SRC.find(SIG, idx)
    if off < 0:
        break
    idx = off + 1
    p = off + 8
    l1 = struct.unpack('>I', SRC[p:p + 4])[0]; p += 4; p += 4; ih = SRC[p:p + l1]; p += l1
    l2 = struct.unpack('>I', SRC[p:p + 4])[0]; p += 4; p += 4; pl = SRC[p:p + l2]; p += l2
    trns = None
    l3 = struct.unpack('>I', SRC[p:p + 4])[0]; p += 4
    t3 = SRC[p:p + 4]; p += 4
    if t3 == b'tRNS':
        trns = SRC[p:p + l3]
        p += l3
        l3 = struct.unpack('>I', SRC[p:p + 4])[0]; p += 4
        t3 = SRC[p:p + 4]; p += 4
    pay = SRC[p:p + l3]
    if l3 <= 0 or not pay:
        continue
    t = pay[0] >> 4
    if t not in (1, 3, 5):
        continue
    w, h, bd, ct, cm, fm, im = struct.unpack('>IIBBBBB', ih)
    out_bytes = w * h if bd == 8 else ((w + 1) // 2) * h
    raw = decode_entry(pay, out_bytes)
    if not raw:
        continue
    name = f'img_{count:03d}_off_{off:06x}_t{t}_{w}x{h}.png'
    if t == 5 and bd == 4:
        mk_png_t5_4bpp(w, h, pl, raw, OUT / name, trns=trns)
    elif bd == 8:
        mk_png8(w, h, pl, raw, OUT / name, trns=trns)
    else:
        mk_png4(w, h, pl, raw, OUT / name, trns=trns)
    manifest.append((count, off, t, w, h, l3, name))
    count += 1

(Path(OUT / 'manifest.tsv')).write_text('\n'.join(f"{i}\t0x{off:06x}\t{t}\t{w}x{h}\t{ln}\t{nm}" for i, off, t, w, h, ln, nm in manifest) + '\n')
print('rendered', count, '->', OUT)

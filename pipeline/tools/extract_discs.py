"""Extract a PS1 MODE2/2352 BIN (ISO9660) and a GameCube CISO into folders."""
import os, struct, sys


# ---------------- PS1 BIN (MODE2/2352, ISO9660) ----------------
def ps1_extract(bin_path, out_dir):
    f = open(bin_path, "rb")
    SECT = 2352

    def sector(lba):
        f.seek(lba * SECT)
        raw = f.read(SECT)
        submode = raw[18]
        form2 = bool(submode & 0x20)
        return raw[24:24 + (2324 if form2 else 2048)], form2

    def read_extent(lba, size, raw_form2=False):
        out = bytearray()
        n = (size + 2047) // 2048
        for i in range(n):
            data, form2 = sector(lba + i)
            out += data[:2048] if not form2 else data
        return bytes(out[:size]) if not raw_form2 else bytes(out)

    pvd, _ = sector(16)
    assert pvd[1:6] == b"CD001", "not ISO9660"
    root = pvd[156:156 + 34]
    listing = []

    def walk(lba, size, rel):
        data = read_extent(lba, size)
        i = 0
        while i < len(data):
            ln = data[i]
            if ln == 0:
                i = ((i // 2048) + 1) * 2048
                continue
            rec = data[i:i + ln]
            elba = struct.unpack_from("<I", rec, 2)[0]
            esize = struct.unpack_from("<I", rec, 10)[0]
            flags = rec[25]
            nlen = rec[32]
            name = rec[33:33 + nlen]
            i += ln
            if name in (b"\x00", b"\x01"):
                continue
            name = name.decode("ascii", "replace").split(";")[0]
            path = os.path.join(rel, name)
            if flags & 2:
                os.makedirs(os.path.join(out_dir, path), exist_ok=True)
                walk(elba, esize, path)
            else:
                # detect Form2 (XA/STR) files: keep 2336-byte raw for those
                _, form2 = sector(elba)
                if form2:
                    nsec = (esize + 2047) // 2048
                    buf = bytearray()
                    for s in range(nsec):
                        f.seek((elba + s) * SECT + 16)
                        buf += f.read(2336)
                    content = bytes(buf)
                else:
                    content = read_extent(elba, esize)
                with open(os.path.join(out_dir, path), "wb") as o:
                    o.write(content)
                listing.append((path, esize, elba, form2))

    os.makedirs(out_dir, exist_ok=True)
    walk(struct.unpack_from("<I", root, 2)[0], struct.unpack_from("<I", root, 10)[0], "")
    return listing


# ---------------- GameCube CISO ----------------
class Ciso:
    def __init__(self, path):
        self.f = open(path, "rb")
        hdr = self.f.read(0x8000)
        assert hdr[:4] == b"CISO"
        self.bs = struct.unpack_from("<I", hdr, 4)[0]
        self.index = {}
        pos = 0
        for blk, present in enumerate(hdr[8:0x8000]):
            if present:
                self.index[blk] = pos
                pos += 1

    def read(self, off, size):
        out = bytearray()
        while size > 0:
            blk, inner = divmod(off, self.bs)
            n = min(size, self.bs - inner)
            if blk in self.index:
                self.f.seek(0x8000 + self.index[blk] * self.bs + inner)
                out += self.f.read(n)
            else:
                out += b"\x00" * n
            off += n
            size -= n
        return bytes(out)


def gc_extract(ciso_path, out_dir):
    d = Ciso(ciso_path)
    boot = d.read(0, 0x440)
    game_id = boot[:6].decode()
    dol_off, fst_off, fst_size = struct.unpack_from(">III", boot, 0x420)
    os.makedirs(os.path.join(out_dir, "sys"), exist_ok=True)
    open(os.path.join(out_dir, "sys", "boot.bin"), "wb").write(boot)
    open(os.path.join(out_dir, "sys", "bi2.bin"), "wb").write(d.read(0x440, 0x2000))
    open(os.path.join(out_dir, "sys", "fst.bin"), "wb").write(d.read(fst_off, fst_size))
    # DOL size from header
    dh = d.read(dol_off, 0x100)
    end = 0
    for i in range(18):
        o = struct.unpack_from(">I", dh, i * 4)[0]
        s = struct.unpack_from(">I", dh, 0x90 + i * 4)[0]
        end = max(end, o + s)
    open(os.path.join(out_dir, "sys", "main.dol"), "wb").write(d.read(dol_off, end))

    fst = d.read(fst_off, fst_size)
    n = struct.unpack_from(">I", fst, 8)[0]
    str_base = n * 12
    listing = []

    def name_at(o):
        e = fst.index(b"\x00", str_base + o)
        return fst[str_base + o:e].decode("shift_jis", "replace")

    def walk(start, end, rel):
        i = start
        while i < end:
            w0, a, b = struct.unpack_from(">III", fst, i * 12)
            is_dir = w0 >> 24
            nm = name_at(w0 & 0xFFFFFF)
            p = os.path.join(rel, nm)
            if is_dir:
                os.makedirs(os.path.join(out_dir, "files", p), exist_ok=True)
                walk(i + 1, b, p)
                i = b
            else:
                with open(os.path.join(out_dir, "files", p), "wb") as o:
                    o.write(d.read(a, b))
                listing.append((p, b))
                i += 1

    os.makedirs(os.path.join(out_dir, "files"), exist_ok=True)
    walk(1, n, "")
    return game_id, listing


if __name__ == "__main__":
    kind, src, dst = sys.argv[1:4]
    if kind == "ps1":
        lst = ps1_extract(src, dst)
        print("files:", len(lst), "form2:", sum(1 for x in lst if x[3]))
        for p, s, l, f2 in lst:
            print(f"{s:>12} {'XA ' if f2 else '   '}{p}")
    else:
        gid, lst = gc_extract(src, dst)
        print("game id:", gid, "files:", len(lst), "bytes:", sum(s for _, s in lst))

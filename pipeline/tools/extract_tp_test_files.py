"""Read only the two test-stage archives from an unmodified GameCube ISO/CISO.
This utility never writes to the source disc image.
"""
from pathlib import Path
import struct, sys

image = Path(sys.argv[1])
out = Path(sys.argv[2])
with image.open('rb') as f:
    header = f.read(0x8000)
    compressed = header[:4] == b'CISO'
    if compressed:
        block_size = struct.unpack_from('<I', header, 4)[0]
        assert block_size and block_size <= 0x8000000
        offsets = []
        count = 0
        for flag in header[8:]:
            offsets.append(0x8000 + count*block_size if flag else None)
            count += bool(flag)
    def read_at(offset, length):
        if not compressed:
            f.seek(offset)
            data = f.read(length)
            assert len(data) == length
            return data
        result = bytearray()
        while length:
            block, within = divmod(offset, block_size)
            take = min(length, block_size-within)
            mapped = offsets[block]
            if mapped is None:
                result.extend(bytes(take))
            else:
                f.seek(mapped+within)
                data = f.read(take)
                assert len(data) == take, 'Truncated CISO'
                result.extend(data)
            offset += take
            length -= take
        return bytes(result)
    assert read_at(0, 8) == b'GZ2E01\0\0', 'Expected USA GameCube revision 0'
    fst_at, fst_size = struct.unpack('>II', read_at(0x424, 8))
    fst = read_at(fst_at, fst_size)
    count = struct.unpack_from('>I', fst, 8)[0]
    strings = 12*count
    wanted = {'res/Stage/R_SP108/STG_00.arc', 'res/Stage/R_SP108/R00_00.arc'}
    dirs = [(count, '')]
    found = set()
    for i in range(1, count):
        while i >= dirs[-1][0]: dirs.pop()
        name_word, at, size = struct.unpack_from('>III', fst, i*12)
        name_at = strings+(name_word & 0xffffff)
        name = fst[name_at:fst.index(0, name_at)].decode('ascii')
        path = dirs[-1][1]+name
        if name_word >> 24:
            dirs.append((size, path+'/'))
        elif path in wanted:
            target = out/path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(read_at(at, size))
            found.add(path)
            print(path, size)
    assert found == wanted, 'Missing test-stage archives'

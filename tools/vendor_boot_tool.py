#!/usr/bin/env python3
"""
vendor_boot_tool.py — work with Android boot header v4 vendor_boot images.

Commands:
  info    <vendor_boot.img>
          Print header fields and the vendor ramdisk table.
  extract <vendor_boot.img> <out_dir>
          Dump every vendor ramdisk fragment (still compressed) + dtb.
  inject  <stock_vendor_boot.img> <recovery_fragment_or_image> <out.img>
          Replace ONLY the fragment of type RECOVERY in the stock image.
          The second argument may be a raw fragment (lz4/gzip cpio) or a whole
          vendor_boot.img produced by the OrangeFox build; in that case its
          RECOVERY fragment is taken. Everything else (header, platform
          ramdisk, dtb, bootconfig, cmdline, addresses) is copied from stock.

Written for OSCAL TANK 1 (MT6877), but generic for header v4.
"""
import struct
import sys
import os

HDR_FMT_HEAD = '<8sIIIII'   # magic, version, page_size, kernel_addr, ramdisk_addr, vendor_ramdisk_size
TYPES = {0: 'NONE', 1: 'PLATFORM', 2: 'RECOVERY', 3: 'DLKM'}
RECOVERY = 2


def align(x, a):
    return (x + a - 1) // a * a


class VendorBoot:
    def __init__(self, data):
        if data[:8] != b'VNDRBOOT':
            raise ValueError('not a vendor_boot image (magic %r)' % data[:8])
        (self.magic, self.version, self.page_size, self.kernel_addr,
         self.ramdisk_addr, self.vendor_ramdisk_size) = struct.unpack_from(HDR_FMT_HEAD, data, 0)
        if self.version < 4:
            raise ValueError('header v%d not supported (need v4)' % self.version)
        self.cmdline = data[28:28 + 2048]
        self.tags_addr, = struct.unpack_from('<I', data, 2076)
        self.name = data[2080:2096]
        self.header_size, self.dtb_size = struct.unpack_from('<II', data, 2096)
        self.dtb_addr, = struct.unpack_from('<Q', data, 2104)
        (self.table_size, self.table_num, self.table_entry_size,
         self.bootconfig_size) = struct.unpack_from('<4I', data, 2112)
        self.header = data[:self.header_size]
        pg = self.page_size
        o_rd = align(self.header_size, pg)
        o_dtb = o_rd + align(self.vendor_ramdisk_size, pg)
        o_tbl = o_dtb + align(self.dtb_size, pg)
        o_bc = o_tbl + align(self.table_size, pg)
        self.payload_end = o_bc + align(self.bootconfig_size, pg)
        rd = data[o_rd:o_rd + self.vendor_ramdisk_size]
        self.dtb = data[o_dtb:o_dtb + self.dtb_size]
        self.bootconfig = data[o_bc:o_bc + self.bootconfig_size]
        self.entries = []
        for i in range(self.table_num):
            e = data[o_tbl + i * self.table_entry_size: o_tbl + (i + 1) * self.table_entry_size]
            size, off, typ = struct.unpack_from('<3I', e, 0)
            self.entries.append({'size': size, 'offset': off, 'type': typ,
                                 'rest': e[12:], 'data': rd[off:off + size]})

    def info(self):
        print('header v%d, page %d, header_size %d' % (self.version, self.page_size, self.header_size))
        print('kernel_addr 0x%x ramdisk_addr 0x%x tags_addr 0x%x dtb_addr 0x%x' %
              (self.kernel_addr, self.ramdisk_addr, self.tags_addr, self.dtb_addr))
        print('cmdline: %s' % self.cmdline.split(b'\0')[0].decode(errors='replace'))
        print('vendor_ramdisk_size %d, dtb %d, bootconfig %d, payload %d bytes' %
              (self.vendor_ramdisk_size, self.dtb_size, self.bootconfig_size, self.payload_end))
        for i, e in enumerate(self.entries):
            name = e['rest'][:32].split(b'\0')[0].decode(errors='replace')
            print('  [%d] %-8s name=%-10r size=%d offset=%d magic=%s' %
                  (i, TYPES.get(e['type'], e['type']), name, e['size'], e['offset'], e['data'][:4].hex()))

    def build(self):
        pg = self.page_size
        rd = b''
        tbl = b''
        for e in self.entries:
            off = len(rd)
            rd += e['data']
            tbl += struct.pack('<3I', len(e['data']), off, e['type']) + e['rest']
        hdr = bytearray(self.header)
        struct.pack_into('<I', hdr, 24, len(rd))          # vendor_ramdisk_size
        struct.pack_into('<I', hdr, 2112, len(tbl))       # vendor_ramdisk_table_size
        out = bytearray()
        for blob in (bytes(hdr), rd, self.dtb, tbl, self.bootconfig):
            out += blob
            out += b'\0' * (align(len(blob), pg) - len(blob))
        return bytes(out)


def load(path):
    with open(path, 'rb') as f:
        return f.read()


def recovery_fragment(path):
    data = load(path)
    if data[:8] == b'VNDRBOOT':
        vb = VendorBoot(data)
        recs = [e for e in vb.entries if e['type'] == RECOVERY]
        if len(recs) != 1:
            # Some builds put recovery into a single platform-less ramdisk;
            # fall back to the last fragment.
            if not vb.entries:
                raise SystemExit('built image has no ramdisk fragments')
            print('warning: built image has %d RECOVERY fragments, using the last fragment' % len(recs))
            return vb.entries[-1]['data']
        return recs[0]['data']
    return data


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == 'info':
        VendorBoot(load(sys.argv[2])).info()
    elif cmd == 'extract':
        vb = VendorBoot(load(sys.argv[2]))
        out = sys.argv[3]
        os.makedirs(out, exist_ok=True)
        for i, e in enumerate(vb.entries):
            name = e['rest'][:32].split(b'\0')[0].decode() or 'noname'
            fn = os.path.join(out, '%d_%s_%s.ramdisk' % (i, TYPES.get(e['type'], e['type']), name))
            open(fn, 'wb').write(e['data'])
            print(fn)
        open(os.path.join(out, 'dtb'), 'wb').write(vb.dtb)
    elif cmd == 'inject':
        stock_path, frag_path, out_path = sys.argv[2:5]
        stock_data = load(stock_path)
        vb = VendorBoot(stock_data)
        recs = [e for e in vb.entries if e['type'] == RECOVERY]
        if len(recs) != 1:
            raise SystemExit('stock image must have exactly one RECOVERY fragment, found %d' % len(recs))
        platform_before = [e['data'] for e in vb.entries if e['type'] != RECOVERY]
        new = recovery_fragment(frag_path)
        old_size = len(recs[0]['data'])
        recs[0]['data'] = new
        img = vb.build()
        # safety checks: re-parse and verify every non-recovery part is byte-identical
        chk = VendorBoot(img)
        assert [e['data'] for e in chk.entries if e['type'] != RECOVERY] == platform_before, 'platform ramdisk changed!'
        assert [e['data'] for e in chk.entries if e['type'] == RECOVERY] == [new], 'recovery fragment mismatch'
        assert chk.dtb == vb.dtb and chk.bootconfig == vb.bootconfig, 'dtb/bootconfig changed'
        assert chk.cmdline == vb.cmdline and chk.kernel_addr == vb.kernel_addr and chk.ramdisk_addr == vb.ramdisk_addr
        part_size = int(os.environ.get('VENDOR_BOOT_PARTITION_SIZE', '68157440'))
        if len(img) > part_size:
            raise SystemExit('result %d bytes does not fit vendor_boot partition (%d)' % (len(img), part_size))
        open(out_path, 'wb').write(img)
        print('OK: %s (%d bytes, recovery fragment %d -> %d bytes, %d%% of partition)' %
              (out_path, len(img), old_size, len(new), 100 * len(img) // part_size))
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()

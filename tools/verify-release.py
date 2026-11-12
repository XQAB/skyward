#!/usr/bin/env python3
"""Check a built recovery image against what a release has to hold.

The packer puts a ramdisk-only boot image together from the phone's own stock
recovery, the Skyward binary, and the vendor files a device keeps in
``<codename>_extra/``. Everything that has to be in it is put there in code or
copied from that folder, and a build that quietly lost a piece of it still
flashes and still boots — into a recovery whose MTP page is empty, or whose
se_omapi cannot find a library. This reads the image back the way the phone's
bootloader does and says which pieces are there:

* the boot header is the ramdisk-only layout — the stock recovery's version 3
  or 4 header, with no kernel in it;
* the ramdisk is one LZ4 legacy stream, the framing the kernel's initramfs
  unpacker reads, holding a newc archive;
* every file under ``<codename>_extra/`` is in that archive, with the mode the
  packer gives it;
* ``system/bin/{7za,zstd,unzip,avbctl,resetprop}`` are links to ``recovery``,
  which is how install scripts find the commands a stock recovery lacks;
* the recovery binary says which version it is, ``Skyward <version>``;
* ``prop.default`` names the stock build the image was made on, and the
  properties the packer sets (and the ones it takes out) are as expected.

It needs no tool but python: the LZ4 block decoder is written out here, so a
runner without ``lz4`` checks the same thing the kernel will do.

Usage:
    tools/verify-release.py out/skyward-<version>-<codename>-<stock>.img \\
        --config devices/<codename>.toml [--extra <codename>_extra] \\
        [--version <version>] [--report out/<name>.verify.txt]

The exit status is 1 when a check fails, 0 otherwise. Warnings are printed and
kept in the report but do not fail the build.
"""

import argparse
import re
import struct
import sys
import tomllib
from pathlib import Path, PurePosixPath

PAGE = 4096
ANDROID_MAGIC = b"ANDROID!"
AVB_MAGIC = b"AVBf"
# The legacy LZ4 framing's magic number, 0x184C2102 little endian.
LZ4_LEGACY_MAGIC = b"\x02\x21\x4c\x18"
NEWC_MAGIC = b"070701"

S_IFMT = 0o170000
S_IFREG = 0o100000
S_IFDIR = 0o040000
S_IFLNK = 0o120000

RECOVERY = "system/bin/recovery"
PROP_DEFAULT = "prop.default"
# What the packer puts in besides the device's own extra files: the first
# program of the system installed beside this one, the phone's configuration,
# the two typefaces, logd's scheduling profiles and file transfer's init rules.
PACKED = [
    "skyward/system-init",
    "skyward/device.toml",
    "skyward/MiSansVF.ttf",
    "skyward/KirkMono-Regular.ttf",
    "system/etc/task_profiles.json",
    "system/etc/init/skyward-mtp.rc",
]
# Every command a stock recovery lacks, as links to the recovery binary, each
# started as the name it is linked under (crates/skyward-config/src/lib.rs,
# ramdisk::COMMANDS).
COMMANDS = ["7za", "avbctl", "resetprop", "unzip", "zstd"]
# The properties the packer sets on a recovery: adbd keeps root, lets any
# computer in, and update_engine accepts a package built before this recovery.
SET_PROPS = ["ro.secure=0", "ro.adb.secure=0", "ro.debuggable=1", "ro.ota.allow_downgrade=true"]
# The properties it takes out, so that the recovery fills them in from the
# installed system instead of claiming the stock build's levels.
STRIPPED_PROPS = ["ro.build.version.release", "ro.build.version.security_patch", "ro.vendor.build.security_patch"]


class Check:
    """One thing the image is looked for, and what came of looking."""

    def __init__(self, name, status, detail):
        self.name = name
        self.status = status
        self.detail = detail

    def line(self):
        return f"{self.status:4}  {self.name}: {self.detail}"


class Report:
    def __init__(self):
        self.checks = []

    def ok(self, name, detail=""):
        self.checks.append(Check(name, "ok", detail))

    def warn(self, name, detail):
        self.checks.append(Check(name, "warn", detail))

    def fail(self, name, detail):
        self.checks.append(Check(name, "FAIL", detail))

    def failed(self):
        return [c for c in self.checks if c.status == "FAIL"]

    def text(self):
        counts = {s: sum(1 for c in self.checks if c.status == s) for s in ("ok", "warn", "FAIL")}
        lines = [c.line() for c in self.checks]
        lines.append("")
        lines.append(f"{counts['ok']} passed, {counts['warn']} warnings, {counts['FAIL']} failed")
        return "\n".join(lines)


def lz4_block(src):
    """Unpack one LZ4 block, as lib/lz4 in the kernel does."""
    dst = bytearray()
    i, n = 0, len(src)
    while i < n:
        token = src[i]
        i += 1
        literals = token >> 4
        if literals == 15:
            while True:
                b = src[i]
                i += 1
                literals += b
                if b != 255:
                    break
        dst += src[i : i + literals]
        i += literals
        if i >= n:
            # The last sequence of a block may hold literals alone.
            break
        offset = src[i] | (src[i + 1] << 8)
        i += 2
        if offset == 0 or offset > len(dst):
            raise ValueError(f"a match at {i} reaches back {offset} bytes, past the {len(dst)} unpacked")
        length = token & 15
        if length == 15:
            while True:
                b = src[i]
                i += 1
                length += b
                if b != 255:
                    break
        length += 4
        at = len(dst) - offset
        for k in range(length):
            dst.append(dst[at + k])
    return bytes(dst)


def lz4_legacy(data):
    """Unpack an LZ4 legacy stream: the magic, then each block with its length before it."""
    if data[:4] != LZ4_LEGACY_MAGIC:
        raise ValueError(f"starts {data[:4].hex()}, not LZ4 legacy's 02214c18")
    out = bytearray()
    i = 4
    while i < len(data):
        if i + 4 > len(data):
            raise ValueError("the last block has no length before it")
        size = struct.unpack_from("<I", data, i)[0]
        i += 4
        # A block stored as it is has the top bit set, as the kernel reads it.
        stored = bool(size & 0x8000_0000)
        size &= 0x7FFF_FFFF
        block = data[i : i + size]
        if len(block) != size:
            raise ValueError(f"a block at {i} runs {size} bytes past the stream")
        i += size
        out += block if stored else lz4_block(block)
    return bytes(out)


class Entry:
    def __init__(self, name, mode, data):
        self.name = name
        self.mode = mode
        self.data = data

    def is_link(self):
        return self.mode & S_IFMT == S_IFLNK

    def is_file(self):
        return self.mode & S_IFMT == S_IFREG


def newc_entries(archive):
    """Every entry of a newc archive, its name, mode and data."""
    entries = []
    i = 0
    while True:
        if archive[i : i + 6] != NEWC_MAGIC:
            raise ValueError(f"no newc header at {i}")
        # The fields are hex text, eight characters each.
        fields = [int(archive[i + 6 + 8 * k : i + 14 + 8 * k], 16) for k in range(13)]
        mode, _, _, _, _, size, _, _, _, _, namesize, _ = fields[1:]
        name_at = i + 110
        name = archive[name_at : name_at + namesize - 1].decode("utf-8", "replace")
        i = (name_at + namesize + 3) & ~3
        data = archive[i : i + size]
        i = (i + size + 3) & ~3
        if name == "TRAILER!!!":
            return entries
        entries.append(Entry(name, mode, data))
        if i >= len(archive):
            raise ValueError("the archive ends before its trailer")


def elf_needed(data):
    """The libraries an ELF object asks for by name, or None when it is no ELF."""
    if len(data) < 64 or data[:4] != b"\x7fELF":
        return None
    # Only what a phone's recovery carries: 64-bit, little endian.
    if data[4] != 2 or data[5] != 1:
        return None
    shoff = struct.unpack_from("<Q", data, 0x28)[0]
    shentsize, shnum, _ = struct.unpack_from("<HHH", data, 0x3A)
    sections = []
    for k in range(shnum):
        at = shoff + k * shentsize
        sh_type = struct.unpack_from("<I", data, at + 4)[0]
        sh_offset = struct.unpack_from("<Q", data, at + 0x18)[0]
        sh_size = struct.unpack_from("<Q", data, at + 0x20)[0]
        sh_link = struct.unpack_from("<I", data, at + 0x28)[0]
        sections.append((sh_type, sh_offset, sh_size, sh_link))
    for sh_type, sh_offset, sh_size, sh_link in sections:
        if sh_type != 6:  # SHT_DYNAMIC
            continue
        _, str_offset, str_size, _ = sections[sh_link]
        needed = []
        for k in range(0, sh_size, 16):
            tag, value = struct.unpack_from("<qQ", data, sh_offset + k)
            if tag == 0:  # DT_NULL
                break
            if tag == 1:  # DT_NEEDED
                raw = data[str_offset + value : str_offset + str_size]
                needed.append(raw.split(b"\0")[0].decode("utf-8", "replace"))
        return needed
    return None


def prop_file(text):
    """A property file's entries, keeping the last of a name, as init does."""
    props = {}
    for line in text.splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        props[name.strip()] = value.strip()
    return props


def extra_manifest(directory):
    """Every file under `directory`, named as the recovery's root names it."""
    files = []
    for path in sorted(Path(directory).rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        files.append((PurePosixPath(*path.relative_to(directory).parts).as_posix(), path))
    return files


def mode_for(name):
    """The mode the packer gives a file it copies in: a program runnable, everything else readable."""
    if name.startswith("system/bin/") or name.startswith("system/xbin/"):
        return S_IFREG | 0o755
    return S_IFREG | 0o644


def version_of(manifest):
    """The version in the workspace's Cargo.toml, as the recovery compiles it in."""
    text = Path(manifest).read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', text, re.MULTILINE)
    return match.group(1) if match else None


def same_build(prop, stock):
    """Whether a property names the stock build the device file does.

    A package's version carries the channel it was made for at its end — ``XM``
    for China — and the stock recovery's prop.default leaves that off.
    """
    if prop == stock:
        return True
    rest = stock[len(prop) :]
    return len(rest) == 2 and stock.startswith(prop) and rest.isalpha()


MIUI_VERSION = re.compile(r"^OS(\d+)\.(\d+)\.(\d+)\.(\d+)\.([A-Z0-9]+)CN(?:[A-Z]+)?$")


def same_line(prop, stock):
    """Whether two versions are one device's line: the same OS and channel.

    A stock package can hold a recovery built before the package it ships in —
    several do — so the property's last number may be older than the package's
    while still naming the same phone and the same OS.
    """
    a, b = MIUI_VERSION.match(prop), MIUI_VERSION.match(stock)
    if not a or not b:
        return False
    return a[1] == b[1] and a[2] == b[2] and a[5] == b[5]


def verify(image, config, extra, version, manifest):
    report = Report()
    device = Path(config).stem
    settings = tomllib.loads(Path(config).read_text(encoding="utf-8"))
    stock = settings.get("stock", {}).get("version")
    codename = settings.get("device", {}).get("codename", device)

    data = Path(image).read_bytes()
    report.ok("image size", f"{len(data)} bytes")

    # The boot header. The packer keeps the stock recovery's header, sizes
    # aside, so the version is the one that phone ships with: 4 on the builds
    # whose recovery holds nothing but its ramdisk, which is what these are.
    if data[:8] != ANDROID_MAGIC:
        report.fail("boot header magic", f"starts {data[:8]!r}, not ANDROID!")
        return report
    kernel_size, ramdisk_size, _, header_size = struct.unpack_from("<4I", data, 8)
    header_version = struct.unpack_from("<I", data, 40)[0]
    if header_version not in (3, 4):
        report.fail("boot header", f"version {header_version}, and a recovery is built on 3 or 4")
    else:
        report.ok("boot header", f"version {header_version}, header {header_size} bytes")
    if kernel_size == 0:
        report.ok("kernel size", "no kernel: the recovery is the ramdisk alone")
    elif header_version == 4:
        report.fail("kernel size", f"{kernel_size} bytes, and a version 4 recovery carries no kernel")
    else:
        report.warn("kernel size", f"{kernel_size} bytes, kept from the stock recovery")
    ramdisk_at = PAGE + -(-kernel_size // PAGE) * PAGE
    ramdisk = data[ramdisk_at : ramdisk_at + ramdisk_size]
    if ramdisk_size == 0 or len(ramdisk) != ramdisk_size:
        report.fail("ramdisk", f"{ramdisk_size} bytes named, {len(ramdisk)} in the image")
        return report
    report.ok("ramdisk", f"{len(ramdisk)} bytes at {ramdisk_at}")

    # The unsigned AVB footer the image ends in: what the bootloader reads the
    # partition's size and hash from.
    if len(data) < 64 or data[-64:-60] != AVB_MAGIC:
        report.fail("AVB footer", "the image does not end in an AVB footer")
    else:
        report.ok("AVB footer", "the image ends in AVBf")

    try:
        archive = lz4_legacy(ramdisk)
    except ValueError as e:
        report.fail("ramdisk unpacking", str(e))
        return report
    report.ok("ramdisk unpacking", f"LZ4 legacy, {len(archive)} bytes unpacked")

    try:
        entries = newc_entries(archive)
    except ValueError as e:
        report.fail("cpio archive", str(e))
        return report
    report.ok("cpio archive", f"{len(entries)} entries")
    by_name = {e.name: e for e in entries}

    # The recovery itself, and the Pan-OS pieces the packer puts in.
    if RECOVERY not in by_name:
        report.fail("recovery binary", f"{RECOVERY} is not in the ramdisk")
    else:
        report.ok("recovery binary", f"{RECOVERY}, {len(by_name[RECOVERY].data)} bytes")
    for name in PACKED:
        if name in by_name:
            report.ok("packed file", f"{name}, {len(by_name[name].data)} bytes")
        else:
            report.fail("packed file", f"{name} is not in the ramdisk")

    # Install scripts find the commands a stock recovery lacks by these names,
    # and each is the recovery binary started as that name.
    for command in COMMANDS:
        name = f"system/bin/{command}"
        entry = by_name.get(name)
        if entry is None:
            report.fail("command link", f"{name} is not in the ramdisk")
        elif not entry.is_link():
            report.fail("command link", f"{name} is a file, not a link")
        elif entry.data != b"recovery":
            report.fail("command link", f"{name} points to {entry.data!r}, not to recovery")
        else:
            report.ok("command link", f"{name} → recovery")

    # Every vendor file the device carries, under the name the recovery's root
    # gives it: a program in system/bin is runnable, anything else readable.
    files = extra_manifest(extra) if extra else []
    report.ok("extra manifest", f"{len(files)} files under {extra}" if extra else "no extra folder")
    for name, path in files:
        entry = by_name.get(name)
        if entry is None:
            report.fail("extra file", f"{name} is not in the ramdisk")
            continue
        if not entry.is_file():
            report.fail("extra file", f"{name} is not a regular file in the ramdisk")
            continue
        if len(entry.data) != path.stat().st_size:
            report.fail("extra file", f"{name} holds {len(entry.data)} bytes, the one on disk is {path.stat().st_size}")
            continue
        want = mode_for(name)
        if entry.mode != want:
            report.warn("extra file", f"{name} is {entry.mode:06o}, which is not {want:06o}")
        else:
            report.ok("extra file", f"{name}, {len(entry.data)} bytes")

    # The libraries those vendor programs ask for by name: a missing one is the
    # bug this check is here for, but a phone may resolve one outside the
    # ramdisk, so it is reported and does not stop the build.
    wanted = []
    for name, path in files:
        needed = elf_needed(path.read_bytes()) or []
        for library in needed:
            if library in wanted:
                continue
            present = [n for n in (f"system/lib64/{library}", f"system/lib/{library}", f"vendor/lib64/{library}", f"odm/lib64/{library}") if n in by_name]
            if present:
                report.ok("requested library", f"{library} ({name} asks for it) is {present[0]}")
            else:
                wanted.append(library)
                report.warn("requested library", f"{name} asks for {library}, which is not in the ramdisk")

    # The phone's configuration travels with the image, and has to be its own.
    config_file = by_name.get("skyward/device.toml")
    if config_file is not None:
        try:
            inside = tomllib.loads(config_file.data.decode("utf-8"))
            name = inside.get("device", {}).get("codename")
        except (UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
            name = None
            report.fail("device config", f"skyward/device.toml does not parse: {e}")
        if name is not None:
            if name == codename:
                report.ok("device config", f"{codename}, as devices/{device}.toml names it")
            else:
                report.fail("device config", f"skyward/device.toml is for {name}, the image was built for {codename}")

    # Which version the binary says it is, as About shows it and as the phone
    # names the release it asks for next.
    versions = [version] if version else []
    compiled = version_of(manifest)
    if compiled and compiled not in versions:
        versions.append(compiled)
    binary = by_name.get(RECOVERY)
    if binary is not None:
        found = [v for v in versions if f"Skyward {v}".encode() in binary.data]
        if not versions:
            report.warn("version string", "no version to look for; give --version or run from the repository")
        elif found:
            report.ok("version string", f"the binary says Skyward {found[0]}")
        else:
            report.fail("version string", f"the binary says none of {', '.join('Skyward ' + v for v in versions)}")

    # prop.default: the stock build the image was made on, the properties the
    # packer sets, and the ones it takes out for the recovery to fill in later.
    props_entry = by_name.get(PROP_DEFAULT)
    if props_entry is None:
        report.fail("prop.default", f"{PROP_DEFAULT} is not in the ramdisk")
    else:
        try:
            props = prop_file(props_entry.data.decode("utf-8", "replace"))
        except UnicodeDecodeError as e:
            props = {}
            report.fail("prop.default", f"does not read as text: {e}")
        if props:
            # The build the image was made on, under whichever name the stock
            # recovery gives it: AOSP's own, or the one MIUI versions a system
            # by, which is the one the phone's pages read.
            names = ["ro.build.version.incremental", "ro.mi.os.version.incremental"]
            own = settings.get("device", {}).get("os_version_prop")
            if own and own not in names:
                names.insert(0, own)
            named = {n: props[n] for n in names if n in props}
            if stock is None:
                report.warn("prop.default build", "the configuration names no [stock].version to compare with")
            elif named:
                build = next((n for n, v in named.items() if same_build(v, stock)), None)
                if build:
                    report.ok("prop.default build", f"{build}={named[build]}, the stock build [stock].version names")
                elif any(same_line(v, stock) for v in named.values()):
                    name, version = next((n, v) for n, v in named.items() if same_line(v, stock))
                    report.warn(
                        "prop.default build",
                        f"{name}={version} on the same line as [stock].version {stock}: the recovery in that "
                        "package is built before the package, so its own build is the older one",
                    )
                else:
                    report.fail("prop.default build", f"{named} where [stock].version is {stock}")
            else:
                report.warn("prop.default build", f"none of {', '.join(names)} is set")
            for line in SET_PROPS:
                name, value = line.split("=", 1)
                if props.get(name) == value:
                    report.ok("prop.default setting", line)
                else:
                    report.fail("prop.default setting", f"{name}={props.get(name)}, and the packer sets {value}")
            for name in STRIPPED_PROPS:
                if name in props:
                    report.fail("prop.default stripped", f"{name} is still set to {props[name]}, and the recovery fills it in from the installed system")
                else:
                    report.ok("prop.default stripped", f"{name} is left out")
    return report


def main():
    parser = argparse.ArgumentParser(description="Check a built recovery image against what a release has to hold.")
    parser.add_argument("image", help="the built image, the whole partition")
    parser.add_argument("--config", required=True, help="devices/<codename>.toml the image was built for")
    parser.add_argument("--extra", help="the folder the vendor files came from, <codename>_extra")
    parser.add_argument("--version", help="the version the binary should say it is; taken from Cargo.toml otherwise")
    parser.add_argument("--manifest", default="Cargo.toml", help="where to read the version from when --version is not given")
    parser.add_argument("--report", help="write the report here as well as printing it")
    args = parser.parse_args()

    report = verify(args.image, args.config, args.extra, args.version, args.manifest)
    text = report.text()
    print(text)
    if args.report:
        Path(args.report).write_text(text + "\n", encoding="utf-8")
    return 1 if report.failed() else 0


if __name__ == "__main__":
    sys.exit(main())

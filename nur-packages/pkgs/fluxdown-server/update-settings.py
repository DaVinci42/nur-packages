import argparse
import difflib
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

SOURCES = ["native/protocol/src/daemon_config.rs", "native/protocol/src/rpc.rs"]


def parse_fields(source):
    source = re.sub(r"//[^\n]*", "", source)
    enums = {
        name: json.loads("[" + values + "]")
        for name, values in re.findall(
            r"pub const (\w+): &\[&str\] = &\[([^\]]*)\];", source
        )
    }
    catalog = (
        source.split("pub const DAEMON_CONFIG_FIELDS:", 1)[1]
        .split("= &[", 1)[1]
        .split("];", 1)[0]
    )
    pattern = re.compile(
        r'\s*field\(\s*("[^"\\]*")\s*,\s*DaemonConfigKind::'
        r"(Bool|Integer|Float|Enum|Text|ReadOnly)\s*"
        r'(\{[^}]*\}|\([^)]*\))?\s*,\s*("[^"\\]*")\s*,?\s*\)\s*,?'
    )
    fields = {}
    while catalog.strip():
        match = pattern.match(catalog)
        if match is None:
            raise ValueError("Unrecognized upstream configuration syntax")
        key, kind, constraints, default = match.groups()
        key = json.loads(key)
        if key in fields:
            raise ValueError("Duplicate upstream key: " + key)
        field = {"kind": kind, "default": json.loads(default)}
        if kind in ("Integer", "Float"):
            for part in constraints.strip("{} ").split(","):
                if part.strip():
                    name, value = part.strip().split(":", 1)
                    value = value.strip().replace("_", "")
                    field[name] = (
                        (2**63 - 1) if value == "i64::MAX" else json.loads(value)
                    )
        elif kind == "Enum":
            field["values"] = enums[constraints.strip("() ")]
        fields[key] = field
        catalog = catalog[match.end() :]
    if not fields:
        raise ValueError("Empty upstream configuration catalog")
    return fields


def generate(ref):
    sources = {
        path: subprocess.check_output(
            [
                "gh",
                "api",
                f"repos/zerx-lab/FluxDown/contents/{path}?ref={ref}",
                "-H",
                "Accept: application/vnd.github.raw+json",
            ],
            text=True,
        )
        for path in SOURCES
    }
    protocol = re.search(
        r"pub const PROTOCOL_VERSION: u32 = (\d+);", sources[SOURCES[1]]
    )
    if protocol is None:
        raise ValueError("Cannot determine upstream RPC protocol version")
    return {
        "version": ref.removeprefix("v"),
        "protocolVersion": int(protocol.group(1)),
        "sourceHashes": {
            path: hashlib.sha256(text.encode()).hexdigest()
            for path, text in sources.items()
        },
        "fields": parse_fields(sources[SOURCES[0]]),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate or check the pinned FluxDown daemon configuration contract"
    )
    parser.add_argument(
        "--ref", help="Upstream tag or revision; defaults to the package version"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail on upstream contract drift without modifying files",
    )
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    version = re.search(
        r'version = "([^"]+)";', (folder / "default.nix").read_text()
    ).group(1)
    content = (
        json.dumps(generate(args.ref or "v" + version), indent=2, sort_keys=True) + "\n"
    )
    target = folder / "settings-schema.json"
    if args.check:
        previous = target.read_text()
        if previous != content:
            sys.stdout.writelines(
                difflib.unified_diff(
                    previous.splitlines(True),
                    content.splitlines(True),
                    fromfile="recorded",
                    tofile="upstream",
                )
            )
            return 1
        print("Upstream daemon configuration contract matches")
    else:
        target.write_text(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())

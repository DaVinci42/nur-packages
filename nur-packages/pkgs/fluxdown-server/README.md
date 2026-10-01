# FluxDown Server

Pinned upstream binaries for `x86_64-linux` and `aarch64-linux`, including
`fluxdown-agent`, `fluxdownd`, and the embedded Web UI, but not the desktop GUI.

## Usage

Run commands from the repository root. Adjust the import path to your configuration:

```sh
nix-build ./nur-packages -A fluxdown-server --no-out-link
```

```nix
{
  imports = [ ./nur-packages/modules/fluxdown.nix ];
  services.fluxdown = {
    enable = true;
    environmentFile = "/run/secrets/fluxdown.env";
    environment.FLUXDOWN_LANG = "en";
  };
}
```

Defaults: `127.0.0.1:17800`, user `fluxdown`, state `/var/lib/fluxdown`, downloads
in its `downloads` subdirectory. Analytics and mDNS are disabled.

The optional environment file may contain `FLUXDOWN_TOKEN=<access-key>`; keep it
outside the Nix store with mode `0600`. Keys need 8 to 128 visible ASCII characters,
including letters and digits. Without a key, the Web UI opens first-run setup.
There is no Web username or LAN authentication bypass.

For LAN access, set `listenAddress = "0.0.0.0"; openFirewall = true;`.
This opens the port globally, not just to LAN clients. Initialize authentication
before exposure; use HTTPS and WebSocket forwarding for remote access.
Use brackets for IPv6 addresses, such as `[::1]`.

## Configuration

The module exposes `enable`, `package`, `listenAddress`, `port`, `openFirewall`,
`environment`, and `environmentFile`. Additional startup settings:

| Variable | Purpose |
| --- | --- |
| `FLUXDOWN_SAVE_DIR` | Seed the initial download directory; saved settings take precedence |
| `FLUXDOWN_DATABASE_URL` | SQLite or PostgreSQL connection string; credentials belong in the environment file |
| `FLUXDOWN_WEBROOT` | Replace the embedded Web UI with a static directory |
| `FLUXDOWN_TOKEN` / `FLUXDOWN_TOKEN_FORCE` | Seed the key; force replaces it on each start when set to `1` |
| `FLUXDOWN_LANG` | Fallback language: `en` or `zh` |
| `FLUXDOWN_MDNS` / `FLUXDOWN_LINK_NAME` | Discovery and device name |
| `FLUXDOWN_ANALYTICS` | Anonymous analytics |
| `FLUXDOWN_LOG_LEVEL` / `RUST_LOG` | Logging; `RUST_LOG` takes precedence |
| `FLUXDOWN_DEMO` / `FLUXDOWN_DEMO_URL` | Demo mode and permitted URL |

Do not override module-managed `FLUXDOWN_BIND` or `FLUXDOWN_DATA_DIR` in runtime
files. Custom download directories must be writable by the service user;
home directories are inaccessible by default.

## Maintenance

Follow the package-set `AGENTS.md`. Verify both architecture hashes and that the
two executables remain siblings with an embedded Web UI.

Configuration authorities in [upstream](https://github.com/zerx-lab/FluxDown),
at the packaged tag:

- `native/protocol/src/daemon_config.rs`: daemon keys, types, defaults, bounds.
- `native/protocol/src/settings.rs`: synchronized settings, not all preferences.
- `native/agent/src/server_mode.rs`: server startup and access-key validation.
- `native/agent/src/runtime.rs`, `native/daemon/src/config.rs`: component startup.
- `native/agent/src/gateway.rs`, `native/protocol/src/rpc.rs`: persistent-setting RPCs.

Complete typed configuration coverage, persistent-setting application, and
automated upstream drift detection are not yet implemented.

Lightweight regression test:

```sh
nix-instantiate --eval --strict --expr 'import ./nur-packages/tests/eval.nix {}'
```

Optional VM integration test: `nix-build ./nur-packages/tests/fluxdown.nix`.
It checks startup, Web UI, key persistence, and shutdown; first-run dependencies
can be large.

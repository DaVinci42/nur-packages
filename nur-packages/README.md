# NUR packages

A standalone package set within this fork of the NUR index. The top-level index
is unchanged; this directory can also serve as a separate NUR repository root.

## Layout

- `default.nix`: package and module exports.
- `pkgs/<name>/`: package expressions and package-specific documentation.
- `modules/`: NixOS service modules, exported as paths under `nixosModules`.
- `tests/`: package and module tests.
- `AGENTS.md`: shared maintenance and validation rules.

## Packages

| Package | NixOS module | Documentation |
| --- | --- | --- |
| `fluxdown-server` | `nixosModules.fluxdown` | [FluxDown Server](pkgs/fluxdown-server/README.md) |

Dependencies come from the caller's `pkgs`; module exports also work with
`pkgs = null`.

## Update and validate

Run from the parent repository root. Requires `nix-update`, `jq`, and Nix with
`nix-command` enabled and `<nixpkgs>` available. Define this zsh function:

```zsh
nur-update() {
  local system version=stable
  for system in $(nix eval -f ./nur-packages "$1.meta.platforms" --json | jq -r '.[]'); do
    nix-update -f ./nur-packages "$1" --system "$system" --version="$version" || return
    version=skip
  done
}
```

The first platform selects the latest stable version; subsequent platforms keep
that version and refresh their hashes. If already current, the first invocation
may skip refreshing its hash. This assumes explicit system names in
`meta.platforms`; packages with custom update requirements need their own procedure.
Keep package files tracked in Git so `nix-update` can detect changes reliably.

```zsh
nur-update fluxdown-server
nix build -f ./nur-packages fluxdown-server --no-link
```

Build all packages for the current system with
`nix build -f ./nur-packages --no-link`. Hash updates for other platforms do not
verify their builds; those require a suitable builder or emulation.

Review the version/hash changes and upstream configuration changes, then run the
package's tests (see its README). For FluxDown:

```sh
nix-instantiate --eval --strict --expr 'import ./nur-packages/tests/eval.nix {}'
nixfmt --check nur-packages/default.nix nur-packages/pkgs/fluxdown-server/default.nix nur-packages/modules/fluxdown.nix nur-packages/tests/*.nix
statix check nur-packages
deadnix --fail nur-packages
```

These checks do not start a VM or activate services. `nix-update` updates package
sources, not module compatibility with upstream configuration changes.

## Registration

This package set is not registered in public NUR. After publishing, register the
repository with `file = "nur-packages/default.nix"` in NUR's `repos.json`.
If this directory becomes a separate repository root, omit the `file` field.

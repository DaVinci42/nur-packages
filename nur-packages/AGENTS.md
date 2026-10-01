# NUR package maintenance

- Keep packages in `pkgs/<name>/`, NixOS modules in `modules/`, and tests in
  `tests/`. Export packages and module paths from `default.nix`.
- Keep module exports evaluable with `pkgs = null`; use the caller's `pkgs`.
- Write documentation in English. Put package-specific usage and maintenance
  notes in `pkgs/<name>/README.md`, not in this file.
- Do not modify the central index, consuming configurations, or running services
  unless requested. Keep secrets outside the Nix store.

## Commit style

Use English Conventional Commit titles: `feat:`, `fix:`, `docs:`, `refactor:`,
`test:`, or `chore:`. Keep titles under 72 characters and describe the outcome.
Use `feat` for new capabilities and `fix` for corrections. Explain non-obvious
reasoning in the body. Do not commit, push, or rewrite published history unless
explicitly requested; use `--force-with-lease` for authorized history rewrites.

## Updates

AI agents should follow the `Update and validate` section in `README.md` for
update commands and read the target package's README for exceptions. Refresh
hashes for every supported platform; do not treat an updater's success as proof
of build success or configuration compatibility.

1. Verify the upstream release and review changes since the packaged version.
2. Update the version and all supported source hashes together. Check archive
   layout, dependencies, license, and platform support.
3. Use upstream schemas or parsers at that release as configuration authorities.
   Compare keys, types, defaults, bounds, and application semantics; update
   affected modules and regression tests. Do not claim unimplemented coverage.
4. If generated contracts exist, regenerate and check them; never edit their
   output by hand. Documentation alone does not detect upstream drift.

## Validation

From the repository root, build the changed package with
`nix build -f ./nur-packages <name> --no-link`, run its lightweight tests,
then run `nixfmt --check` on changed Nix files, `statix check nur-packages`,
and `deadnix --fail nur-packages`.

Run VM tests only when requested. Isolate runtime tests from existing services
and data. Report what was verified and what remains untested.

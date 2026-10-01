# NUR package maintenance

- Keep packages in `pkgs/<name>/`, NixOS modules in `modules/`, and tests in
  `tests/`. Export packages and module paths from `default.nix`.
- Keep module exports evaluable with `pkgs = null`; use the caller's `pkgs`.
- Write documentation in English. Put package-specific usage and maintenance
  notes in `pkgs/<name>/README.md`, not in this file.
- Do not modify consuming configurations or running services unless requested.
  Keep secrets outside the Nix store.

## Commit style

Use English Conventional Commit titles: `feat:`, `fix:`, `docs:`, `refactor:`,
`test:`, or `chore:`. Keep titles under 72 characters and describe the outcome.
Use `feat` for new capabilities and `fix` for corrections. Explain non-obvious
reasoning in the body. Do not commit, push, or rewrite published history unless
explicitly requested; use `--force-with-lease` for authorized history rewrites.

## Updates

Use `nix-shell --run 'just update <name>'` and the package's `maintenance.toml`.
Read the package README for exceptions. Review contract changes before using
`just update-reviewed <name> <version>`; never bypass a failed check merely to
finish an update. Only the current platform is build-tested.

1. Verify the upstream release and review changes since the packaged version.
2. Update the version and all supported source hashes together. Check archive
   layout, dependencies, license, and platform support.
3. Use upstream schemas or parsers at that release as configuration authorities.
   Compare keys, types, defaults, bounds, and application semantics; update
   affected modules and regression tests. Do not claim unimplemented coverage.
4. If generated contracts exist, regenerate and check them; never edit their
   output by hand. Documentation alone does not detect upstream drift.

## Validation

Run `nix-shell --run 'just check <name>'` for a package or `just check-all` for
all maintenance targets and updater tests. CI uses the same entry point.
Python changes must pass basedpyright with zero errors and warnings; `just lint`
runs it for every Python file using the shell's interpreter and dependencies.
`just contract <name>` checks the pinned upstream contract without rewriting it.

Run VM tests only when requested. Isolate runtime tests from existing services
and data. Report what was verified and what remains untested.

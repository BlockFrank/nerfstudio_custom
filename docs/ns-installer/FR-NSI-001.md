# FR-NSI-001 — NS Installer modularization and compatibility milestone

## Purpose

FR-NSI-001 converts the custom Nerfstudio installer from a growing collection of flat modules into a bounded architecture with a canonical core, decomposed CLI commands, a GUI surface, compatibility guarantees, and evidence-bound promotion.

## Desired end state

The installer should eventually act as a local control plane for Windows-first Nerfstudio environments:

1. inspect hardware, CUDA, MSVC, Python and current environment state;
2. plan an installation or repair from explicit locks and method contracts;
3. execute deterministic, resumable operations;
4. expose the same behavior through CLI, GUI and automation APIs;
5. preserve receipts, diagnostics and validated lessons for future runs;
6. remain portable enough to migrate toward cross-platform execution later.

## Stable in this milestone

- Canonical implementation modules live under `ns_installer.core`.
- The CLI is decomposed into `ns_installer.cli.app` and command handlers.
- The GUI lives under `ns_installer.gui` and uses the canonical method catalog.
- Existing compatibility wrappers (`locks.py`, `methods_registry.py`, `protected.py`, `deps_lock.py`, and `cli.py`) delegate to canonical implementations.
- Deleted historical import paths are restored as thin facades.
- `ns_installer.core` reexports only helpers proven to have exact historical parity.
- `ns_installer.core.main` remains obsolete; `ns_installer.cli:main` is canonical.
- Compatibility imports are covered by regression tests.
- `.forgerail/` remains repository-local and ignored by Git.

## Compatibility boundary

The following paths are intentionally retained for downstream callers:

- `ns_installer.bootstrap`
- `ns_installer.build`
- `ns_installer.doctor`
- `ns_installer.patches`
- selected exports from `ns_installer.core`

Each flat module delegates directly to its canonical `ns_installer.core.*` implementation. No implementation is copied into the facade.

## Validation contract

Promotion requires all of the following:

- exact branch, baseline and upstream gates;
- no staged or unexpected working-tree paths;
- a fresh A2 compatibility analysis with `PROPOSED_NOT_APPLIED` status;
- patch path allow-list enforcement;
- Python compilation;
- all `tests/ns_installer` tests with repository `addopts` disabled for portability;
- legacy import identity checks;
- CLI parser smoke tests;
- `git diff --check`;
- feature-branch push, target-branch merge, post-merge revalidation, annotated tag, and release attempt;
- immutable external receipts and SHA-256 ledgers.

## Known limitations

The milestone validates architecture and compatibility, not every full installation permutation. CUDA toolkits, MSVC installations, native extensions, method-specific repositories, and large dependency sets still require machine-specific end-to-end matrices. The current GUI also needs additional controls, cancellation, recovery and durable session management.

## Roadmap

1. Add environment-contract schemas and deterministic preflight planning.
2. Expand method metadata into dependency and native-build graphs.
3. Add resumable execution receipts and repair workflows.
4. Complete GUI panels and align them with CLI/API contracts.
5. Validate portable-root operation and then abstract platform-specific behavior.
6. Introduce a formal facade deprecation policy only after caller telemetry and migration evidence exist.

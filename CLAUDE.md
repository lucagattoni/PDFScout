# Claude Instructions

## README auto-update rule

Whenever you modify any file that is referenced or documented in `README.md`
(source files, config files, CLI entry points, schema files, API modules, etc.),
you **must** update `README.md` in the same turn to keep it accurate — without
waiting for the user to ask.

This applies to:
- Any file whose name, path, or purpose is described in `README.md`
- Any behaviour (flags, environment variables, output format, endpoints) that
  `README.md` documents
- Any dependency or configuration change that affects the usage instructions

Update only the sections that are now inaccurate; do not rewrite the whole file.

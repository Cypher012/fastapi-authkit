# fastauthx

A family of small, focused FastAPI packages for authentication and
authorization. Each package does one job, has no hidden dependency on
the others beyond what it actually needs, and ships no database
migrations of its own. You bring your own database session, your own
email provider, and your own Alembic (or other) migration setup.

This repo is a workspace containing three independent packages:

| Package | What it does | Install |
|---|---|---|
| [`fastauthx`](packages/fastauthx) | Core authentication. Password auth, Google OAuth, JWT access tokens, rotating refresh tokens, email verification, password reset. | `pip install fastauthx` |
| [`fastauthx-orgs`](packages/fastauthx-orgs) | Multi tenant organizations, membership, rank based role checks, and invitations. Built on top of `fastauthx`. | `pip install fastauthx-orgs` |
| [`fastauthx-roles`](packages/fastauthx-roles) | Simple global roles for apps that do not need organizations at all. Works with any auth system, not just `fastauthx`. | `pip install fastauthx-roles` |

Each package has its own README with a full quickstart, configuration
reference, and explanation of what it deliberately does not do (and
why). Start there once you know which one you need.

## Which package do I want

* You need password and/or Google login, tokens, verification, and
  password reset, and nothing else. Use `fastauthx` on its own.
* You need multi tenant organizations, teams, or workspaces, where a
  user can belong to more than one and have a different role in each.
  Use `fastauthx` plus `fastauthx-orgs`.
* You just need "is this user an admin" without any concept of
  organizations. Use `fastauthx-roles`, either alone or alongside
  `fastauthx`.

`fastauthx-orgs` and `fastauthx-roles` solve different problems and are
not meant to be used together for the same purpose. If you need both
per organization roles and separate global roles (for example, a
platform level "staff" flag that is independent of any organization),
you can use both at once.

## Design principles behind all three packages

* No package owns a database connection or engine. You always pass in
  a `get_session` dependency.
* No package ships Alembic migrations. Each ships plain SQLModel table
  classes that you import onto your own metadata and migrate yourself,
  so your app's schema history stays in one place.
* No package guesses at your domain. `fastauthx-orgs` ships roles and
  membership checks, not a `Permission` enum, because what permissions
  mean in your app is inherently specific to your app. The same goes
  for `fastauthx-roles`.
* Extension happens through explicit hooks and dependency composition,
  not inheritance or monkeypatching. See `AuthHooks` in `fastauthx`'s
  README for the main example.

## Development

This repo is a `uv` workspace. To run everything locally:

```bash
uv sync
export POSTGRES_USER=... POSTGRES_PASSWORD=... POSTGRES_DB=...
uv run pytest packages/fastauthx/tests packages/fastauthx-orgs/tests packages/fastauthx-roles/tests
```

Each package's test suite talks to a real Postgres instance and builds
its own minimal FastAPI app directly, with no dependency on a host
application.

## License

MIT. See [LICENSE](LICENSE).

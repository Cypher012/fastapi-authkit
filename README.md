# fastauthx

![Python](https://img.shields.io/badge/python-3.13%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

A family of small, focused FastAPI packages for authentication and
authorization. Each package does one job, has no hidden dependency on
the others beyond what it actually needs, and ships no database
migrations of its own. You bring your own database session, your own
email provider, and your own Alembic (or other) migration setup.

## Table of contents

- [Packages](#packages)
- [Which package do I want](#which-package-do-i-want)
- [Design principles](#design-principles)
- [Architecture](#architecture)
- [Development](#development)
- [FAQ](#faq)
- [License](#license)

## Packages

This repo is a `uv` workspace containing three independent packages:

| Package | What it does | Install (uv) | Install (pip) |
|---|---|---|---|
| [`fastauthx`](packages/fastauthx) | Core authentication. Password auth, Google OAuth, JWT access tokens, rotating refresh tokens, email verification, password reset. | `uv add fastauthx` | `pip install fastauthx` |
| [`fastauthx-orgs`](packages/fastauthx-orgs) | Multi tenant organizations, membership, rank based role checks, and invitations. Built on top of `fastauthx`. | `uv add fastauthx-orgs` | `pip install fastauthx-orgs` |
| [`fastauthx-roles`](packages/fastauthx-roles) | Simple global roles for apps that do not need organizations at all. Works with any auth system, not just `fastauthx`. | `uv add fastauthx-roles` | `pip install fastauthx-roles` |

Each package has its own README with a full quickstart, a complete
runnable example, an endpoint or API reference, a configuration
reference, an error response reference, security notes, and an FAQ.
Start there once you know which one you need.

## Which package do I want

- You need password and/or Google login, tokens, verification, and
  password reset, and nothing else. Use `fastauthx` on its own.
- You need multi tenant organizations, teams, or workspaces, where a
  user can belong to more than one and have a different role in each.
  Use `fastauthx` plus `fastauthx-orgs`.
- You just need "is this user an admin" without any concept of
  organizations. Use `fastauthx-roles`, either alone or alongside
  `fastauthx`.

`fastauthx-orgs` and `fastauthx-roles` solve different problems and are
not meant to be used together for the same purpose. If you need both
per organization roles and separate global roles (for example, a
platform level "staff" flag that is independent of any organization),
you can use both at once, since neither depends on the other.

## Design principles

- **No package owns a database connection or engine.** You always pass
  in a `get_session` dependency, the same one your app already uses
  everywhere else.
- **No package ships Alembic migrations.** Each ships plain SQLModel
  table classes that you import onto your own metadata and migrate
  yourself, so your app's schema history stays in one place instead of
  being split across your code and a third party package's.
- **No package guesses at your domain.** `fastauthx-orgs` ships roles
  and membership checks, not a `Permission` enum, because what
  permissions mean in your app is inherently specific to your app. The
  same reasoning applies to `fastauthx-roles`.
- **Extension happens through explicit hooks and dependency
  composition, not inheritance or monkeypatching.** See `AuthHooks` in
  [`fastauthx`'s README](packages/fastauthx#extending-authhooks) for
  the main example, and how `fastauthx-orgs` is built entirely on top
  of it.

## Architecture

```
fastauthx            owns: users, accounts, sessions, verification tokens
   ^
   | AuthHooks.on_user_created (the only seam)
   |
fastauthx-orgs        owns: organizations, memberships, invitations
                       foreign keys into fastauthx's users table

fastauthx-roles        owns: user_roles
                        foreign keys into a "users" table
                        does not import fastauthx at runtime
```

`fastauthx-orgs` depends on `fastauthx` directly, since its hook has to
match `fastauthx`'s exact `AuthHooks` contract. `fastauthx-roles` is
intentionally decoupled: it only needs a `get_current_user` shaped
callable and a `users` table to point a foreign key at, so it works
with `fastauthx` or with a completely different auth setup.

## Development

To run everything locally:

```bash
uv sync
export POSTGRES_USER=... POSTGRES_PASSWORD=... POSTGRES_DB=...
uv run pytest packages/fastauthx/tests packages/fastauthx-orgs/tests packages/fastauthx-roles/tests
```

Each package's test suite talks to a real Postgres instance (no mocks)
and builds its own minimal FastAPI app directly, with no dependency on
a host application.

## FAQ

**Do I need all three packages?**
No. `fastauthx` works completely on its own. `fastauthx-orgs` and
`fastauthx-roles` are optional, and installing one does not pull in the
other.

**Can I use this with an existing user table that is not `fastauthx`'s?**
`fastauthx-orgs` needs `fastauthx`'s exact `Users` model, since its
`AuthHooks.on_user_created` hook is typed against it. `fastauthx-roles`
does not: it works with any `get_current_user` dependency and any table
literally named `users`.

**Why one repo for three packages instead of three repos?**
While the APIs are still settling, keeping them together makes it
easier to change all three consistently. They may be split into
separate repos later once the boundaries are more stable, since each
already publishes and installs as an independent package today.

**Is this production ready?**
The core flows (password auth, Google OAuth, organizations, roles,
invitations) are covered by an automated test suite that runs against
a real Postgres database, and the design choices are documented
throughout each package's README specifically so you can audit them.
That said, this is a young project. Read the code, read the security
notes in each README, and evaluate it the way you would any
authentication dependency before relying on it in production.

## License

MIT. See [LICENSE](LICENSE).

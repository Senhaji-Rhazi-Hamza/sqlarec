# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.0] - 2026-09-26

### Added

- Synchronous and asynchronous `Model.insert().values(mappings)` builders for
  optimized ORM bulk inserts, explicit session overrides, and typed entity,
  row, or mapping results through `returning()`.

## [0.6.0] - 2026-09-26

### Changed

- **Breaking.** `create()` now generates a primary key only when the
  primary-key column type can hold one. `Uuid` columns receive a `uuid.UUID`
  object, or a hex string when declared with `as_uuid=False`; `String` and
  `Text` columns receive a 32-character hex string when they declare no length
  or a length of at least 32. Every other column type, and any primary key that
  is also a foreign key, is left untouched so SQLAlchemy or the database reports
  the missing value. Previously every such primary key received a 32-character
  hex string, which failed on `Uuid` columns, corrupted non-auto-increment
  integer and foreign-key primary keys, and overflowed short string columns.
- `to_dict()` and `__repr__()` now iterate the mapper's column attributes
  instead of `__table__.columns`. Models using joined-table inheritance include
  their inherited columns, and imperatively mapped models keyed by a renamed
  attribute are keyed by the attribute name rather than the column name.
- `__repr__()` is now built only from already-loaded state and never triggers a
  database load. Expired, deferred, and unset attributes render as
  `<not loaded>`. This fixes `DetachedInstanceError` on detached instances,
  `MissingGreenlet` when rendering an asynchronous instance after a commit, and
  the stray `SELECT` emitted for deferred columns.

### Added

- `get_or_create()` accepts an optional `defaults` mapping, on both the
  synchronous and the asynchronous mixin. Lookup keyword arguments now only
  select the existing model, while `defaults` supplies values used solely when
  creating one. Calls without `defaults` behave exactly as before.

## [0.5.0]

- Initial documented release.

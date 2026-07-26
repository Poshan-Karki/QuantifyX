# Developer-managed market context

NEPSEIntel reads developer-reviewed market context from `market_context.json`.
The existing `nepseintel` price table does not need to be changed.

Only two scopes are supported:

- `MARKET`: shown for every symbol.
- `SYMBOL`: shown only when the analyzed ticker matches `symbol`.

## Publishing an entry

Use `market_context.example.json` as a reference. Copy the required entry into
`market_context.json`, replace all example content and links, then change
`status` from `DRAFT` to `PUBLISHED`.

Dates use `YYYY-MM-DD` in Nepal time. An entry is active when:

- its status is `PUBLISHED`;
- `published_at` is today or earlier;
- `expires_at` is empty or today/later; and
- a `SYMBOL` entry matches the analyzed ticker.

The results page displays every matching entry. The highest-priority active
entry supplies the contextual verdict. Ordering is decided by:

1. `priority`;
2. `impact` (`HIGH`, `MEDIUM`, `LOW`);
3. most recent `published_at`.

The following fields are required:

- `id`
- `scope`
- `headline`
- `message`
- `verdict_message`
- `published_at`

`symbol` is also required for `SYMBOL` entries. Use an official or primary
source URL whenever possible. Keep the quantitative strategy verdict and the
developer-written contextual verdict distinct.

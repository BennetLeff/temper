# Temper System Atlas

The atlas is a static GitHub Pages application backed by the curated graph in
`app.js`. Its nodes and payload paths are semantic architecture: they are not
inferred from imports alone.

Run the same structural and citation check used by CI:

```bash
node dashboard/architecture/validate.mjs
```

On relevant pull requests, `.github/workflows/architecture-atlas.yml` checks
that node IDs, flow endpoints, payloads, districts, and all repository source
citations remain valid. After a merge to `main`, `dashboard-deploy.yml` repeats
the check, stamps `build-info.js` with the source commit, and publishes the
whole `dashboard/` directory to the `gh-pages` branch. The atlas is served from
the `/architecture/` path of that Pages site.

When an architectural responsibility or data flow changes, update the graph in
`app.js` in the same pull request. CI catches structural drift and stale cited
paths; the human-authored descriptions and topology remain deliberately
reviewable rather than guessed by a generator.

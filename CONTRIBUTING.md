# Build a clearer public record

OpenPali makes the Palisades rebuild easier to understand, one documented
observation at a time. You can help with code, maps, accessibility, source
research, clearer language, or a good bug report.

Start small. A confusing label, a broken local setup step, and a missing
source citation are all useful places to begin.

## Find your first piece

| If you enjoy… | Start here |
| --- | --- |
| Maps and interfaces | [The web client](web/README.md): React, MapLibre, and optional 3D |
| Civic data | [Source adapters](pipeline/openpali/adapters/) and [golden source fixtures](pipeline/tests/fixtures/sources/) |
| Backend engineering | [The platform](pipeline/README.md): the evidence ledger, API, and release gates |
| Statistics and ML | [Metrics](pipeline/openpali/metrics/) and [model evaluation](pipeline/openpali/ml/) |
| Writing and design | Setup instructions, map labels, [methods](web/src/pages/MethodsPage.tsx), and accessible explanations |

Check [existing issues](https://github.com/Andrewwilliamross/openpali/issues)
before starting. For a substantial feature, new source, or change to what a
milestone means, open an issue with the problem, supporting evidence, and
proposed scope. Small fixes can go straight to a pull request.

## Get a local checkout running

Use Python 3.12 and Node.js 24 to match CI. Git, npm, and Python's `venv`
module are needed; Docker Compose is needed for the full platform.

```sh
git clone https://github.com/Andrewwilliamross/openpali.git
cd openpali
./scripts/bootstrap
./scripts/check-fast
```

Bootstrap installs the locked Python dependencies into `pipeline/.venv` and
the web dependencies into `web/node_modules`. It does not start services.
If web dependencies are already installed and the lockfile changes, run
`npm ci` again from `web/`.

For UI work, start with the bundled map data:

```sh
cd web
npm run dev
```

Open the local URL Vite prints. The bundled fallback supports browsing the
map; live API features need the stack in [infra/README.md](infra/README.md).
That guide covers image builds, migrations, object-store initialization, and
the first development release.

## The rules that make the data useful

- **Keep the evidence attached.** Preserve the source record, observation
  time, retrieval time, and lineage needed to check a claim.
- **Let unknown stay unknown.** Missing evidence does not mean an owner is
  inactive. A scheduled inspection does not establish an inspection outcome.
- **Keep milestones distinct.** Cleanup, design review, permitting,
  construction evidence, and occupancy are separate lanes.
- **Make corrections visible.** Preserve history and conflicts; do not
  quietly overwrite a prior assertion.
- **Respect release boundaries.** API data and spatial assets must use the
  selected release and snapshot. Preserve explicit fallback states.
- **Keep fixtures and private details out of public evidence.** Use synthetic
  records in tests. Do not commit credentials, resident contact details, or
  assets whose redistribution rights are unresolved.

The domain code in [`pipeline/openpali/domain/`](pipeline/openpali/domain/)
and its tests are the implementation reference. The documents under
`Docs/initialbuild_docs/` describe the earlier prototype; its scores and
completion guesses are retired from the product.

## Check your change

Run focused checks while you work. From the repository root:

```sh
# Example: domain behavior, without services
pipeline/.venv/bin/python -m pytest pipeline/tests/test_domain_semantics.py -q

# The shared local/CI gate: Python + web tests, lint, types, OpenAPI drift
./scripts/check-fast
```

For web changes, also run `npm run build` from `web/`. Include a screenshot
or short recording for visible changes, and check narrow screens, keyboard
navigation, and reduced motion where relevant.

When API schemas change, regenerate both the contract and the client using
the commands in [web/README.md](web/README.md#api-contract). Include the
generated changes in the same pull request.

Database, publication, orchestration, or spatial changes may also need
service-backed checks. Follow [infra/README.md](infra/README.md), then use
`./scripts/check-full` for the extended local gate. It includes long-running
jobs and source access; it is separate from the smaller pull-request CI gate.
Record which checks ran and explain anything you could not run.

## Send a pull request

1. Fork the repository and make a branch for one coherent change.
2. Explain the user-visible problem and the resulting behavior.
3. Add or update meaningful tests when behavior changes; update affected docs.
4. Link the related issue and include your validation results.

Keep generated data and unrelated formatting changes out of the diff unless
they are necessary to the change. If you use coding assistants, review their
output and verify its claims as you would any other contribution.

## Reports, people, and rights

Use the [issue chooser](https://github.com/Andrewwilliamross/openpali/issues/new/choose)
for software bugs, feature ideas, and source or methodology problems. For a
specific property correction, use **Report an issue with this record** on its map card
when the API is available. Avoid posting personal details in public issues.

Follow our [Code of Conduct](CODE_OF_CONDUCT.md). Report vulnerabilities using
the [security policy](SECURITY.md).

The project license is still pending. Read the [license status](README.md#license-and-data-rights)
before reusing or redistributing code or assets; public visibility does not
settle the separate rights of the code, source data, imagery, and basemaps.

# ED807 Converter

An offline ED807 XML-to-JSON converter with XSD validation.

## Overview

ED807 is a Bank of Russia XML message format used for BIC directory information. ED807 Converter reads a local XML file or ZIP containing one XML document, validates the supported profile against an official schema package and writes JSON with diagnostics to private local staging.

This is independent developer tooling. It does not download inputs or publish outputs.

## Features

- Official, fingerprint-verified UFEBS XSD validation.
- Source field names, textual values, leading zeros, nesting and repeated records preserved.
- Deterministic JSON for identical inputs, converter version and event metadata.
- Reference and integrity diagnostics, with unresolved references retained as warnings.
- Bounded XML/ZIP processing, DTD/XXE rejection and private output permissions.

## Requirements

The qualified baseline is **CPython 3.14.10 non-FIPS**, **lxml 6.1.3**, conventional **Linux x86_64**, with **glibc >= 2.26** required by the pinned wheel. Other platforms and free-threaded builds are not qualified. Later Python 3.14 patches are accepted by the version guard but require qualification before support is claimed.

A local official UFEBS 2026.09.0 package is required for validation. See [runtime and security limitations](converter/docs/runtime-security.md), including unresolved bundled-native-library risks.

## Installation

Obtain this repository from [nick-roust/ed807](https://github.com/nick-roust/ed807). From its root, use a trusted supported Python interpreter and pip installer:

```sh
cd converter
python3.14 -m venv --without-pip .venv
python3.14 -m pip --python .venv install --only-binary=:all: --require-hashes -r requirements.lock
```

The installer needs pip >= 22.3. If the selected interpreter has no pip, use another trusted pip-capable interpreter for the second command, retaining `--python .venv`. The lockfile allows only the approved lxml wheel. See the [installation guide](converter/README.md#installation) for runtime checks and offline installation.

## Official Schema

Obtain [UFEBS 2026.09.0 from the Bank of Russia](https://cbr.ru/Content/Document/File/123129/UFEBS_v2026_09_0.zip) separately and keep it outside the repository. Verify SHA-256:

```text
3ca5333743462c7ccce34914765c15d45b1f26e3ca227f75f04bce01062e3566
```

The converter checks the package and its four-member ED807 dependency closure. It does not accept arbitrary schemas. See [attribution and rights boundaries](ATTRIBUTION.md).

## Usage

From `converter/`, with a separately obtained input and schema:

```sh
mkdir -m 700 /tmp/ed807-private
PYTHONPATH=src .venv/bin/python -m bic convert \
  --input /path/to/private/input.xml \
  --schema-package /path/to/private/UFEBS_v2026_09_0.zip \
  --staging /tmp/ed807-private \
  --converted-at 2026-11-11T12:00:00Z
```

Replace the example timestamp with the actual recorded UTC conversion event. Reuse that timestamp for deterministic reruns of that event. Input may also be `.zip`. Optional `--expected-xml-sha256` checks the expected hash of **your** XML bytes; no particular private snapshot is required for normal use.

Stdout reports output paths, counts, size and SHA-256. Each run creates `candidate.json`, `diagnostics.json` and, after completed writes, a `COMPLETE` marker in a private run directory. See [CLI details](converter/README.md#cli).

## Output Format

The contract is **`roust.bic.ed807` / `1.0.0`**. The envelope contains metadata and source-order participants; nested arrays retain accounts, SWIFT identifiers and restrictions, including duplicates. XML attributes remain strings. JSON is compact UTF-8 without BOM with sorted object keys and one trailing LF.

See the [implemented JSON contract](converter/docs/json-contract.md). XSD validation does not prove source authenticity, freshness or completeness.

## Testing

From `converter/`, explicitly supply the schema and a nonexistent private-input path:

```sh
BIC_SCHEMA_PACKAGE=/path/to/private/UFEBS_v2026_09_0.zip \
  BIC_SOURCE_XML=/path/to/not-supplied/private-regression.xml \
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  .venv/bin/python -m unittest discover -s tests -v
```

Expected: **29 passed, one explicitly identified private integration skip, zero failures**. Missing schema causes additional skips and is incomplete verification. No banking dataset is needed for the public synthetic cases. [Optional private regression](converter/README.md#optional-private-regression) is separate.

## Security

DTD/entities and external resource resolution are blocked; XML and ZIP sizes, entry counts and depth are bounded. The CLI sets a 120-second deadline and 1 GiB address-space ceiling. Native library risks remain; these controls are not a security certification. See [security details](converter/docs/runtime-security.md).

Staging must be owned by the current user, have no group/other permission bits and be outside the checkout at a canonical path without symlink components. The CLI does not recognize every web server's document root or prevent later copying/publication. Choose a private local filesystem and keep output access controlled.

## Limitations

Only the implemented single-message FIRR profile and pinned XSD release are supported. SIRR, multipart, unsupported historical profiles, automatic updates and dataset publication are outside scope. Official schemas and banking data are not bundled. Diagnostics are partly Russian.

ED807 Converter v0.1.0 is publicly available as an independent, source-only open-source project under the MIT License.

The supported runtime is CPython 3.14.10 (non-FIPS) with lxml 6.1.3 on Linux x86_64.

The project has passed its public CI qualification. Known residual native-library security risks remain documented in the [runtime security guide](converter/docs/runtime-security.md). These risks have not been eliminated, and the supported execution model remains limited to the offline CLI.

No standalone GitHub Release, binary distribution, or PyPI package has been published.

## License

[MIT](LICENSE), Copyright (c) 2026 Nick Roust, for project-owned software and original documentation. Official materials, source datasets and dependencies retain their respective rights; see [ATTRIBUTION.md](ATTRIBUTION.md). Generated banking data is not granted a license by the software license.

## Author

[Nick Roust](https://roust.us) · [nick-roust/ed807](https://github.com/nick-roust/ed807).

For contribution proposals, use the repository's discussion/issue facilities when available. Do not submit banking datasets, credentials or private conversion outputs.

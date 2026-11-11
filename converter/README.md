# ED807 Converter — Installation and CLI

An offline ED807 XML/ZIP-to-JSON converter with official XSD validation. See the [product overview](../README.md), [JSON contract](docs/json-contract.md), [technical reference](docs/technical-reference.md) and [attribution](../ATTRIBUTION.md).

## Requirements

Qualified runtime: **CPython 3.14.10 non-FIPS**, **lxml 6.1.3**, Linux x86_64, conventional GIL build. The selected wheel requires glibc >= 2.26; the test host uses glibc 2.43, so minimum-glibc behavior is not separately qualified. The CLI accepts Python 3.14 patches >= 10, exact lxml 6.1.3 and FIPS mode 0. Later patches require qualification. Other minors, FIPS deployments, other platforms and free-threaded Python are not qualified. Do not disable an organizational FIPS requirement to run this tool.

Use a trusted Python distribution with `venv` and a trusted pip >= 22.3 installer supporting `--python`. The CLI uses Linux process limits. No package installation/build step for `bic` is required: run with `PYTHONPATH=src`.

## Installation

From `converter/`, create a fresh isolated environment:

```sh
python3.14 -m venv --without-pip .venv
python3.14 -m pip --python .venv install --only-binary=:all: --require-hashes -r requirements.lock
.venv/bin/python -c 'import sys, _hashlib; from lxml import etree; assert sys.version_info[:3] == (3, 14, 10); assert _hashlib.get_fips_mode() == 0; assert etree.LXML_VERSION[:3] == (6, 1, 3); print(sys.version, etree.LIBXML_VERSION, etree.LIBXSLT_VERSION)'
```

If that interpreter has no pip, invoke a separately trusted pip-capable Python for installation, retaining `--python .venv`. Installing into an older environment does not upgrade its interpreter. The wheel is:

```text
lxml-6.1.3-cp314-cp314-manylinux_2_26_x86_64.manylinux_2_28_x86_64.whl
SHA-256: a7eb78ba28b187e1e9203a55c60fcf70df2d22cb205fe6d51b9383d6097419f0
```

Offline installation can use the exact separately obtained wheel:

```sh
python3.14 -m pip --python .venv install --no-index --find-links /path/to/private/wheels --only-binary=:all: --require-hashes -r requirements.lock
```

There is no unpinned source-build fallback. Runtime component versions and unresolved security limitations are documented in [runtime security](docs/runtime-security.md).

## Official Schema

Obtain [UFEBS 2026.09.0](https://cbr.ru/Content/Document/File/123129/UFEBS_v2026_09_0.zip) from the [Bank of Russia's format publication](https://www.cbr.ru/development/Formats/) and store it outside the checkout. Verify before use:

```sh
sha256sum /path/to/private/UFEBS_v2026_09_0.zip
```

Expected archive SHA-256:

```text
3ca5333743462c7ccce34914765c15d45b1f26e3ca227f75f04bce01062e3566
```

`load_schema` additionally checks the four approved ED807 members listed in the [technical reference](docs/technical-reference.md#schema-identity). The package is an external input, not part of this distribution. Conversion performs no download or arbitrary schema resolution. Official materials retain their respective rights; see [attribution](../ATTRIBUTION.md).

## CLI

All commands below run from `converter/`:

```sh
mkdir -m 700 /tmp/ed807-private
PYTHONPATH=src .venv/bin/python -m bic convert \
  --input /path/to/private/input.xml \
  --schema-package /path/to/private/UFEBS_v2026_09_0.zip \
  --staging /tmp/ed807-private \
  --converted-at 2026-11-11T12:00:00Z
```

| Parameter | Meaning |
| --- | --- |
| `--input` | Required local XML or ZIP with exactly one XML member; source bytes are not changed |
| `--schema-package` | Required local fingerprint-pinned official ZIP |
| `--staging` | Required existing private directory outside the checkout |
| `--converted-at` | Required recorded event timestamp, exact `YYYY-MM-DDTHH:MM:SSZ` UTC form |
| `--expected-xml-sha256` | Optional lowercase SHA-256 of your original XML bytes, including the XML inside a ZIP |

Use the actual UTC event time in place of the example; reuse event metadata only for a reproduction of that conversion. Obtain module help with `PYTHONPATH=src .venv/bin/python -m bic convert --help`.

### Staging trust boundary

The CLI resolves the staging path and rejects it when it is inside the checkout root inferred from `cli.py`'s location or differs from its absolute canonical path (including symlink components). It requires a directory owned by the current user with no group/other permission bits. Documentation recommends mode **0700**. It creates unique `ed807-*` run directories with private permissions, output files at **0600**, and a `COMPLETE` marker only after both completed writes.

It does not discover arbitrary public/build/web-served directories elsewhere on the machine. The caller must choose a private local destination, control ancestors and access, and prevent concurrent untrusted changes. This is not a defense against a malicious same-user process or all filesystem races. Direct API callers must apply their own process supervision.

On success, stdout is a summary with candidate/diagnostic paths, counts, output byte size and SHA-256. Stderr gives diagnostic severity/code and Russian explanations. `candidate.json` follows the [contract](docs/json-contract.md); `diagnostics.json` carries source hash, counts and diagnostic context. Do not publish diagnostics from real inputs indiscriminately: context can contain source identifiers. Failure can leave an incomplete private run directory without `COMPLETE`; earlier runs are not overwritten.

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Conversion succeeded; inspect warnings |
| 2 | Argument parsing failure |
| 10 | Input/archive/checksum/runtime failure |
| 20 | XML parsing or XML security rejection |
| 30 | Official XSD validation failure |
| 40 | Unsupported profile or mapping structure |
| 50 | Integrity or count failure |
| 60 | Metadata, staging, process-resource or generic conversion failure |

Diagnostic codes distinguish causes; native parser wording is not a stable API. Unresolved references and unknown described code values warn while preserving source data. Duplicate BICs and parent cycles reject the entire candidate; duplicate account occurrences are retained.

## Public Synthetic Tests

Provide the schema externally and explicitly point the private source variable at a nonexistent path:

```sh
BIC_SCHEMA_PACKAGE=/path/to/private/UFEBS_v2026_09_0.zip \
  BIC_SOURCE_XML=/path/to/not-supplied/private-regression.xml \
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  .venv/bin/python -m unittest discover -s tests -v
```

Expected: **30 tests discovered, 29 passed, one skip** (`test_local_integration_regression`: local original not supplied), zero failures. Schema-related skips are not accepted as complete public verification. Without the official package, parser/input-only cases still run, but the result is incomplete. Fixtures are synthetic and generated at runtime; no dataset is committed. Tests exercise the CLI, security controls, XSD validation, mapping, diagnostics and determinism.

## Optional Private Regression

Maintainers with the separately preserved original `20261008_ED807_full.xml` can set `BIC_SOURCE_XML` to its private path and run the same command. The integration test deliberately checks that exact historical XML SHA-256 and its measured counts; unrelated user inputs must not be used as replacements. Expected with both exact external inputs: **30 passed, zero skipped, zero failed**. The original dataset is not distributed and is not needed for normal conversion or the public synthetic tests.

For historical byte comparison, run two CLI conversions with the preserved original XML, pinned XSD and fixed `--converted-at 2026-10-08T07:40:33Z`. Historical candidate: **804373 bytes**, SHA-256 `beb21d3f5fd9db9e044350e74104ff9facf7ee2fced585a7ff7057a1cfbad715`. This is a fixed private acceptance fixture, not a universal output hash.

## Security and Limitations

See [runtime security](docs/runtime-security.md). Only supported FIRR with the accepted headers/namespace is converted. Multipart/SIRR and unsupported historical profiles reject. No acquisition, automatic updates, business-rule certification or output publication is implemented. XSD validity does not prove authentic origin, completeness or currency. Output rights are independent of the software's [MIT License](../LICENSE).

# Attribution and licensing boundaries

## Project software

ED807 Converter is an independent project by Nick Roust. Copyright (c) 2026 Nick Roust.
The [MIT License](LICENSE) applies to project-owned software, tests and original documentation. It does not claim ownership of official technical identifiers or grant rights belonging to other parties. The project is not official Bank of Russia software and is not endorsed by the Bank of Russia.

## Official technical sources

The Bank of Russia is the official source of the ED807 message specification. ED807 uses the XML namespace `urn:cbr-ru:ed:v2.0`. This converter validates its supported profile using **UFEBS 2026.09.0**.

- [Official UFEBS format publication](https://www.cbr.ru/development/Formats/).
- [UFEBS 2026.09.0 package acquisition](https://cbr.ru/Content/Document/File/123129/UFEBS_v2026_09_0.zip).
- Package member `УФЭБС_2026_09_0_КБР.pdf`: general format documentation.
- Package member `Doc/УФЭБС_2026_09_0_КБР_Реквизитный_Состав.pdf`: ED807 section 4.118, table 126, printed pages 481–483.
- Package member `Doc/УФЭБС_2026_09_0_КБР_Кодовые_Значения.pdf`: code entries 65–67 and 72–81, printed pages 29–34.

References checked on 2026-11-11. These identify technical sources; package fingerprints and acquisition instructions are in [the converter guide](converter/README.md#official-schema).

Field names, code values, namespace identifiers and validation facts are used for interoperability. Public documentation describes the project's mapping and behavior in original factual wording; it does not reproduce the official descriptive code-list tables. Consult the official package for authoritative definitions and code meanings.

Official specifications, separately obtained schemas, banking datasets and third-party dependencies retain their respective rights. They are not relicensed under this project's MIT License. The converter source distribution does not redistribute official schemas, PDFs or banking datasets. Users obtain official materials separately. Generated JSON may contain source banking data; the software license does not grant redistribution rights to those records.

The Bank of Russia's [site notice](https://www.cbr.ru/about/) and [user agreement](https://www.cbr.ru/user_agreement/) remain relevant to official materials. Attribution is not a blanket permission to relicense, redistribute or publish them. This project makes no blanket determination of those rights.

## Third-party software

Dependencies are acquired separately; their implementations and binaries are not included in this source distribution.

- **CPython:** [PSF license and incorporated-software notices](https://docs.python.org/3/license.html).
- **lxml 6.1.3:** BSD licensing for its main implementation, with separately licensed portions and resources; see the [version-specific license inventory](https://raw.githubusercontent.com/lxml/lxml/lxml-6.1.3/LICENSES.txt).
- The selected lxml wheel bundles **libxml2, libxslt and libexslt** under MIT-style component terms, **zlib** under its own license and **GNU libiconv** under LGPL 2.1 terms. These components retain their notices and conditions. See the same upstream inventory; the project MIT License does not replace those terms.

Any future redistribution of dependency binaries or official materials needs an artifact-specific license and notice review. Installing a separately supplied dependency does not make it project-owned source.

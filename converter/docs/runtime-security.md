# Runtime and Security Limitations

Qualification baseline: 2026-11-11, CPython 3.14.10 non-FIPS, lxml 6.1.3, Linux x86_64. Only the pinned wheel is supported. Functionality tests do not establish security certification or release approval.

## Input Controls

The converter rejects DTDs/internal subsets (including UTF-16) and disables external entities, external resource resolution and network schema loading. Only the fingerprinted official schema closure is resolved. ZIP members are read without extraction; unsafe paths, special files/symlinks, encryption, duplicate names, unsupported compression and ambiguous XML inputs are rejected. CRC and bounded reads are checked.

| Limit | Value |
| --- | --- |
| XML bytes | 32 MiB |
| ZIP bytes | 16 MiB |
| ZIP entries | 16 |
| Total decompressed ZIP bytes | 32 MiB |
| XML depth | 32 |
| Trusted schema archive | 64 MiB plus package/member fingerprints |
| CLI deadline | 120 seconds |
| CLI address-space ceiling | 1 GiB |

Direct library callers must impose their own process limits. Parsing remains native-code execution; bounded offline inputs reduce exposure without proving all malformed inputs safe.

## Output Controls

The CLI requires canonical staging outside its inferred checkout root, owned by the user with no group/other permission bits. It writes unique private directories, 0600 files and a completion marker. It does not identify arbitrary web-server roots or control copying after conversion. Use trusted private directories and controlled ancestors. Concurrent filesystem changes or malicious same-user processes are outside the assurance provided by these checks. Input symlink handling is not a general filesystem sandbox; supply trusted local input locations.

Candidate JSON and diagnostic context can contain source identifiers. Keep them private unless a separate data-rights and publication decision authorizes disclosure. No converter command performs publication.

## Bundled Native Components

The selected official wheel reports libxml2 **2.14.6**, libxslt **1.1.43** with documented security backports, libexslt **0.8.24**, zlib **1.3.2** and GNU libiconv **1.18**. Version and wheel identity do not establish a complete patch inventory or eliminate advisories. Upgrading system libxml2 does not replace the wheel's bundled copy.

As reviewed on 2026-11-10, unresolved libxml2 dictionary/allocation risks and incomplete native-component advisory/backport coverage remain. [libxml2 2.15.4 release notes](https://download.gnome.org/sources/libxml2/2.15/libxml2-2.15.4.news) and [current zlib upstream information](https://zlib.net/) describe newer fixes not supplied simply by this wheel pin. lxml's [release notes](https://lxml.de/6.1/changes-6.1.3.html) and [version-specific build configuration](https://github.com/lxml/lxml/blob/lxml-6.1.3/.github/workflows/wheels.yml) provide upstream context. Some affected APIs are outside the converter path; that is not equivalent to a fully fixed binary.

Native security acceptance remains pending before a public release. Do not expand this converter into arbitrary XSLT processing or a network-facing service based on these tests. Recheck upstream advisories at the release decision and qualify any future dependency change separately. There is no custom wheel or unpinned fallback in this distribution.

## Reporting Issues

Use an appropriate private contact channel linked from [the author's website](https://roust.us) for sensitive reports when available. Do not post banking inputs, tokens or real diagnostics in public issues. No security response SLA or formal vulnerability-disclosure program is promised.

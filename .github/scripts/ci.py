"""CI-only qualification; no acquisition code is added to the converter.

The tests command uses unittest's discover CLI parser with the same arguments as
python -m unittest discover -s tests -v, plus a structured result/coverage gate.
"""
import _hashlib
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import ssl
import subprocess
import sys
import sysconfig
import tempfile
import unittest
from urllib.parse import urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_URL = "https://cbr.ru/Content/Document/File/123129/UFEBS_v2026_09_0.zip"
SCHEMA_HASH = "3ca5333743462c7ccce34914765c15d45b1f26e3ca227f75f04bce01062e3566"
WHEEL_NAME = "lxml-6.1.3-cp314-cp314-manylinux_2_26_x86_64.manylinux_2_28_x86_64.whl"
WHEEL_HASH = "a7eb78ba28b187e1e9203a55c60fcf70df2d22cb205fe6d51b9383d6097419f0"
MAX_SCHEMA = 64 * 1024 * 1024
PERMITTED_SKIP = "test_converter.OfficialSchemaTests.test_local_integration_regression"


class CIError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise CIError(message)


def fingerprint(path, maximum):
    require(path.is_file() and not path.is_symlink(), "INPUT: expected a regular local file")
    require(0 < path.stat().st_size <= maximum, "INPUT: file size outside allowed bounds")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            size += len(block)
            require(size <= maximum, "INPUT: file exceeded size bound")
            digest.update(block)
    return digest.hexdigest()


def verify_runtime():
    require(platform.python_implementation() == "CPython", "RUNTIME: CPython required")
    require(sys.version_info[:3] == (3, 14, 10), "RUNTIME: exact Python 3.14.10 required")
    require(sys.platform == "linux" and platform.machine() == "x86_64", "RUNTIME: Linux x86_64 required")
    require(not sysconfig.get_config_var("Py_GIL_DISABLED"), "RUNTIME: conventional GIL build required")
    probe = getattr(_hashlib, "get_fips_mode", None)
    require(callable(probe) and probe() == 0, "RUNTIME: Python OpenSSL FIPS mode must be 0")
    marker = Path("/proc/sys/crypto/fips_enabled")
    if marker.exists():
        require(marker.read_text().strip() == "0", "RUNTIME: kernel FIPS flag is not 0")
    require(not Path("/etc/system-fips").exists(), "RUNTIME: system FIPS marker present")
    # These probes are not proof about every provider or system-wide policy.
    print(json.dumps({"python": platform.python_version(), "implementation": "CPython",
                      "architecture": platform.machine(), "openssl": ssl.OPENSSL_VERSION,
                      "pythonFips": 0, "kernelFipsFlag": "checked" if marker.exists() else "absent"}))


def verify_wheel(directory):
    require(sorted(p.name for p in directory.iterdir()) == [WHEEL_NAME], "DEPENDENCY: unexpected wheel set")
    wheel = directory / WHEEL_NAME
    require(fingerprint(wheel, 32 * 1024 * 1024) == WHEEL_HASH, "DEPENDENCY: wheel SHA-256 mismatch")
    print(json.dumps({"wheel": WHEEL_NAME, "sha256": WHEEL_HASH}))
    return wheel


def verify_dependencies(directory):
    from lxml import etree
    require(etree.LXML_VERSION[:3] == (6, 1, 3), "DEPENDENCY: exact lxml 6.1.3 required")
    wheel = verify_wheel(directory)
    with zipfile.ZipFile(wheel) as archive:
        member = "lxml/" + Path(etree.__file__).name
        require(Path(etree.__file__).read_bytes() == archive.read(member),
                "DEPENDENCY: installed etree differs from pinned wheel")
    native = ctypes.CDLL(etree.__file__)
    try:
        exslt = ctypes.c_int.in_dll(native, "exsltLibexsltVersion").value
    except ValueError:
        exslt = None
    print(json.dumps({"lxml": etree.LXML_VERSION, "libxmlRuntime": etree.LIBXML_VERSION,
                      "libxmlCompiled": etree.LIBXML_COMPILED_VERSION,
                      "libxsltRuntime": etree.LIBXSLT_VERSION,
                      "libxsltCompiled": etree.LIBXSLT_COMPILED_VERSION,
                      "libexsltNumeric": exslt, "nativeSecurityAcceptance": "OPEN"}))


def acquire_schema(temp_root):
    temp_root = temp_root.resolve()
    require(temp_root.is_dir() and not temp_root.is_relative_to(ROOT),
            "SCHEMA_ACQUISITION: runner-local storage must be outside checkout")
    parts = urlsplit(SCHEMA_URL)
    require(parts.scheme == "https" and parts.hostname == "cbr.ru" and parts.port is None
            and parts.username is None and parts.password is None and not parts.fragment,
            "SCHEMA_ACQUISITION: unexpected source host or protocol")
    try:
        version = subprocess.run(["curl", "--disable", "--version"], capture_output=True,
                                 text=True, check=True, timeout=5)
        match = re.match(r"curl (\d+)\.(\d+)\.(\d+)", version.stdout)
        require(match and tuple(map(int, match.groups())) >= (8, 4, 0),
                "SCHEMA_ACQUISITION: curl >= 8.4 required for streaming size limit")
        with tempfile.TemporaryDirectory(prefix="ed807-schema-", dir=temp_root) as folder:
            partial = Path(folder) / "package.zip"
            result = subprocess.run([
                "curl", "--disable", "--fail", "--silent", "--show-error",
                "--proto", "=https", "--proto-redir", "=https", "--location", "--max-redirs", "0",
                "--connect-timeout", "10", "--max-time", "90", "--max-filesize", str(MAX_SCHEMA),
                "--output", str(partial), "--write-out", "%{http_code} %{url_effective}", SCHEMA_URL,
            ], capture_output=True, text=True, timeout=95)
            require(result.returncode == 0, "SCHEMA_ACQUISITION: official HTTPS download failed")
            require(result.stdout.strip() == "200 " + SCHEMA_URL,
                    "SCHEMA_ACQUISITION: unexpected HTTP status or effective URL")
            require(fingerprint(partial, MAX_SCHEMA) == SCHEMA_HASH,
                    "SCHEMA_FINGERPRINT: official package SHA-256 mismatch")
            # Keep only verified bytes; mkstemp is private, outside checkout/cache.
            descriptor, name = tempfile.mkstemp(prefix="ed807-verified-", suffix=".zip", dir=temp_root)
            try:
                with os.fdopen(descriptor, "wb") as output, partial.open("rb") as stream:
                    while block := stream.read(1024 * 1024):
                        output.write(block)
                require(fingerprint(Path(name), MAX_SCHEMA) == SCHEMA_HASH,
                        "SCHEMA_FINGERPRINT: final copy mismatch")
            except BaseException:
                Path(name).unlink(missing_ok=True)
                raise
            return Path(name)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise CIError("SCHEMA_ACQUISITION: download tool, timeout or storage failure") from exc


def enforce_results(discovered, result):
    skipped = [test.id() for test, _ in result.skipped]
    accepted = (discovered == 30 and result.testsRun == 30 and result.successes == 29
                and skipped == [PERMITTED_SKIP] and not result.failures and not result.errors
                and not result.expectedFailures and not result.unexpectedSuccesses)
    summary = {"discovered": discovered, "run": result.testsRun, "passed": result.successes,
               "skipped": skipped, "failures": len(result.failures), "errors": len(result.errors),
               "accepted": accepted}
    print(json.dumps(summary, sort_keys=True))
    require(accepted, "TEST_POLICY: expected exactly 29 successes and the one named private skip")


class Result(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.successes = 0

    def addSuccess(self, test):
        super().addSuccess(test)
        self.successes += 1


class Runner(unittest.TextTestRunner):
    resultclass = Result

    def run(self, test):
        discovered = test.countTestCases()
        result = super().run(test)
        enforce_results(discovered, result)
        return result


def run_tests():
    require("BIC_SOURCE_XML" not in os.environ, "TEST_INPUT: BIC_SOURCE_XML must be unset")
    require(not (ROOT / "data").exists(), "TEST_INPUT: no data directory permitted in public CI")
    schema = os.environ.get("BIC_SCHEMA_PACKAGE")
    require(bool(schema), "SCHEMA_ENV: BIC_SCHEMA_PACKAGE is required")
    require(fingerprint(Path(schema), MAX_SCHEMA) == SCHEMA_HASH, "SCHEMA_FINGERPRINT: test schema mismatch")
    require(Path.cwd() == ROOT / "converter", "TEST_POLICY: run from converter/")
    # The standard unittest CLI discovery parser and verbosity, with structured results.
    unittest.main(module=None, argv=["python -m unittest", "discover", "-s", "tests", "-v"],
                  testRunner=Runner, exit=False)


def main():
    require(len(sys.argv) == 2, "CI: expected runtime, wheel, dependencies, schema or tests")
    command = sys.argv[1]
    if command == "runtime":
        verify_runtime()
    elif command in {"wheel", "dependencies"}:
        directory = Path(os.environ["RUNNER_TEMP"]) / "ed807-wheels"
        (verify_wheel if command == "wheel" else verify_dependencies)(directory)
    elif command == "schema":
        archive = acquire_schema(Path(os.environ["RUNNER_TEMP"]))
        with Path(os.environ["GITHUB_ENV"]).open("a") as stream:
            stream.write("BIC_SCHEMA_PACKAGE=" + str(archive) + "\n")
        print(json.dumps({"schema": "UFEBS 2026.09.0", "sha256": SCHEMA_HASH}))
    elif command == "tests":
        run_tests()
    else:
        raise CIError("CI: unknown command")


if __name__ == "__main__":
    try:
        main()
    except (CIError, OSError, KeyError, ValueError, subprocess.SubprocessError) as exc:
        print("CI FAILED: " + str(exc), file=sys.stderr)
        raise SystemExit(1)

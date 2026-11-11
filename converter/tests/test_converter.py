import argparse
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from lxml import etree

from bic.cli import staging_directory, utc_timestamp, write_result
from bic.core import (
    BASE_URL, ConversionError, Limits, NS, SCHEMA_FILES, SchemaResolver,
    check_coverage, convert, load_input, load_schema, parse_xml, serialize,
    verify_projection,
)

REPOSITORY = Path(__file__).resolve().parents[2]
SCHEMA_PATH = Path(os.environ.get("BIC_SCHEMA_PACKAGE", "/tmp/ed807-UFEBS_v2026_09_0.zip"))
SOURCE_PATH = Path(os.environ.get("BIC_SOURCE_XML", REPOSITORY / "data/ed807/20261008_ED807_full.xml"))
SOURCE_HASH = "b28862aa26ce5063846d7231477b611947afd91bef0c5707f3a26fd8382be779"
TIME = "2026-10-08T00:00:00Z"


def synthetic(participants=1):
    root = etree.Element("{" + NS + "}ED807", nsmap={None: NS}, EDNo="1", EDDate="2026-10-08", EDAuthor="0000000001", CreationReason="FCBD", CreationDateTime=TIME, InfoTypeCode="FIRR", BusinessDay="2026-10-08", DirectoryVersion="1")
    for i in range(participants):
        entry = etree.SubElement(root, "{" + NS + "}BICDirectoryEntry", BIC=f"{i + 1:09d}")
        etree.SubElement(entry, "{" + NS + "}ParticipantInfo", NameP="SYNTHETIC TEST ONLY", UID=f"{i + 1:010d}", Rgn="01", DateIn="2026-10-08", PtType="20", Srvcs="1", XchType="1")
    return root


def account(entry, number="00000A00000000000000", target="000000001"):
    return etree.SubElement(entry, "{" + NS + "}Accounts", Account=number, RegulationAccountType="CRSA", AccountCBRBIC=target, DateIn="2026-10-08")


class InputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def xml(self, raw):
        p = self.directory / "test.xml"
        p.write_bytes(raw)
        return p

    def archive(self, entries, compression=zipfile.ZIP_STORED):
        p = self.directory / "test.zip"
        with zipfile.ZipFile(p, "w", compression=compression) as z:
            for name, value in entries:
                z.writestr(name, value)
        return p

    def test_xml_hash_and_preservation(self):
        raw = b"<test/>"
        p = self.xml(raw)
        self.assertEqual(load_input(p).artifact["xmlSha256"], sha256(raw).hexdigest())
        self.assertEqual(p.read_bytes(), raw)
        with self.assertRaises(ConversionError):
            load_input(p, expected_sha256="0" * 64)

    def test_zip_xml_identity_and_no_extraction(self):
        raw = b"<test/>"
        p = self.archive([("directory/test.xml", raw)])
        before = p.read_bytes()
        self.assertEqual(load_input(p).xml, raw)
        self.assertEqual(load_input(p).artifact["archiveSha256"], sha256(before).hexdigest())
        self.assertEqual(p.read_bytes(), before)
        self.assertFalse((self.directory / "directory").exists())

    def test_unsafe_paths(self):
        for name in ["../test.xml", "/test.xml", "C:/test.xml", "a\\test.xml", "a/./test.xml", "a//test.xml"]:
            with self.subTest(name=name), self.assertRaises(ConversionError):
                load_input(self.archive([(name, b"<test/>")]))

    def test_symlink(self):
        info = zipfile.ZipInfo("test.xml")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaises(ConversionError):
            load_input(self.archive([(info, b"/etc/passwd")]))

    def test_ambiguous_archives(self):
        for entries in [[("a.xml", b"x"), ("b.xml", b"x")], [("readme.txt", b"x")]]:
            with self.assertRaises(ConversionError):
                load_input(self.archive(entries))

    def test_duplicate_member_names(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            p = self.archive([("test.xml", b"x"), ("test.xml", b"x")])
        with self.assertRaises(ConversionError):
            load_input(p)

    def test_crc_and_truncation(self):
        p = self.archive([("test.xml", b"<SYNTHETIC_TEST/>")])
        raw = p.read_bytes()
        p.write_bytes(raw.replace(b"SYNTHETIC_TEST", b"SYNTHETIC_FAIL"))
        with self.assertRaises(ConversionError):
            load_input(p)
        p.write_bytes(raw[:20])
        with self.assertRaises(ConversionError):
            load_input(p)

    def test_compression_and_encryption(self):
        with self.assertRaises(ConversionError):
            load_input(self.archive([("test.xml", b"x")], zipfile.ZIP_BZIP2))
        p = self.archive([("test.xml", b"x")])
        raw = bytearray(p.read_bytes())
        central = raw.index(b"PK\x01\x02")
        raw[6] |= 1
        raw[central + 8] |= 1
        p.write_bytes(raw)
        with self.assertRaises(ConversionError):
            load_input(p)

    def test_invalid_deflate_and_directory_payload(self):
        p = self.archive([("test.xml", b"TEST" * 100)], zipfile.ZIP_DEFLATED)
        raw = bytearray(p.read_bytes())
        data_start = 30 + len("test.xml")
        raw[data_start] = 0xff
        p.write_bytes(raw)
        with self.assertRaises(ConversionError):
            load_input(p)
        with self.assertRaises(ConversionError):
            load_input(self.archive([("directory/", b"payload"), ("test.xml", b"x")]))

    def test_limits(self):
        with self.assertRaises(ConversionError):
            load_input(self.xml(b"abcd"), Limits(xml_bytes=3))
        p = self.archive([("test.xml", b"a" * 1024)], zipfile.ZIP_DEFLATED)
        for limits in [Limits(zip_bytes=2), Limits(zip_entries=0), Limits(decompressed_bytes=512), Limits(xml_bytes=512)]:
            with self.subTest(limits=limits), self.assertRaises(ConversionError):
                load_input(p, limits)


class ParserTests(unittest.TestCase):
    def test_dtd_entities_encodings(self):
        documents = ['<!DOCTYPE a><a/>', '<!DOCTYPE a SYSTEM "http://127.0.0.1:1/x"><a/>', '<!DOCTYPE a [<!ENTITY e SYSTEM "file:///etc/passwd">]><a>&e;</a>', '<!DOCTYPE a [<!ENTITY e "TEST">]><a>&e;</a>']
        for text in documents:
            for encoding in ["utf-8", "utf-16"]:
                raw = (f'<?xml version="1.0" encoding="{encoding}"?>' + text).encode(encoding)
                with self.subTest(encoding=encoding, text=text), self.assertRaises(ConversionError) as cm:
                    parse_xml(raw)
                self.assertEqual(cm.exception.diagnostics[0].code, "DTD_FORBIDDEN")

    def test_malformed_xml(self):
        with self.assertRaises(ConversionError):
            parse_xml(b"<a><b></a>")

    def test_depth_and_bytes(self):
        with self.assertRaises(ConversionError):
            parse_xml(b"<a><b><c/></b></a>", Limits(depth=2))
        self.assertEqual(parse_xml(b"<a><b/></a>", Limits(depth=2)).tag, "a")
        with self.assertRaises(ConversionError):
            parse_xml(b"<a/>", Limits(xml_bytes=3))

    def test_external_schema_resolver(self):
        resolver = SchemaResolver({name: b"test" for name in SCHEMA_FILES})
        for url in ["file:///etc/passwd", "https://cbr.ru/schema.xsd", BASE_URL + "../secret", BASE_URL + "unknown.xsd"]:
            with self.assertRaises(ConversionError):
                resolver.resolve(url, None, None)

    def test_schema_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "schema.zip"
            p.write_bytes(b"not official")
            with self.assertRaises(ConversionError) as cm:
                load_schema(p)
            self.assertEqual(cm.exception.diagnostics[0].code, "SCHEMA_CHECKSUM")

    def test_timestamp(self):
        self.assertEqual(utc_timestamp(TIME), TIME)
        for invalid in ["today", "2026-02-30T00:00:00Z", "2026-10-08T00:00:00+00:00"]:
            with self.assertRaises(argparse.ArgumentTypeError):
                utc_timestamp(invalid)


class OfficialSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SCHEMA_PATH.is_file():
            raise unittest.SkipTest("Set BIC_SCHEMA_PACKAGE to the official local archive")
        cls.schema = load_schema(SCHEMA_PATH)

    def run_conversion(self, root):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "synthetic.xml"
            p.write_bytes(etree.tostring(root, encoding="windows-1251", xml_declaration=True))
            return convert(load_input(p), self.schema, TIME)

    def test_full_firr_and_no_accounts(self):
        result = self.run_conversion(synthetic())
        p = result.payload["participants"][0]
        self.assertEqual(p["BIC"], "000000001")
        self.assertEqual(p["ParticipantInfo"]["UID"], "0000000001")
        self.assertEqual(p["Accounts"], [])
        self.assertEqual(p["SWBICS"], [])
        self.assertEqual(p["ParticipantInfo"]["RstrList"], [])
        self.assertIn("NO_ACCOUNTS", [d.code for d in result.diagnostics])

    def test_xsd_invalid(self):
        root = synthetic()
        del root[0][0].attrib["UID"]
        with self.assertRaises(ConversionError) as cm:
            self.run_conversion(root)
        self.assertEqual(cm.exception.exit_code, 30)
        root = synthetic()
        root[0][0].set("NameP", "")
        with self.assertRaises(ConversionError):
            self.run_conversion(root)

    def test_profiles(self):
        for change in ["sir", "historic", "multipart", "namespace"]:
            root = synthetic()
            if change == "sir": root.set("InfoTypeCode", "SIRR")
            if change == "historic": del root.attrib["BusinessDay"]
            if change == "multipart": etree.SubElement(root, "{" + NS + "}PartInfo", PartNo="1", PartQuantity="2", PartAggregateID="1")
            if change == "namespace": root.tag = "{urn:unsupported}ED807"
            with self.subTest(change=change), self.assertRaises(ConversionError) as cm:
                self.run_conversion(root)
            self.assertEqual(cm.exception.exit_code, 40)

    def test_optional_fields_and_restrictions(self):
        root = synthetic()
        root.set("EDReceiver", "0000000002")
        root[0].set("ChangeType", "NCNG")
        info = root[0][0]
        info.set("NameP", "  ТЕСТ  ")
        info.set("DateOut", "2026-10-09")
        etree.SubElement(info, "{" + NS + "}RstrList", Rstr="URRS", RstrDate="2026-10-08")
        etree.SubElement(root[0], "{" + NS + "}SWBICS", SWBIC="TESTXX00", DefaultSWBIC="true")
        a = account(root[0]); a.set("CK", "01"); a.set("AccountStatus", "ACAC")
        etree.SubElement(a, "{" + NS + "}AccRstrList", AccRstr="SDRS", AccRstrDate="2026-10-08", SuccessorBIC="000000099")
        p = self.run_conversion(root).payload["participants"][0]
        self.assertEqual(p["ParticipantInfo"]["NameP"], "  ТЕСТ  ")
        self.assertNotIn("RegN", p["ParticipantInfo"])
        self.assertEqual(p["SWBICS"][0]["DefaultSWBIC"], "true")
        self.assertEqual(p["Accounts"][0]["CK"], "01")
        self.assertEqual(p["Accounts"][0]["AccRstrList"][0]["SuccessorBIC"], "000000099")
        self.assertEqual(p["ParticipantInfo"]["RstrList"][0]["Rstr"], "URRS")

    def test_initial_ed(self):
        root = synthetic()
        initial = etree.Element("{" + NS + "}InitialED", EDNo="1", EDDate="2026-10-08", EDAuthor="0000000001")
        root.insert(0, initial)
        result = self.run_conversion(root)
        self.assertEqual(result.payload["metadata"]["source"]["document"]["InitialED"], dict(initial.attrib))

    def test_duplicate_accounts_source_order(self):
        root = synthetic(2)
        account(root[0]); account(root[0]); account(root[1])
        result = self.run_conversion(root)
        self.assertEqual(result.counts["accountCount"], 3)
        self.assertEqual(len(result.payload["participants"][0]["Accounts"]), 2)
        self.assertEqual([p["BIC"] for p in result.payload["participants"]], ["000000001", "000000002"])
        self.assertIn("REPEATED_ACCOUNTS", [d.code for d in result.diagnostics])

    def test_duplicate_bic_uid_and_cycles(self):
        root = synthetic(2)
        root[1].set("BIC", root[0].get("BIC"))
        with self.assertRaises(ConversionError) as cm:
            self.run_conversion(root)
        self.assertIn("DUPLICATE_BIC", [d.code for d in cm.exception.diagnostics])
        root = synthetic(2); root[1][0].set("UID", root[0][0].get("UID"))
        self.assertIn("DUPLICATE_UID", [d.code for d in self.run_conversion(root).diagnostics])
        root[0][0].set("PrntBIC", "000000002"); root[1][0].set("PrntBIC", "000000001")
        with self.assertRaises(ConversionError) as cm:
            self.run_conversion(root)
        self.assertIn("PARENT_CYCLE", [d.code for d in cm.exception.diagnostics])

    def test_unresolved_reference_and_unknown_code(self):
        root = synthetic(); account(root[0], target="000000099")
        root[0][0].set("PtType", "ZZ")
        result = self.run_conversion(root)
        warnings = [d.code for d in result.diagnostics if d.severity == "WARNING"]
        self.assertIn("UNRESOLVED_REFERENCE", warnings)
        self.assertIn("UNKNOWN_CODE_DESCRIPTION", warnings)
        self.assertEqual(result.payload["participants"][0]["Accounts"][0]["AccountCBRBIC"], "000000099")

    def test_unknown_fields_and_mismatch(self):
        root = synthetic(); root[0][0].set("Invented", "test")
        with self.assertRaises(ConversionError): self.run_conversion(root)
        root = synthetic(); etree.SubElement(root[0], "{" + NS + "}Invented")
        with self.assertRaises(ConversionError): check_coverage(root)
        with self.assertRaises(ConversionError): verify_projection(synthetic()[0][0], {"UID": 1})

    def test_invalid_metadata_and_count_mismatch(self):
        root = synthetic()
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "test.xml"
            p.write_bytes(etree.tostring(root))
            with self.assertRaises(ConversionError):
                convert(load_input(p), self.schema, "not a timestamp")
        from bic.core import project
        record = project(root[0])
        record["ParticipantInfo"]["RstrList"] = []
        etree.SubElement(root[0][0], "{" + NS + "}RstrList", Rstr="URRS", RstrDate="2026-10-08")
        with self.assertRaises(ConversionError) as cm:
            verify_projection(root[0], record)
        self.assertEqual(cm.exception.diagnostics[0].code, "COUNT_MISMATCH")

    def test_serialization(self):
        result = self.run_conversion(synthetic())
        first = serialize(result.payload)
        self.assertEqual(first, serialize(self.run_conversion(synthetic()).payload))
        self.assertTrue(first.endswith(b"\n")); self.assertFalse(first.endswith(b"\n\n"))
        self.assertFalse(first.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(serialize({"b": "ТЕСТ", "a": "01"}), b'{"a":"01","b":"\xd0\xa2\xd0\x95\xd0\xa1\xd0\xa2"}\n')
        for value in [float("nan"), float("inf")]:
            with self.assertRaises(ValueError): serialize({"value": value})

    def test_staging_and_write_failure(self):
        result = self.run_conversion(synthetic())
        with tempfile.TemporaryDirectory() as directory:
            summary = write_result(result, directory)
            output = Path(summary["output"])
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertTrue((output.parent / "COMPLETE").is_file())
            self.assertEqual(output.read_bytes(), serialize(result.payload))
            with patch("bic.cli.os.fsync", side_effect=OSError("synthetic failure")), self.assertRaises(ConversionError):
                write_result(result, directory)
            self.assertEqual(sum(p.name == "COMPLETE" for p in Path(directory).rglob("COMPLETE")), 1)
        with self.assertRaises(ConversionError): staging_directory(REPOSITORY)
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o755)
            with self.assertRaises(ConversionError): staging_directory(directory)

    def test_cli_process_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "test.xml"; p.write_bytes(etree.tostring(synthetic()))
            command = [sys.executable, "-m", "bic", "convert", "--input", str(p), "--schema-package", str(SCHEMA_PATH), "--staging", directory, "--converted-at", TIME]
            a = subprocess.run(command, capture_output=True, check=True)
            b = subprocess.run(command, capture_output=True, check=True)
            self.assertEqual(json.loads(a.stdout)["outputSha256"], json.loads(b.stdout)["outputSha256"])
            for target, value in [
                ("bic.cli.sys.version_info", (3, 13, 10)),
                ("bic.cli.sys.version_info", (3, 14, 9)),
                ("bic.cli.etree.LXML_VERSION", (6, 0, 2, 0)),
            ]:
                wrapper = ("import sys; from unittest.mock import patch; from bic.cli import main\n"
                           f"with patch({target!r}, {value!r}):\n"
                           "    raise SystemExit(main(sys.argv[1:]))\n")
                with self.subTest(runtime=target, value=value):
                    rejected = subprocess.run([sys.executable, "-c", wrapper, *command[3:]], capture_output=True)
                    self.assertEqual(rejected.returncode, 10)
                    self.assertEqual(json.loads(rejected.stdout)["codes"], ["RUNTIME"])
            wrapper = ("import sys; from unittest.mock import patch; from bic.cli import main\n"
                       "with patch('bic.cli._hashlib.get_fips_mode', return_value=1):\n"
                       "    raise SystemExit(main(sys.argv[1:]))\n")
            rejected = subprocess.run([sys.executable, "-c", wrapper, *command[3:]], capture_output=True)
            self.assertEqual(rejected.returncode, 10)
            self.assertEqual(json.loads(rejected.stdout)["codes"], ["RUNTIME"])
            p.write_bytes(b"<!DOCTYPE a><a/>")
            failure = subprocess.run(command, capture_output=True)
            self.assertEqual(failure.returncode, 20)
            self.assertEqual(json.loads(failure.stdout)["status"], "failed")

    def test_local_integration_regression(self):
        if not SOURCE_PATH.is_file():
            self.skipTest("Local original ED807 XML not supplied")
        original = SOURCE_PATH.read_bytes()
        self.assertEqual(sha256(original).hexdigest(), SOURCE_HASH)
        source = load_input(SOURCE_PATH, expected_sha256=SOURCE_HASH)
        result = convert(source, self.schema, TIME)
        self.assertEqual(result.counts, {"participantCount": 1382, "accountCount": 1339, "participantsWithoutAccounts": 199, "swbicsCount": 288, "participantRestrictionCount": 294, "accountRestrictionCount": 71})
        self.assertEqual(sum(d.code == "UNRESOLVED_REFERENCE" for d in result.diagnostics), 1)
        self.assertEqual(SOURCE_PATH.read_bytes(), original)
        archive = SOURCE_PATH.parent / "20261008ED01OSBR.zip"
        if archive.exists():
            self.assertEqual(load_input(archive).xml, source.xml)


if __name__ == "__main__":
    unittest.main()

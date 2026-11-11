import _hashlib
import argparse
import json
import os
import re
import resource
import signal
import sys
import tempfile
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from lxml import etree

from .core import ConversionError, convert, load_input, load_schema, serialize


def utc_timestamp(value):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise argparse.ArgumentTypeError("Требуется UTC-время YYYY-MM-DDTHH:MM:SSZ.")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Некорректная дата UTC.") from exc
    return value


def staging_directory(path):
    original = Path(path).absolute()
    resolved = original.resolve()
    repository = Path(__file__).resolve().parents[3]
    if resolved.is_relative_to(repository) or original != resolved:
        raise ConversionError("STAGING_PATH", "Staging должен быть вне репозитория и без символьных ссылок.", 60)
    if not resolved.is_dir() or resolved.stat().st_uid != os.getuid() or resolved.stat().st_mode & 0o077:
        raise ConversionError("STAGING_PERMISSIONS", "Требуется существующий staging-каталог владельца с правами 0700.", 60)
    return resolved


def write_result(result, directory):
    directory = staging_directory(directory)
    data = serialize(result.payload)
    digest = sha256(data).hexdigest()
    run = Path(tempfile.mkdtemp(prefix="ed807-", dir=directory))
    files = {
        "candidate.json": data,
        "diagnostics.json": serialize({"sourceXmlSha256": result.payload["metadata"]["source"]["artifact"]["xmlSha256"], "counts": result.counts, "diagnostics": [asdict(d) for d in result.diagnostics]}),
    }
    try:
        for name, content in files.items():
            descriptor = os.open(run / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        # Маркер завершения появляется только после записи обоих файлов.
        descriptor = os.open(run / "COMPLETE.tmp", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(digest + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(run / "COMPLETE.tmp", run / "COMPLETE")
    except OSError as exc:
        raise ConversionError("STAGING_IO", "Запись staging не завершена; COMPLETE отсутствует.", 60) from exc
    return {"status": "candidate-ready", "output": str(run / "candidate.json"), "diagnostics": str(run / "diagnostics.json"), "outputBytes": len(data), "outputSha256": digest, "counts": result.counts}


def deadline(signum, frame):
    raise ConversionError("RESOURCE_LIMIT", "Превышен лимит времени 120 секунд.", 60)


def main(argv=None):
    arguments = argparse.ArgumentParser(description="Офлайн-конвертер ED807; публикация не выполняется.")
    subcommands = arguments.add_subparsers(dest="command", required=True)
    command = subcommands.add_parser("convert", help="Проверить XML/ZIP и создать закрытый кандидат JSON.")
    command.add_argument("--input", required=True, type=Path)
    command.add_argument("--schema-package", required=True, type=Path)
    command.add_argument("--staging", required=True, type=Path)
    command.add_argument("--converted-at", required=True, type=utc_timestamp)
    command.add_argument("--expected-xml-sha256", type=lambda s: s if re.fullmatch("[0-9a-f]{64}", s) else arguments.error("Требуется SHA-256 в нижнем регистре."))
    options = arguments.parse_args(argv)
    try:
        if (sys.version_info[:2] != (3, 14) or sys.version_info[:3] < (3, 14, 10)
                or etree.LXML_VERSION[:3] != (6, 1, 3) or _hashlib.get_fips_mode()):
            raise ConversionError("RUNTIME", "Требуются CPython 3.14.10 или новее в ветке 3.14, режим non-FIPS и lxml 6.1.3.")
        resource.setrlimit(resource.RLIMIT_AS, (1024 ** 3, 1024 ** 3))
        signal.signal(signal.SIGALRM, deadline)
        signal.alarm(120)
        staging_directory(options.staging)
        source = load_input(options.input, expected_sha256=options.expected_xml_sha256)
        result = convert(source, load_schema(options.schema_package), options.converted_at)
        summary = write_result(result, options.staging)
        for diagnostic in result.diagnostics:
            print(f"{diagnostic.severity} {diagnostic.code}: {diagnostic.message}", file=sys.stderr)
        print(json.dumps(summary, sort_keys=True))
        return 0
    except ConversionError as exc:
        for diagnostic in exc.diagnostics:
            print(f"{diagnostic.severity} {diagnostic.code}: {diagnostic.message}", file=sys.stderr)
        print(json.dumps({"status": "failed", "codes": [d.code for d in exc.diagnostics]}, sort_keys=True))
        return exc.exit_code
    except (OSError, ValueError, MemoryError) as exc:
        print("ERROR CONVERSION: Конвертация не завершена.", file=sys.stderr)
        print(json.dumps({"status": "failed", "codes": ["CONVERSION"]}))
        return 60
    finally:
        signal.alarm(0)

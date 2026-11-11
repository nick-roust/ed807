import io
import json
import os
import stat
import zipfile
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath

from lxml import etree

from . import __version__

NS = "urn:cbr-ru:ed:v2.0"
SCHEMA_VERSION = "2026.09.0"
SCHEMA_HASH = "3ca5333743462c7ccce34914765c15d45b1f26e3ca227f75f04bce01062e3566"
BASE_URL = "https://schema.invalid/XMLSchemas/ed/"
SCHEMA_FILES = {
    "cbr_ed807_v2026.09.0.xsd": "9b898e49185a52b83603af3bff1d92381f7c8b3e91439be1be0ba1e72098ede5",
    "cbr_ed_objects_v2026.09.0.xsd": "a764939da35c9a884451c9d70ab60504f49635cd684eb74974a18865a2ceae25",
    "cbr_ed_leaftypes_v2026.09.0.xsd": "2a474499dabfa50aece0dbb17747a6258ac3a784462806496f2350a31ff1e6c8",
    "cbr_ed_basetypes_v2018.3.0.xsd": "7fc20aa13386459f73d9b96d6d3df43d0d6b22761eea3c1d152aa6ed233c9b0e",
}
ATTRIBUTES = {
    "ED807": set("EDNo EDDate EDAuthor EDReceiver CreationReason CreationDateTime InfoTypeCode BusinessDay DirectoryVersion".split()),
    "InitialED": set("EDNo EDDate EDAuthor".split()),
    "BICDirectoryEntry": {"BIC", "ChangeType"},
    "ParticipantInfo": set("NameP EnglName RegN CntrCd Rgn Ind Tnp Nnp Adr PrntBIC DateIn DateOut PtType Srvcs XchType UID ParticipantStatus".split()),
    "SWBICS": {"SWBIC", "DefaultSWBIC"},
    "Accounts": set("Account RegulationAccountType CK AccountCBRBIC DateIn DateOut AccountStatus".split()),
    "RstrList": {"Rstr", "RstrDate"},
    "AccRstrList": {"AccRstr", "AccRstrDate", "SuccessorBIC"},
}
CHILDREN = {
    "ED807": {"InitialED", "BICDirectoryEntry"},
    "BICDirectoryEntry": {"ParticipantInfo", "SWBICS", "Accounts"},
    "ParticipantInfo": {"RstrList"},
    "Accounts": {"AccRstrList"},
}


@dataclass(frozen=True)
class Limits:
    xml_bytes: int = 32 * 1024 * 1024
    zip_bytes: int = 16 * 1024 * 1024
    zip_entries: int = 16
    decompressed_bytes: int = 32 * 1024 * 1024
    depth: int = 32


@dataclass(frozen=True)
class Diagnostic:
    severity: str
    code: str
    message: str
    context: dict = field(default_factory=dict)


class ConversionError(Exception):
    def __init__(self, code, message, exit_code=10, diagnostics=None):
        super().__init__(message)
        self.exit_code = exit_code
        self.diagnostics = diagnostics or [Diagnostic("ERROR", code, message)]


def bounded_read(stream, limit):
    data = stream.read(limit + 1)
    if len(data) > limit:
        raise ConversionError("RESOURCE_LIMIT", "Превышен допустимый размер входа.")
    return data


def read_file(path, limit):
    try:
        with Path(path).open("rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ConversionError("INPUT_TYPE", "Требуется обычный локальный файл.")
            return bounded_read(stream, limit)
    except OSError as exc:
        raise ConversionError("INPUT_IO", "Не удалось прочитать локальный файл.") from exc


def safe_member(info):
    name = info.orig_filename
    parts = name.rstrip("/").split("/")
    if (not name or "\x00" in name or "\\" in name or ":" in name
            or PurePosixPath(name).is_absolute()
            or any(p in {"", ".", ".."} for p in parts)):
        raise ConversionError("ZIP_PATH", "Небезопасное имя элемента ZIP.")
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}):
        raise ConversionError("ZIP_MEMBER_TYPE", "Недопустимый тип элемента ZIP.")
    if info.is_dir() and info.file_size:
        raise ConversionError("ZIP_MEMBER_TYPE", "Каталог ZIP не должен содержать данные.")
    if info.flag_bits & 1 or info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
        raise ConversionError("ZIP_COMPRESSION", "Неподдерживаемый элемент ZIP.")


@dataclass(frozen=True)
class Source:
    xml: bytes
    artifact: dict


def load_input(path, limits=Limits(), expected_sha256=None):
    suffix = Path(path).suffix.lower()
    if suffix not in {".xml", ".zip"}:
        raise ConversionError("INPUT_TYPE", "Поддерживаются только локальные XML и ZIP.")
    raw = read_file(path, limits.zip_bytes if suffix == ".zip" else limits.xml_bytes)
    xml = raw
    artifact = {}
    if suffix == ".zip":
        artifact["archiveSha256"] = sha256(raw).hexdigest()
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries = archive.infolist()
                if len(entries) > limits.zip_entries:
                    raise ConversionError("RESOURCE_LIMIT", "Слишком много элементов ZIP.")
                names = set()
                total = 0
                selected = []
                for info in entries:
                    safe_member(info)
                    if info.filename in names:
                        raise ConversionError("ZIP_AMBIGUOUS", "Повторяющиеся имена в ZIP.")
                    names.add(info.filename)
                    total += info.file_size
                    if total > limits.decompressed_bytes:
                        raise ConversionError("RESOURCE_LIMIT", "Превышен размер распакованных данных.")
                    if not info.is_dir() and info.filename.lower().endswith(".xml"):
                        selected.append(info)
                if len(selected) != 1:
                    raise ConversionError("ZIP_AMBIGUOUS", "ZIP должен содержать ровно один XML.")
                actual_total = 0
                for info in entries:
                    if info.is_dir():
                        continue
                    with archive.open(info) as stream:
                        data = bounded_read(stream, limits.decompressed_bytes - actual_total)
                    actual_total += len(data)
                    if info is selected[0]:
                        xml = data
                        artifact["archiveMember"] = info.filename
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError, EOFError, ValueError, zlib.error) as exc:
            raise ConversionError("ZIP_INVALID", "ZIP повреждён или не поддерживается.") from exc
    if len(xml) > limits.xml_bytes:
        raise ConversionError("RESOURCE_LIMIT", "Превышен размер XML.")
    artifact["xmlSha256"] = sha256(xml).hexdigest()
    if expected_sha256 is not None and artifact["xmlSha256"] != expected_sha256:
        raise ConversionError("CHECKSUM", "SHA-256 исходного XML не совпадает.")
    return Source(xml, artifact)


class DenyResolver(etree.Resolver):
    def resolve(self, url, public_id, context):
        raise ConversionError("EXTERNAL_RESOURCE", "Внешние ресурсы XML запрещены.", 20)


class SafetyTarget:
    def __init__(self, depth):
        self.maximum_depth = depth
        self.depth = 0

    def start(self, tag, attributes, nsmap=None):
        self.depth += 1
        if self.depth > self.maximum_depth:
            raise ConversionError("RESOURCE_LIMIT", "Превышена глубина XML.", 20)

    def end(self, tag):
        self.depth -= 1

    def data(self, text):
        pass

    def close(self):
        return None

    def doctype(self, name, public_id, system_id):
        raise ConversionError("DTD_FORBIDDEN", "DTD и объявления сущностей запрещены.", 20)


def parser(resolver, target=None):
    result = etree.XMLParser(
        resolve_entities=False, load_dtd=False, no_network=True,
        attribute_defaults=False, dtd_validation=False, recover=False,
        huge_tree=False, target=target,
    )
    result.resolvers.add(resolver)
    return result


def parse_xml(xml, limits=Limits()):
    if len(xml) > limits.xml_bytes:
        raise ConversionError("RESOURCE_LIMIT", "Превышен размер XML.", 20)
    try:
        # Проверка DTD и глубины идёт до построения рабочего дерева.
        etree.fromstring(xml, parser(DenyResolver(), SafetyTarget(limits.depth)))
        root = etree.fromstring(xml, parser(DenyResolver()))
    except etree.XMLSyntaxError as exc:
        raise ConversionError("XML_INVALID", "XML не прошёл синтаксическую проверку.", 20) from exc
    if root.getroottree().docinfo.doctype or any(isinstance(e, etree._Entity) for e in root.iter()):
        raise ConversionError("DTD_FORBIDDEN", "DTD и сущности запрещены.", 20)
    return root


class SchemaResolver(etree.Resolver):
    def __init__(self, members):
        self.members = members

    def resolve(self, url, public_id, context):
        if not url.startswith(BASE_URL) or url[len(BASE_URL):] not in self.members:
            raise ConversionError("SCHEMA_RESOURCE", "Неизвестная зависимость XSD.", 30)
        return self.resolve_string(self.members[url[len(BASE_URL):]], context, base_url=url)


def load_schema(path):
    raw = read_file(path, 64 * 1024 * 1024)
    if sha256(raw).hexdigest() != SCHEMA_HASH:
        raise ConversionError("SCHEMA_CHECKSUM", "SHA-256 официального пакета XSD не совпадает.", 30)
    try:
        members = {}
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for name, expected in SCHEMA_FILES.items():
                matches = [i for i in archive.infolist() if i.filename == "XMLSchemas/ed/" + name]
                if len(matches) != 1:
                    raise ConversionError("SCHEMA_MEMBER", "Отсутствует однозначная зависимость XSD.", 30)
                with archive.open(matches[0]) as stream:
                    data = bounded_read(stream, 16 * 1024 * 1024)
                if sha256(data).hexdigest() != expected:
                    raise ConversionError("SCHEMA_MEMBER_HASH", "Хеш зависимости XSD не совпадает.", 30)
                members[name] = data
        doc = etree.fromstring(members["cbr_ed807_v2026.09.0.xsd"], parser(SchemaResolver(members)), base_url=BASE_URL + "cbr_ed807_v2026.09.0.xsd")
        return etree.XMLSchema(doc)
    except (KeyError, zipfile.BadZipFile, etree.XMLSyntaxError, etree.XMLSchemaParseError) as exc:
        raise ConversionError("SCHEMA_INVALID", "Не удалось скомпилировать официальный XSD.", 30) from exc


def local_name(element):
    return etree.QName(element).localname


def profile(root):
    if root.tag != "{" + NS + "}ED807" or root.get("InfoTypeCode") != "FIRR":
        raise ConversionError("PROFILE", "Поддерживается только полный ED807 FIRR.", 40)
    if root.find("{" + NS + "}PartInfo") is not None or "BusinessDay" not in root.attrib:
        raise ConversionError("PROFILE", "Multipart и исторические профили не поддерживаются.", 40)


def check_coverage(root):
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        name = local_name(element)
        if etree.QName(element).namespace != NS or name not in ATTRIBUTES:
            raise ConversionError("MAPPING_FIELD", "Неизвестный исходный элемент.", 40)
        if set(element.attrib) - ATTRIBUTES[name]:
            raise ConversionError("MAPPING_FIELD", "Неизвестный исходный атрибут.", 40)
        if element.text and element.text.strip():
            raise ConversionError("MAPPING_TEXT", "Неожиданный текст в исходном элементе.", 40)
        for child in element:
            if child.tail and child.tail.strip():
                raise ConversionError("MAPPING_TEXT", "Неожиданный текст между элементами.", 40)
            if isinstance(child.tag, str) and local_name(child) not in CHILDREN.get(name, set()):
                raise ConversionError("MAPPING_FIELD", "Неизвестная вложенная структура.", 40)


def project(element):
    name = local_name(element)
    record = dict(element.attrib)
    arrays = {"BICDirectoryEntry": ["Accounts", "SWBICS"], "ParticipantInfo": ["RstrList"], "Accounts": ["AccRstrList"]}.get(name, [])
    record.update({a: [] for a in arrays})
    for child in element:
        if not isinstance(child.tag, str):
            continue
        child_name = local_name(child)
        if child_name in arrays:
            record[child_name].append(project(child))
        elif child_name == "ParticipantInfo":
            record[child_name] = project(child)
    return record


def verify_projection(element, record):
    if any(record.get(k) != v or not isinstance(record.get(k), str) for k, v in element.attrib.items()):
        raise ConversionError("MAPPING_MISMATCH", "Изменено исходное значение.", 50)
    groups = defaultdict(list)
    for child in element:
        if isinstance(child.tag, str):
            groups[local_name(child)].append(child)
    for name, children in groups.items():
        if name not in record:
            raise ConversionError("MAPPING_MISMATCH", "Отсутствует вложенная исходная структура.", 50)
        mapped = record[name] if isinstance(record[name], list) else [record[name]]
        if len(children) != len(mapped):
            raise ConversionError("COUNT_MISMATCH", "Потеряны исходные записи.", 50)
        for child, value in zip(children, mapped, strict=True):
            verify_projection(child, value)


def integrity(participants):
    diagnostics = []
    by_bic = defaultdict(list)
    uids = Counter()
    accounts = Counter()
    def add(severity, code, message, **context):
        diagnostics.append(Diagnostic(severity, code, message, context))
    for i, p in enumerate(participants):
        by_bic[p["BIC"]].append(i)
        uids[p["ParticipantInfo"]["UID"]] += 1
        accounts.update(a["Account"] for a in p["Accounts"])
    for bic, positions in by_bic.items():
        if len(positions) > 1:
            add("ERROR", "DUPLICATE_BIC", "Повторяющийся BIC.", BIC=bic, occurrences=len(positions))
    for uid, count in uids.items():
        if count > 1:
            add("WARNING", "DUPLICATE_UID", "Повторяющийся UID.", UID=uid, occurrences=count)
    repeated = sum(n - 1 for n in accounts.values() if n > 1)
    if repeated:
        add("INFO", "REPEATED_ACCOUNTS", "Повторяющиеся номера счетов сохранены.", additionalOccurrences=repeated)
    empty = sum(not p["Accounts"] for p in participants)
    if empty:
        add("INFO", "NO_ACCOUNTS", "Участники без счетов сохранены.", participantCount=empty)
    parents = {}
    for i, p in enumerate(participants):
        info = p["ParticipantInfo"]
        references = [("PrntBIC", info["PrntBIC"])] if "PrntBIC" in info else []
        for j, a in enumerate(p["Accounts"]):
            references.append((f"Accounts[{j}].AccountCBRBIC", a["AccountCBRBIC"]))
            references.extend((f"Accounts[{j}].AccRstrList[{k}].SuccessorBIC", r["SuccessorBIC"]) for k, r in enumerate(a["AccRstrList"]) if "SuccessorBIC" in r)
        for field_name, target in references:
            if len(by_bic.get(target, [])) != 1:
                add("WARNING", "UNRESOLVED_REFERENCE", "Ссылка не разрешена однозначно.", participantIndex=i, field=field_name, target=target)
        if "PrntBIC" in info and len(by_bic.get(info["PrntBIC"], [])) == 1:
            parents[i] = by_bic[info["PrntBIC"]][0]
    done = set()
    for start in parents:
        seen = set()
        cursor = start
        while cursor in parents and cursor not in done:
            if cursor in seen:
                add("ERROR", "PARENT_CYCLE", "Обнаружен цикл родительских ссылок.", participantIndex=cursor)
                break
            seen.add(cursor)
            cursor = parents[cursor]
        done.update(seen)
    return diagnostics


def code_diagnostics(root):
    # Наборы описанных кодов взяты из официальных таблиц, не из частот выборки.
    known = {
        "CreationReason": {"RQST", "CIBD", "FCBD"},
        "InfoTypeCode": {"FIRR", "SIRR"},
        "ChangeType": {"ADDD", "CHGD", "DLTD"},
        "PtType": set("00 10 12 15 16 20 30 40 51 52 60 65 71 75 78 90 99".split()),
        "Srvcs": set("1 2 3 4 5 6".split()), "XchType": {"0", "1"},
        "RegulationAccountType": set("CBRA BANA CRSA TRSA TRUA UTRA CLAC CBDC".split()),
        "ParticipantStatus": {"PSAC", "PSDL"}, "AccountStatus": {"ACAC", "ACDL"},
        "Rstr": set("URRS LWRS MRTR RSIP FPIP FOCL".split()),
        "AccRstr": set("URRS CLRS LMRS FPRS SDRS SCRS".split()),
    }
    values = defaultdict(set)
    for element in root.iter():
        if isinstance(element.tag, str):
            for name, allowed in known.items():
                if name in element.attrib and element.get(name) not in allowed:
                    values[name].add(element.get(name))
    return [Diagnostic("WARNING", "UNKNOWN_CODE_DESCRIPTION", "Код не имеет проверенного описания в локальном реестре.", {"field": name, "value": value}) for name in sorted(values) for value in sorted(values[name])]


def serialize(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


@dataclass(frozen=True)
class Result:
    payload: dict
    diagnostics: list
    counts: dict


def convert(source, schema, converted_at, limits=Limits()):
    try:
        parsed_time = datetime.strptime(converted_at, "%Y-%m-%dT%H:%M:%SZ")
        if parsed_time.strftime("%Y-%m-%dT%H:%M:%SZ") != converted_at:
            raise ValueError("Noncanonical UTC timestamp")
    except (TypeError, ValueError) as exc:
        raise ConversionError("METADATA", "Требуется фиксированное время UTC.", 60) from exc
    root = parse_xml(source.xml, limits)
    profile(root)
    check_coverage(root)
    if not schema.validate(root):
        diagnostics = [Diagnostic("ERROR", "XSD_INVALID", "Документ не соответствует официальному XSD.", {"line": e.line, "type": e.type_name}) for e in list(schema.error_log)[:100]]
        raise ConversionError("XSD_INVALID", "Документ не соответствует XSD.", 30, diagnostics)
    entries = root.findall("{" + NS + "}BICDirectoryEntry")
    participants = [project(e) for e in entries]
    for e, p in zip(entries, participants, strict=True):
        verify_projection(e, p)
    counts = {"participantCount": len(participants), "accountCount": sum(len(p["Accounts"]) for p in participants)}
    regression = dict(counts)
    regression.update({
        "participantsWithoutAccounts": sum(not p["Accounts"] for p in participants),
        "swbicsCount": sum(len(p["SWBICS"]) for p in participants),
        "participantRestrictionCount": sum(len(p["ParticipantInfo"]["RstrList"]) for p in participants),
        "accountRestrictionCount": sum(len(a["AccRstrList"]) for p in participants for a in p["Accounts"]),
    })
    diagnostics = integrity(participants) + code_diagnostics(root)
    if any(d.severity == "ERROR" for d in diagnostics):
        raise ConversionError("INTEGRITY", "Проверка целостности не пройдена.", 50, diagnostics)
    docinfo = root.getroottree().docinfo
    document = {"rootElement": "ED807", "namespace": NS, "xmlVersion": docinfo.xml_version, "attributes": dict(root.attrib)}
    initial = root.find("{" + NS + "}InitialED")
    if initial is not None:
        document["InitialED"] = dict(initial.attrib)
    artifact = dict(source.artifact, encoding=docinfo.encoding)
    payload = {"format": "roust.bic.ed807", "metadata": {
        "publicSchemaVersion": "1.0.0",
        "source": {"organization": "Bank of Russia", "acquisition": {"mode": "manual-import", "requestedUrl": None, "resolvedUrl": None, "downloadedAt": None}, "artifact": artifact, "document": document},
        "processing": {"converterVersion": __version__, "convertedAt": converted_at, "xsdVersion": SCHEMA_VERSION, "xsdPackageSha256": SCHEMA_HASH},
        "publication": {"publishedAt": None}, "counts": counts,
    }, "participants": participants}
    return Result(payload, diagnostics, regression)

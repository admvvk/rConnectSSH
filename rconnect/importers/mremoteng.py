"""Import connections from a mRemoteNG confCons.xml export.

Format (confirmed against this project's actual export, ConfVersion 2.6,
EncryptionEngine="AES", BlockCipherMode="GCM", KdfIterations="1000"):
  - Each encrypted field (the root `Protected` attribute, and each
    Connection node's `Password` attribute) is base64 of:
        salt (16 bytes) || nonce (16 bytes) || ciphertext || tag (16 bytes)
  - Key = PBKDF2-HMAC-SHA1(passphrase, salt, iterations, dklen=32)
  - AES-GCM decrypt(nonce, ciphertext+tag, aad=salt) — the salt doubles as
    the GCM associated data; omitting it is the one easy way to get this
    wrong (it decrypts/authenticates fine structurally but always raises
    InvalidTag).
  - passphrase is "mR3m" (mRemoteNG's hardcoded default) unless the user
    set a custom master password in mRemoteNG's Tools > Options > Security.

Reference implementations consulted (both public, MIT/unlicensed-style
scripts floating around for this exact format):
  https://github.com/gquere/mRemoteNG_password_decrypt
  https://github.com/kmahyyg/mremoteng-decrypt
"""
from __future__ import annotations

import base64
import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from rconnect.models import Connection, Group, Protocol

DEFAULT_PASSPHRASE = "mR3m"

# mRemoteNG's Protocol attribute values we can represent. SSH is the only
# protocol this app supports; everything else (RDP, VNC, Telnet, HTTP/
# HTTPS, ICA, RAW, Rlogin, IntApp, ...) has no equivalent client wired up
# in launchers.py, so those connections are reported as warnings and
# skipped rather than silently mis-imported.
_PROTOCOL_MAP = {
    "SSH1": Protocol.SSH,
    "SSH2": Protocol.SSH,
}


class MRemoteNGImportError(RuntimeError):
    pass


def decrypt_field(enc_b64: str, passphrase: str, iterations: int = 1000) -> bytes:
    """Decrypt one AES-GCM encrypted field from a confCons.xml. Raises
    InvalidTag (from `cryptography`) if the passphrase is wrong.
    """
    raw = base64.b64decode(enc_b64)
    if len(raw) < 32:
        raise MRemoteNGImportError(f"encrypted field too short ({len(raw)} bytes)")
    salt, nonce, ct_and_tag = raw[:16], raw[16:32], raw[32:]
    key = hashlib.pbkdf2_hmac("sha1", passphrase.encode("utf-8"), salt, iterations, dklen=32)
    return AESGCM(key).decrypt(nonce, ct_and_tag, salt)


def verify_passphrase(xml_root: ET.Element, passphrase: str) -> bool:
    """Checks the file's `Protected` sentinel value, the same check
    mRemoteNG itself does at load time, without needing any real
    connection's password to be present.
    """
    protected = xml_root.attrib.get("Protected")
    if not protected:
        return True  # nothing to check against; assume OK
    iterations = int(xml_root.attrib.get("KdfIterations", "1000"))
    try:
        decrypt_field(protected, passphrase, iterations)
        return True
    except (InvalidTag, MRemoteNGImportError):
        return False


@dataclass
class ImportResult:
    root: Group
    group_count: int = 0
    connection_count: int = 0
    warnings: list[str] = field(default_factory=list)


def _import_node(xml_node: ET.Element, passphrase: str, iterations: int, result: ImportResult, path: str) -> object | None:
    name = xml_node.attrib.get("Name", "(unnamed)")
    node_type = xml_node.attrib.get("Type")
    node_path = f"{path}/{name}"

    if node_type == "Container":
        group = Group(name=name)
        result.group_count += 1
        for child in xml_node.findall("Node"):
            child_obj = _import_node(child, passphrase, iterations, result, node_path)
            if isinstance(child_obj, Group):
                group.subgroups.append(child_obj)
            elif isinstance(child_obj, Connection):
                group.connections.append(child_obj)
        return group

    if node_type == "Connection":
        proto_raw = xml_node.attrib.get("Protocol", "")
        protocol = _PROTOCOL_MAP.get(proto_raw)
        if protocol is None:
            result.warnings.append(f"{node_path}: unsupported protocol '{proto_raw}', skipped")
            return None

        password = ""
        enc_password = xml_node.attrib.get("Password", "")
        if enc_password:
            try:
                password = decrypt_field(enc_password, passphrase, iterations).decode("utf-8")
            except (InvalidTag, MRemoteNGImportError, UnicodeDecodeError) as exc:
                result.warnings.append(f"{node_path}: could not decrypt password ({exc}), left blank")

        port_raw = xml_node.attrib.get("Port", "")
        try:
            port = int(port_raw) if port_raw else None
        except ValueError:
            port = None

        result.connection_count += 1
        return Connection(
            name=name,
            protocol=protocol,
            host=xml_node.attrib.get("Hostname", ""),
            port=port,
            username=xml_node.attrib.get("Username", ""),
            password=password,
        )

    result.warnings.append(f"{node_path}: unknown Node Type '{node_type}', skipped")
    return None


def import_file(xml_path: str, passphrase: str = DEFAULT_PASSPHRASE) -> ImportResult:
    """Parses a mRemoteNG confCons.xml export into a Group tree.

    Does not touch any existing rconnect storage — caller decides whether
    and where to merge `result.root`'s subgroups/connections into the
    live tree, then calls save().
    """
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError as exc:
        raise MRemoteNGImportError(f"not a valid XML file: {exc}") from exc
    xml_root = tree.getroot()

    if xml_root.attrib.get("FullFileEncryption") == "true":
        raise MRemoteNGImportError(
            "this file uses full-file encryption, which is not supported yet "
            "(only per-field password encryption)"
        )

    if not verify_passphrase(xml_root, passphrase):
        raise MRemoteNGImportError("wrong master password (or a non-default encryption scheme)")

    iterations = int(xml_root.attrib.get("KdfIterations", "1000"))
    result = ImportResult(root=Group(name=xml_root.attrib.get("Name", "Imported")))
    for child in xml_root.findall("Node"):
        child_obj = _import_node(child, passphrase, iterations, result, result.root.name)
        if isinstance(child_obj, Group):
            result.root.subgroups.append(child_obj)
        elif isinstance(child_obj, Connection):
            result.root.connections.append(child_obj)
    return result

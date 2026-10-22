import base64
import copy
import logging
import re
import threading
import time
import uuid
import zlib
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlsplit, quote, urlencode

from lxml import etree
from signxml import XMLVerifier

from core.config import app_url, env

NS = {
    "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
    "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
    "md": "urn:oasis:names:tc:SAML:2.0:metadata",
}
GUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
log = logging.getLogger("talentscope")
CLOCK_SKEW = timedelta(seconds=60)
METADATA_TTL_S = 3600
METADATA_TIMEOUT_S = 8
METADATA_MAX_BYTES = 1_000_000
METADATA_HOSTS = ("login.microsoftonline.com", "login.microsoftonline.us", "login.microsoft.com", "login.windows.net")
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
STATUS_SUCCESS = "urn:oasis:names:tc:SAML:2.0:status:Success"
DEFAULT_EMAIL_ATTRIBUTES = [
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn",
    "http://schemas.microsoft.com/identity/claims/emailaddress",
    "email",
    "mail",
    "upn",
]


class SamlError(Exception):
    pass


_seen_ids: dict[str, float] = {}
_seen_lock = threading.Lock()


def _unescape_newlines(value: str) -> str:
    return value.replace("\\n", "\n")


def _strip_cert(value: str) -> str:
    cleaned = _unescape_newlines(value)
    cleaned = cleaned.replace("-----BEGIN CERTIFICATE-----", "").replace("-----END CERTIFICATE-----", "")
    return re.sub(r"\s+", "", cleaned)


def cert_to_pem(body: str) -> str:
    lines = [body[i:i + 64] for i in range(0, len(body), 64)]
    return "-----BEGIN CERTIFICATE-----\n" + "\n".join(lines) + "\n-----END CERTIFICATE-----\n"


def split_certs(value: str) -> list[str]:
    return [cert for cert in (_strip_cert(part) for part in re.split(r"[|,;]", _unescape_newlines(value))) if cert]


_metadata: dict = {"url": "", "at": 0.0, "certs": [], "error": ""}
_metadata_lock = threading.Lock()


def _metadata_url_ok(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme == "https" and (parts.hostname or "") in METADATA_HOSTS and not parts.username


def parse_metadata_certs(xml: bytes) -> list[str]:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)
    root = etree.fromstring(xml, parser)
    certs = []
    for key in root.iter("{urn:oasis:names:tc:SAML:2.0:metadata}KeyDescriptor"):
        if key.get("use") == "encryption":
            continue
        for node in key.iter("{http://www.w3.org/2000/09/xmldsig#}X509Certificate"):
            body = re.sub(r"\s+", "", node.text or "")
            if body and body not in certs:
                certs.append(body)
    return certs


def metadata_certs(url: str) -> tuple[list[str], str]:
    if not url:
        return [], ""
    with _metadata_lock:
        fresh = _metadata["url"] == url and time.monotonic() - _metadata["at"] < METADATA_TTL_S
        if fresh:
            return list(_metadata["certs"]), _metadata["error"]
        try:
            if not _metadata_url_ok(url):
                raise SamlError("SAML_IDP_METADATA_URL must be an https Microsoft login URL")
            import httpx

            response = httpx.get(url, timeout=METADATA_TIMEOUT_S, follow_redirects=False)
            response.raise_for_status()
            if len(response.content) > METADATA_MAX_BYTES:
                raise SamlError("IdP metadata is too large")
            certs = parse_metadata_certs(response.content)
            if not certs:
                raise SamlError("IdP metadata contains no signing certificate")
            _metadata.update(url=url, at=time.monotonic(), certs=certs, error="")
        except Exception as err:
            log.warning("SAML IdP metadata refresh failed: %s", err)
            keep = _metadata["certs"] if _metadata["url"] == url else []
            _metadata.update(url=url, at=time.monotonic() - METADATA_TTL_S + 60, certs=keep, error=str(err)[:200])
        return list(_metadata["certs"]), _metadata["error"]


def reset_metadata_cache() -> None:
    with _metadata_lock:
        _metadata.update(url="", at=0.0, certs=[], error="")


def get_config() -> dict:
    app = app_url()
    tenant = env("MICROSOFT_TENANT_ID")
    issuer = env("SAML_ISSUER")
    idp_certs = split_certs(env("SAML_IDP_CERT"))
    metadata_url = env("SAML_IDP_METADATA_URL")
    fetched_certs, metadata_error = metadata_certs(metadata_url)
    idp_certs.extend(cert for cert in fetched_certs if cert not in idp_certs)
    idp_cert = idp_certs[0] if idp_certs else ""
    entry_point = env("SAML_ENTRY_POINT") or (
        f"https://login.microsoftonline.com/{tenant}/saml2" if GUID_RE.match(tenant) else ""
    )
    missing = []
    if not issuer:
        missing.append("SAML_ISSUER")
    if not idp_cert:
        missing.append("SAML_IDP_CERT (or a reachable SAML_IDP_METADATA_URL)")
    if not entry_point:
        missing.append("SAML_ENTRY_POINT (or a GUID MICROSOFT_TENANT_ID)")
    disabled = env("SAML_ENABLED").lower() in ("0", "false", "off", "no")
    return {
        "app_url": app,
        "issuer": issuer,
        "idp_cert": idp_cert,
        "idp_certs": idp_certs,
        "idp_entity_id": env("SAML_IDP_ENTITY_ID") or (f"https://sts.windows.net/{tenant}/" if GUID_RE.match(tenant) else ""),
        "allow_idp_initiated": env("SAML_ALLOW_IDP_INITIATED") == "1",
        "admin_sso": env("SAML_ADMIN_SSO") == "1",
        "disabled": disabled,
        "metadata_url": metadata_url,
        "metadata_error": metadata_error,
        "entry_point": entry_point,
        "callback_url": env("SAML_CALLBACK_URL") or f"{app}/api/employee/auth/saml/acs",
        "sp_private_key": _unescape_newlines(env("SAML_SP_PRIVATE_KEY")),
        "sp_cert": _strip_cert(env("SAML_SP_CERT")),
        "nameid_format": env("SAML_NAMEID_FORMAT"),
        "email_attribute": env("SAML_EMAIL_ATTRIBUTE"),
        "missing": missing,
        "configured": not missing,
        "enabled": not missing and not disabled,
    }


def not_configured_message(missing: list[str]) -> str:
    return f"SAML SSO is not configured. Missing: {', '.join(missing)}."


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def build_authn_request(cfg: Optional[dict] = None) -> tuple[str, str]:
    cfg = cfg or get_config()
    request_id = "_" + uuid.uuid4().hex
    root = etree.Element(
        "{%s}AuthnRequest" % NS["samlp"],
        nsmap={"samlp": NS["samlp"], "saml": NS["saml"]},
        ID=request_id,
        Version="2.0",
        IssueInstant=_iso(datetime.now(timezone.utc)),
        Destination=cfg["entry_point"],
        ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
        AssertionConsumerServiceURL=cfg["callback_url"],
    )
    etree.SubElement(root, "{%s}Issuer" % NS["saml"]).text = cfg["issuer"]
    policy = {"AllowCreate": "true"}
    if cfg["nameid_format"]:
        policy["Format"] = cfg["nameid_format"]
    etree.SubElement(root, "{%s}NameIDPolicy" % NS["samlp"], **policy)
    return request_id, etree.tostring(root).decode("utf-8")


def _sign_query(query: str, private_key_pem: str) -> str:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    signature = key.sign(query.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signature).decode("ascii")


def build_authorize_url(relay_state: str = "/employee", cfg: Optional[dict] = None) -> str:
    cfg = cfg or get_config()
    _, xml = build_authn_request(cfg)
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    deflated = compressor.compress(xml.encode("utf-8")) + compressor.flush()
    params = [("SAMLRequest", base64.b64encode(deflated).decode("ascii"))]
    if relay_state:
        params.append(("RelayState", relay_state))
    if cfg["sp_private_key"]:
        params.append(("SigAlg", "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"))
        signed = urlencode(params, quote_via=quote)
        params.append(("Signature", _sign_query(signed, cfg["sp_private_key"])))
    sep = "&" if "?" in cfg["entry_point"] else "?"
    return f"{cfg['entry_point']}{sep}{urlencode(params, quote_via=quote)}"


def build_metadata(cfg: Optional[dict] = None) -> str:
    cfg = cfg or get_config()
    root = etree.Element(
        "{%s}EntityDescriptor" % NS["md"], nsmap={"md": NS["md"], "ds": NS["ds"]}, entityID=cfg["issuer"]
    )
    sp = etree.SubElement(
        root,
        "{%s}SPSSODescriptor" % NS["md"],
        AuthnRequestsSigned="true" if cfg["sp_private_key"] else "false",
        WantAssertionsSigned="true",
        protocolSupportEnumeration=NS["samlp"],
    )
    if cfg["sp_cert"]:
        for use in ("signing", "encryption"):
            kd = etree.SubElement(sp, "{%s}KeyDescriptor" % NS["md"], use=use)
            info = etree.SubElement(kd, "{%s}KeyInfo" % NS["ds"])
            data = etree.SubElement(info, "{%s}X509Data" % NS["ds"])
            etree.SubElement(data, "{%s}X509Certificate" % NS["ds"]).text = cfg["sp_cert"]
    etree.SubElement(sp, "{%s}NameIDFormat" % NS["md"]).text = (
        cfg["nameid_format"] or "urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified"
    )
    etree.SubElement(
        sp,
        "{%s}AssertionConsumerService" % NS["md"],
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
        Location=cfg["callback_url"],
        index="1",
        isDefault="true",
    )
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8").decode("utf-8")


def _parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise SamlError("Invalid timestamp in SAML response")
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _check_window(not_before: Optional[str], not_on_or_after: Optional[str], now: datetime) -> None:
    start, end = _parse_time(not_before), _parse_time(not_on_or_after)
    if start and now + CLOCK_SKEW < start:
        raise SamlError("SAML assertion is not yet valid")
    if end and now - CLOCK_SKEW >= end:
        raise SamlError("SAML assertion has expired")


def _register_assertion(assertion_id: str, expires: datetime) -> None:
    now = time.time()
    with _seen_lock:
        for key in [k for k, exp in _seen_ids.items() if exp < now]:
            _seen_ids.pop(key, None)
        if assertion_id in _seen_ids:
            raise SamlError("SAML assertion has already been used")
        _seen_ids[assertion_id] = expires.timestamp() + 300


def reset_replay_cache() -> None:
    with _seen_lock:
        _seen_ids.clear()


def _verified_assertion(assertion: etree._Element, cert_pem: str) -> etree._Element:
    if assertion.find("ds:Signature", NS) is None:
        raise SamlError("SAML assertion is not signed")
    detached = etree.fromstring(etree.tostring(copy.deepcopy(assertion)))
    try:
        result = XMLVerifier().verify(detached, x509_cert=cert_pem, expect_references=1)
    except Exception as err:
        raise SamlError("SAML signature verification failed") from err
    signed = result.signed_xml if not isinstance(result, list) else result[0].signed_xml
    if signed.tag != "{%s}Assertion" % NS["saml"]:
        raise SamlError("SAML signature does not cover the assertion")
    return signed


def _attributes(assertion: etree._Element) -> dict:
    attrs: dict = {}
    for attr in assertion.findall("saml:AttributeStatement/saml:Attribute", NS):
        values = [("".join(v.itertext())).strip() for v in attr.findall("saml:AttributeValue", NS)]
        name = attr.get("Name") or ""
        if not name:
            continue
        attrs[name] = values[0] if len(values) == 1 else values
    return attrs


def validate_post_response(saml_response_b64: str, cfg: Optional[dict] = None, now: Optional[datetime] = None) -> dict:
    cfg = cfg or get_config()
    now = now or datetime.now(timezone.utc)
    try:
        raw = base64.b64decode(saml_response_b64, validate=False)
    except Exception as err:
        raise SamlError("Malformed SAML response") from err
    if not raw or len(raw) > MAX_RESPONSE_BYTES or b"<!DOCTYPE" in raw[:2048].upper() or b"<!ENTITY" in raw.upper():
        raise SamlError("Malformed SAML response")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)
    try:
        root = etree.fromstring(raw, parser)
    except etree.XMLSyntaxError as err:
        raise SamlError("Malformed SAML response") from err
    if root.tag != "{%s}Response" % NS["samlp"]:
        raise SamlError("Unexpected SAML message type")
    status = root.find("samlp:Status/samlp:StatusCode", NS)
    if status is None or status.get("Value") != STATUS_SUCCESS:
        raise SamlError("SAML response status is not success")
    if root.find("saml:EncryptedAssertion", NS) is not None:
        raise SamlError("Encrypted SAML assertions are not supported")
    assertions = root.findall("saml:Assertion", NS)
    if len(assertions) != 1:
        raise SamlError("SAML response must contain exactly one assertion")
    certs = cfg.get("idp_certs") or [cfg["idp_cert"]]
    last_error = None
    for cert in certs:
        try:
            assertion = _verified_assertion(assertions[0], cert_to_pem(cert))
            break
        except SamlError as err:
            last_error = err
    else:
        if last_error:
            raise last_error
        raise SamlError("No SAML signing certificate is configured")

    conditions = assertion.find("saml:Conditions", NS)
    if conditions is None:
        raise SamlError("SAML assertion has no conditions")
    _check_window(conditions.get("NotBefore"), conditions.get("NotOnOrAfter"), now)
    audiences = [("".join(a.itertext())).strip() for a in conditions.findall("saml:AudienceRestriction/saml:Audience", NS)]
    if not audiences or cfg["issuer"] not in audiences:
        raise SamlError("SAML audience mismatch")

    confirmations = assertion.findall("saml:Subject/saml:SubjectConfirmation/saml:SubjectConfirmationData", NS)
    if confirmations:
        valid = False
        for data in confirmations:
            recipient = data.get("Recipient")
            if recipient and recipient != cfg["callback_url"]:
                continue
            try:
                _check_window(data.get("NotBefore"), data.get("NotOnOrAfter"), now)
            except SamlError:
                continue
            valid = True
            break
        if not valid:
            raise SamlError("SAML subject confirmation is invalid")

    expiry = _parse_time(conditions.get("NotOnOrAfter")) or (now + timedelta(minutes=10))
    _register_assertion(assertion.get("ID") or uuid.uuid4().hex, expiry)

    name_id = assertion.find("saml:Subject/saml:NameID", NS)
    profile = {
        "nameID": ("".join(name_id.itertext())).strip() if name_id is not None else "",
        "nameIDFormat": name_id.get("Format") if name_id is not None else None,
        "issuer": ("".join(assertion.find("saml:Issuer", NS).itertext())).strip() if assertion.find("saml:Issuer", NS) is not None else "",
    }
    profile.update(_attributes(assertion))
    return profile


def _values(profile: dict, key: str) -> list[str]:
    raw = profile.get(key)
    items = raw if isinstance(raw, list) else ([] if raw is None else [raw])
    return [str(v or "").strip() for v in items if str(v or "").strip()]


def profile_emails(profile: dict, cfg: Optional[dict] = None) -> list[str]:
    cfg = cfg or get_config()
    keys = [k for k in [cfg["email_attribute"], *DEFAULT_EMAIL_ATTRIBUTES] if k]
    found: list[str] = []
    for key in keys:
        found.extend(_values(profile, key))
    found.append(str(profile.get("nameID") or "").strip())
    seen, out = set(), []
    for value in found:
        low = value.lower()
        if "@" in value and low not in seen:
            seen.add(low)
            out.append(low)
    return out


def profile_local_part(profile: dict, cfg: Optional[dict] = None) -> str:
    emails = profile_emails(profile, cfg)
    return emails[0].split("@")[0].strip() if emails else ""

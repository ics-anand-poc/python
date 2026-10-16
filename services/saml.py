import base64
import copy
import json
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
from signxml import DigestAlgorithm, SignatureConfiguration, SignatureMethod, XMLVerifier

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
PENDING_TTL_S = 600
METADATA_TTL_S = 3600
METADATA_TIMEOUT_S = 8
METADATA_MAX_BYTES = 1_000_000
METADATA_HOSTS = ("login.microsoftonline.com", "login.microsoftonline.us", "login.microsoft.com", "login.windows.net")
RELAY_PREFIXES = ("/employee", "/admin")
BEARER = "urn:oasis:names:tc:SAML:2.0:cm:bearer"
ALLOWED_SIGNATURES = frozenset({SignatureMethod.RSA_SHA256, SignatureMethod.RSA_SHA384, SignatureMethod.RSA_SHA512,
                                SignatureMethod.ECDSA_SHA256, SignatureMethod.ECDSA_SHA384, SignatureMethod.ECDSA_SHA512})
ALLOWED_DIGESTS = frozenset({DigestAlgorithm.SHA256, DigestAlgorithm.SHA384, DigestAlgorithm.SHA512})
SIGNATURE_CONFIG = SignatureConfiguration(signature_methods=ALLOWED_SIGNATURES, digest_algorithms=ALLOWED_DIGESTS, expect_references=1)
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


class SharedState:
    def __init__(self):
        self.mem: dict[str, tuple[float, str]] = {}
        self.lock = threading.Lock()
        self.client = None

    def _redis(self):
        url = env("REDIS_URL")
        if not url:
            return None
        with self.lock:
            if self.client is None:
                import redis

                self.client = redis.Redis.from_url(url, socket_timeout=3, socket_connect_timeout=3, decode_responses=True)
        return self.client

    def _sweep(self) -> None:
        now = time.time()
        for key in [k for k, (exp, _) in self.mem.items() if exp < now]:
            self.mem.pop(key, None)

    def put(self, key: str, value: str, ttl: int) -> None:
        client = self._redis()
        if client is not None:
            try:
                client.set(key, value, ex=ttl)
                return
            except Exception as err:
                log.warning("saml shared state redis write failed, using memory: %s", err)
        with self.lock:
            self._sweep()
            self.mem[key] = (time.time() + ttl, value)

    def put_once(self, key: str, ttl: int) -> bool:
        client = self._redis()
        if client is not None:
            try:
                return bool(client.set(key, "1", nx=True, ex=ttl))
            except Exception as err:
                log.warning("saml replay cache redis failed, using memory: %s", err)
        with self.lock:
            self._sweep()
            if key in self.mem:
                return False
            self.mem[key] = (time.time() + ttl, "1")
            return True

    def take(self, key: str) -> Optional[str]:
        client = self._redis()
        if client is not None:
            try:
                value = client.getdel(key)
                if value is not None:
                    return value
            except Exception as err:
                log.warning("saml shared state redis read failed, using memory: %s", err)
        with self.lock:
            self._sweep()
            hit = self.mem.pop(key, None)
            return hit[1] if hit else None

    def clear(self) -> None:
        with self.lock:
            self.mem.clear()


shared = SharedState()


def _unescape_newlines(value: str) -> str:
    return value.replace("\\n", "\n")


def split_certs(value: str) -> list[str]:
    return [c for c in (_strip_cert(part) for part in re.split(r"[|,;]", _unescape_newlines(value))) if c]


def _strip_cert(value: str) -> str:
    cleaned = _unescape_newlines(value)
    cleaned = cleaned.replace("-----BEGIN CERTIFICATE-----", "").replace("-----END CERTIFICATE-----", "")
    return re.sub(r"\s+", "", cleaned)


def cert_to_pem(body: str) -> str:
    lines = [body[i:i + 64] for i in range(0, len(body), 64)]
    return "-----BEGIN CERTIFICATE-----\n" + "\n".join(lines) + "\n-----END CERTIFICATE-----\n"


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
    _metadata.update(url="", at=0.0, certs=[], error="")


def get_config() -> dict:
    app = app_url()
    tenant = env("MICROSOFT_TENANT_ID")
    issuer = env("SAML_ISSUER")
    idp_certs = split_certs(env("SAML_IDP_CERT"))
    metadata_url = env("SAML_IDP_METADATA_URL")
    fetched, metadata_error = metadata_certs(metadata_url)
    idp_certs = idp_certs + [c for c in fetched if c not in idp_certs]
    entry_point = env("SAML_ENTRY_POINT") or (
        f"https://login.microsoftonline.com/{tenant}/saml2" if GUID_RE.match(tenant) else ""
    )
    missing = []
    if not issuer:
        missing.append("SAML_ISSUER")
    if not idp_certs:
        missing.append("SAML_IDP_CERT (or a reachable SAML_IDP_METADATA_URL)")
    if not entry_point:
        missing.append("SAML_ENTRY_POINT (or a GUID MICROSOFT_TENANT_ID)")
    return {
        "app_url": app,
        "issuer": issuer,
        "idp_cert": idp_certs[0] if idp_certs else "",
        "idp_certs": idp_certs,
        "idp_entity_id": env("SAML_IDP_ENTITY_ID") or (f"https://sts.windows.net/{tenant}/" if GUID_RE.match(tenant) else ""),
        "allow_idp_initiated": env("SAML_ALLOW_IDP_INITIATED") == "1",
        "force_authn": env("SAML_FORCE_AUTHN") == "1",
        "admin_sso": env("SAML_ADMIN_SSO") == "1",
        "disabled": env("SAML_ENABLED").lower() in ("0", "false", "off", "no"),
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
        "enabled": not missing and env("SAML_ENABLED").lower() not in ("0", "false", "off", "no"),
    }


def not_configured_message(missing: list[str]) -> str:
    return f"SAML SSO is not configured. Missing: {', '.join(missing)}."


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def build_authn_request(cfg: Optional[dict] = None) -> tuple[str, str]:
    cfg = cfg or get_config()
    request_id = "_" + uuid.uuid4().hex
    attributes = {"ID": request_id, "Version": "2.0", "IssueInstant": _iso(datetime.now(timezone.utc)),
                  "Destination": cfg["entry_point"], "ProtocolBinding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
                  "AssertionConsumerServiceURL": cfg["callback_url"]}
    if cfg.get("force_authn"):
        attributes["ForceAuthn"] = "true"
    root = etree.Element("{%s}AuthnRequest" % NS["samlp"], nsmap={"samlp": NS["samlp"], "saml": NS["saml"]}, **attributes)
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


def safe_return_path(value: Optional[str], default: str = "/employee") -> str:
    path = str(value or "")
    if not path.startswith("/") or path.startswith("//") or "\\" in path or any(ord(c) < 32 for c in path):
        return default
    return path if path == RELAY_PREFIXES[0] or any(path == p or path.startswith(p + "/") for p in RELAY_PREFIXES) else default


def start_login(target: str, return_to: str, cfg: Optional[dict] = None) -> str:
    cfg = cfg or get_config()
    request_id, xml = build_authn_request(cfg)
    shared.put(f"saml:req:{request_id}", json.dumps({"target": target, "returnTo": safe_return_path(return_to)}), PENDING_TTL_S)
    return _redirect_url(xml, request_id, cfg)


def consume_pending(request_id: str) -> Optional[dict]:
    if not request_id or not re.fullmatch(r"_[0-9a-f]{32}", request_id):
        return None
    raw = shared.take(f"saml:req:{request_id}")
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def response_request_id(saml_response_b64: str) -> str:
    try:
        raw = base64.b64decode(saml_response_b64, validate=False)
        parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)
        return etree.fromstring(raw, parser).get("InResponseTo") or ""
    except Exception:
        return ""


def build_authorize_url(relay_state: str = "/employee", cfg: Optional[dict] = None) -> str:
    cfg = cfg or get_config()
    _, xml = build_authn_request(cfg)
    return _redirect_url(xml, relay_state, cfg)


def _redirect_url(xml: str, relay_state: str, cfg: dict) -> str:
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
    ttl = max(60, int(expires.timestamp() - time.time()) + 300)
    if not shared.put_once(f"saml:assertion:{assertion_id}", ttl):
        raise SamlError("SAML assertion has already been used")


def reset_replay_cache() -> None:
    shared.clear()


def _verify_with_any(element: etree._Element, certs: list[str]) -> etree._Element:
    last: Optional[Exception] = None
    for body in certs:
        detached = etree.fromstring(etree.tostring(copy.deepcopy(element)))
        try:
            result = XMLVerifier().verify(detached, x509_cert=cert_to_pem(body), expect_config=SIGNATURE_CONFIG)
        except Exception as err:
            last = err
            continue
        return result.signed_xml if not isinstance(result, list) else result[0].signed_xml
    raise SamlError("SAML signature verification failed") from last


def _verified_assertion(root: etree._Element, assertion: etree._Element, certs: list[str]) -> etree._Element:
    if assertion.find("ds:Signature", NS) is not None:
        signed = _verify_with_any(assertion, certs)
        if signed.tag != "{%s}Assertion" % NS["saml"]:
            raise SamlError("SAML signature does not cover the assertion")
        return signed
    if root.find("ds:Signature", NS) is None:
        raise SamlError("SAML assertion is not signed")
    signed_root = _verify_with_any(root, certs)
    if signed_root.tag != "{%s}Response" % NS["samlp"]:
        raise SamlError("SAML signature does not cover the response")
    covered = signed_root.findall("saml:Assertion", NS)
    if len(covered) != 1:
        raise SamlError("SAML response must contain exactly one assertion")
    return covered[0]


def _text(element: Optional[etree._Element]) -> str:
    return ("".join(element.itertext())).strip() if element is not None else ""


def _check_issuer(element: etree._Element, expected: str) -> None:
    issuer = _text(element.find("saml:Issuer", NS))
    if expected and issuer and issuer != expected:
        raise SamlError("SAML issuer mismatch")
    if expected and not issuer and element.tag.endswith("}Assertion"):
        raise SamlError("SAML issuer mismatch")


def _attributes(assertion: etree._Element) -> dict:
    attrs: dict = {}
    for attr in assertion.findall("saml:AttributeStatement/saml:Attribute", NS):
        values = [("".join(v.itertext())).strip() for v in attr.findall("saml:AttributeValue", NS)]
        name = attr.get("Name") or ""
        if not name:
            continue
        attrs[name] = values[0] if len(values) == 1 else values
    return attrs


def _parse_response(saml_response_b64: str) -> etree._Element:
    try:
        raw = base64.b64decode(saml_response_b64, validate=False)
    except Exception as err:
        raise SamlError("Malformed SAML response") from err
    if not raw or len(raw) > MAX_RESPONSE_BYTES or b"<!DOCTYPE" in raw[:2048].upper() or b"<!ENTITY" in raw.upper():
        raise SamlError("Malformed SAML response")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)
    try:
        return etree.fromstring(raw, parser)
    except etree.XMLSyntaxError as err:
        raise SamlError("Malformed SAML response") from err


def _check_subject(assertion: etree._Element, cfg: dict, expected_request_id: Optional[str], now: datetime) -> None:
    confirmations = assertion.findall("saml:Subject/saml:SubjectConfirmation", NS)
    if not confirmations:
        return
    for confirmation in confirmations:
        if confirmation.get("Method") not in (None, BEARER):
            continue
        data = confirmation.find("saml:SubjectConfirmationData", NS)
        if data is None:
            continue
        recipient = data.get("Recipient")
        if recipient and recipient != cfg["callback_url"]:
            continue
        if expected_request_id and data.get("InResponseTo") not in (None, expected_request_id):
            continue
        try:
            _check_window(data.get("NotBefore"), data.get("NotOnOrAfter"), now)
        except SamlError:
            continue
        return
    raise SamlError("SAML subject confirmation is invalid")


def validate_post_response(saml_response_b64: str, cfg: Optional[dict] = None, now: Optional[datetime] = None,
                           expected_request_id: Optional[str] = None) -> dict:
    cfg = cfg or get_config()
    now = now or datetime.now(timezone.utc)
    root = _parse_response(saml_response_b64)
    if root.tag != "{%s}Response" % NS["samlp"]:
        raise SamlError("Unexpected SAML message type")
    status = root.find("samlp:Status/samlp:StatusCode", NS)
    if status is None or status.get("Value") != STATUS_SUCCESS:
        raise SamlError("SAML response status is not success")
    if root.find("saml:EncryptedAssertion", NS) is not None:
        raise SamlError("Encrypted SAML assertions are not supported")
    if root.get("Destination") and root.get("Destination") != cfg["callback_url"]:
        raise SamlError("SAML destination mismatch")
    if expected_request_id and root.get("InResponseTo") != expected_request_id:
        raise SamlError("SAML response does not match the login request")
    assertions = root.findall("saml:Assertion", NS)
    if len(assertions) != 1:
        raise SamlError("SAML response must contain exactly one assertion")
    certs = cfg.get("idp_certs") or [cfg["idp_cert"]]
    assertion = _verified_assertion(root, assertions[0], certs)
    entity = cfg.get("idp_entity_id") or ""
    _check_issuer(root, entity)
    _check_issuer(assertion, entity)

    conditions = assertion.find("saml:Conditions", NS)
    if conditions is None:
        raise SamlError("SAML assertion has no conditions")
    _check_window(conditions.get("NotBefore"), conditions.get("NotOnOrAfter"), now)
    audiences = [_text(a) for a in conditions.findall("saml:AudienceRestriction/saml:Audience", NS)]
    if not audiences or cfg["issuer"] not in audiences:
        raise SamlError("SAML audience mismatch")
    _check_subject(assertion, cfg, expected_request_id, now)
    for statement in assertion.findall("saml:AuthnStatement", NS):
        ends = _parse_time(statement.get("SessionNotOnOrAfter"))
        if ends and now - CLOCK_SKEW >= ends:
            raise SamlError("SAML session has expired")

    name_id = assertion.find("saml:Subject/saml:NameID", NS)
    if not _text(name_id):
        raise SamlError("SAML assertion has no subject")
    expiry = _parse_time(conditions.get("NotOnOrAfter")) or (now + timedelta(minutes=10))
    _register_assertion(assertion.get("ID") or uuid.uuid4().hex, expiry)

    profile = {"nameID": _text(name_id), "nameIDFormat": name_id.get("Format"), "issuer": _text(assertion.find("saml:Issuer", NS))}
    profile.update(_attributes(assertion))
    return profile


def cert_expiry(cfg: Optional[dict] = None) -> list[dict]:
    from cryptography import x509

    cfg = cfg or get_config()
    out = []
    for body in cfg.get("idp_certs") or []:
        try:
            cert = x509.load_pem_x509_certificate(cert_to_pem(body).encode())
            expires = cert.not_valid_after_utc if hasattr(cert, "not_valid_after_utc") else cert.not_valid_after.replace(tzinfo=timezone.utc)
            out.append({"expires": expires.isoformat(), "daysLeft": (expires - datetime.now(timezone.utc)).days})
        except Exception:
            out.append({"expires": None, "daysLeft": None})
    return out


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

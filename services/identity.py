import logging
import math
from typing import Optional

from core.config import env_int
from services import face

log = logging.getLogger("talentscope")

ID_UPLOAD_MAX_BYTES = 2 * 1024 * 1024
ID_UPLOAD_MAX_LABEL = "2 MB"
FACE_DESCRIPTOR_LENGTH = 128
MAX_FACE_DISTANCE = 0.55

GOVERNMENT_ID_TYPES = {
    "aadhaar": "Aadhar Card",
    "driving_license": "Driving License",
    "pan": "PAN Card",
    "voter_id": "Voter ID",
}


def is_government_id_type(value) -> bool:
    return isinstance(value, str) and value in GOVERNMENT_ID_TYPES


def id_type_label(value: Optional[str]) -> str:
    return GOVERNMENT_ID_TYPES.get(value or "", value or "Unknown")


def candidate_copy(matched: bool = False, failure_code: Optional[str] = None, selected_id_type: Optional[str] = None) -> str:
    if matched:
        label = id_type_label(selected_id_type)
        return f"{label} matched your live photo. You can continue." if label != "Unknown" else "Your ID matched your live photo. You can continue."
    return {
        "no_face_on_id": "We could not see a clear face on the ID. Upload a sharper photo of the card or take another picture.",
        "no_face_on_selfie": "We could not see a clear face in the selfie. Look at the camera with good lighting and try again.",
        "face_mismatch": "The face on the ID does not match the live photo. Use your own ID and look straight at the camera.",
        "invalid_id_type": "Select the type of government ID you are using.",
        "missing_id_type": "Select the type of government ID you are using.",
        "engine_error": "Identity check is unavailable right now. Your photos were saved for a recruiter to review.",
    }.get(failure_code or "", "We could not verify this ID against the live photo. Try a clearer ID photo or another selfie.")


def is_face_descriptor(value) -> bool:
    return (isinstance(value, list) and len(value) == FACE_DESCRIPTOR_LENGTH
            and all(isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n) for n in value))


def distance_to_confidence(distance: float, max_distance: float = MAX_FACE_DISTANCE) -> int:
    if distance <= 0:
        return 100
    if distance <= max_distance:
        return round(100 - (distance / max_distance) * 30)
    over = min(1.0, (distance - max_distance) / max(0.01, 1 - max_distance))
    return max(0, round(70 - over * 70))


def match_descriptors(id_desc: list, selfie_desc: list) -> dict:
    distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(id_desc, selfie_desc)))
    return {"matched": distance <= MAX_FACE_DISTANCE, "confidence": distance_to_confidence(distance), "distance": distance}


def _result(selected: str, matched: bool, confidence: int, engine: str, failure: Optional[str] = None, face_matched: bool = False) -> dict:
    return {
        "matched": matched,
        "confidence": confidence,
        "reason": f"{id_type_label(selected)} matched your live photo." if matched else candidate_copy(False, failure, selected),
        "selectedIdType": selected,
        "detectedIdType": selected,
        "idTypeMatched": True,
        "faceMatched": face_matched,
        "failureCode": failure,
        "engine": engine,
        "isSystemError": False,
    }


def verify_candidate_identity(id_image: str, selfie_image: str, id_type, id_descriptor=None, selfie_descriptor=None) -> dict:
    if not is_government_id_type(id_type):
        return {"matched": False, "confidence": 0, "reason": "Please select a government ID type before verification.",
                "selectedIdType": None, "detectedIdType": None, "idTypeMatched": False, "faceMatched": False,
                "failureCode": "invalid_id_type", "engine": "none", "isSystemError": False}
    min_conf = env_int("IDENTITY_MIN_CONFIDENCE", 70)
    desc_match = (match_descriptors(id_descriptor, selfie_descriptor)
                  if is_face_descriptor(id_descriptor) and is_face_descriptor(selfie_descriptor) else None)
    remote = None
    try:
        remote = face.compare(id_image, selfie_image)
    except face.FaceServiceError as err:
        log.error("Face match service failed: %s", err)
    if remote is not None:
        failure_raw = str(remote.get("failureCode") or "")
        confidence = remote.get("confidence")
        confidence = confidence if isinstance(confidence, (int, float)) else int(str(confidence or 0) or 0)
        if failure_raw in ("no_face_on_id", "no_face_on_selfie"):
            return _result(id_type, False, int(confidence), "facenet", failure_raw)
        matched = bool(remote.get("matched"))
        if desc_match and matched and desc_match["matched"]:
            confidence = round(confidence * 0.85 + desc_match["confidence"] * 0.15)
        if matched and confidence < min_conf:
            matched = False
        if not matched:
            return _result(id_type, False, int(confidence), "facenet", "face_mismatch")
        return _result(id_type, True, int(confidence), "facenet", face_matched=True)
    if desc_match:
        matched = desc_match["matched"] and desc_match["confidence"] >= min_conf
        if not matched:
            return _result(id_type, False, desc_match["confidence"], "faceapi", "face_mismatch")
        return _result(id_type, True, desc_match["confidence"], "faceapi", face_matched=True)
    return {
        "matched": False, "confidence": 0,
        "reason": "Identity verification engine unavailable. Start the face service (python-ai/faceproj) and check FACE_MATCH_SERVICE_URL. Images saved for manual audit.",
        "selectedIdType": id_type, "detectedIdType": None, "idTypeMatched": False, "faceMatched": False,
        "failureCode": "engine_error", "engine": "none", "isSystemError": True,
    }

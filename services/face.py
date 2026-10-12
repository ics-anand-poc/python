import httpx

from core.config import env, env_int


class FaceServiceError(Exception):
    pass


def base_url() -> str:
    return (env("FACE_MATCH_SERVICE_URL") or "http://127.0.0.1:10000").rstrip("/")


def _headers() -> dict:
    key = env("FACE_MATCH_API_KEY")
    return {"X-Face-Match-Key": key} if key else {}


def compare(id_image: str, selfie_image: str) -> dict:
    timeout = env_int("FACE_MATCH_TIMEOUT_MS", 90000) / 1000
    try:
        res = httpx.post(f"{base_url()}/compare", json={"idImage": id_image, "selfieImage": selfie_image},
                         headers=_headers(), timeout=timeout)
    except httpx.HTTPError as err:
        raise FaceServiceError(f"Face match service is unreachable at {base_url()}") from err
    if res.status_code >= 400:
        raise FaceServiceError(f"Face match service returned HTTP {res.status_code}")
    return res.json()


def is_up() -> bool:
    try:
        return httpx.get(f"{base_url()}/health", timeout=2.5).status_code < 400
    except Exception:
        return False

"""FastAPI app factory and uvicorn entrypoint."""

import io
from typing import Annotated, Any

import uvicorn
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError

from img2person_inference import lhm, mock
from img2person_inference.config import Settings, load_settings

_IMAGE_TYPES = {
    "image/png", "image/jpeg", "image/webp", "image/gif", "image/bmp",
    "image/tiff", "image/x-ms-bmp",
}


def problem(status: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={"type": "about:blank", "title": title, "status": status, "detail": detail},
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = load_settings()
    app = FastAPI(title="img2person-inference")
    app.state.settings = settings

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "mode": settings.mode}

    @app.post("/v1/reconstruct")
    async def reconstruct(image: Annotated[UploadFile, File()]) -> Any:
        data = await image.read()
        if not data:
            return problem(422, "Unprocessable Entity", "empty upload: 'image' field has no bytes")
        if image.content_type and image.content_type not in _IMAGE_TYPES:
            return problem(
                422, "Unprocessable Entity",
                f"unsupported content type {image.content_type!r}: expected an image",
            )
        try:
            decoded = Image.open(io.BytesIO(data))
            decoded.load()
        except (UnidentifiedImageError, OSError, ValueError):
            return problem(422, "Unprocessable Entity", "uploaded bytes are not a readable image")

        if settings.mode == "lhm":
            try:
                result = lhm.run_lhm(data)
            except mock.ReconstructionError as exc:
                return problem(422, "Unprocessable Entity", exc.detail)
            except RuntimeError as exc:
                return problem(503, "Service Unavailable", str(exc))
            payload = mock.response_payload(result)
            payload["mode"] = "lhm"
            return payload

        try:
            result = mock.reconstruct(data, decoded)
        except mock.ReconstructionError as exc:
            return problem(422, "Unprocessable Entity", exc.detail)
        return mock.response_payload(result)

    return app


def main() -> None:
    settings = load_settings()
    uvicorn.run(create_app(settings), host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()

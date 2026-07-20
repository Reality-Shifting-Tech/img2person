import { useRef, useState } from "react";
import { ApiError, MAX_UPLOAD_BYTES, uploadAvatar } from "./api";

interface UploadFormProps {
  onAccepted: (id: string) => void;
}

export function UploadForm({ onAccepted }: UploadFormProps) {
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const submit = async (file: File) => {
    setError(null);
    if (!file.type.startsWith("image/")) {
      setError("That file is not an image. Choose a JPEG or PNG photo.");
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      setError("That photo is larger than 10 MB. Choose a smaller one.");
      return;
    }
    setSubmitting(true);
    try {
      const { id } = await uploadAvatar(file);
      onAccepted(id);
    } catch (err) {
      setSubmitting(false);
      setError(
        err instanceof ApiError ? err.detail : "Upload failed. Check that the API is running.",
      );
    }
  };

  return (
    <section className="upload">
      <div
        className={dragActive ? "dropzone dropzone-active" : "dropzone"}
        onDragOver={(event) => {
          event.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragActive(false);
          const file = event.dataTransfer.files[0];
          if (!submitting && file) {
            void submit(file);
          }
        }}
      >
        <p>Drop a photo here, or</p>
        <button type="button" disabled={submitting} onClick={() => inputRef.current?.click()}>
          {submitting ? "Uploading…" : "Choose a photo"}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          aria-label="Photo upload"
          className="file-input"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) {
              void submit(file);
            }
            event.target.value = "";
          }}
        />
      </div>
      <p className="hint">One clear photo, facing the camera, works best.</p>
      {error !== null && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}

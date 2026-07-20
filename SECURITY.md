# Security Policy

## Scope

img2person processes biometric-adjacent data (photos of people). Treat every
upload as sensitive.

## Reporting a vulnerability

Please do not open public issues for security reports. Email the maintainers
via the address listed on the Reality-Shifting-Tech organization profile, or
use GitHub's private vulnerability reporting on this repository. We aim to
acknowledge reports within 72 hours.

## Notes for self-hosters

- Uploaded photos and generated avatars are stored unencrypted on disk by
  default (`STORAGE_DIR`). Put the storage volume behind your own encryption
  and access controls.
- The `/v1` API ships without authentication in the default configuration —
  it is meant to run behind your own reverse proxy or gateway. Do not expose
  it directly to the public internet without adding auth.
- Face photos may be biometric data under GDPR, BIPA, and similar laws. If
  you operate img2person for others, you are the data controller; obtain
  consent and honor deletion requests (`DELETE /v1/avatars/:id` removes all
  artifacts).

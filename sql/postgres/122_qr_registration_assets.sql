-- Store the QR image selected by a DAv for the tenant-scoped registration entry.
-- The application validates the image type and size before writing this field.
ALTER TABLE tenant_fan_qr_invites
    ADD COLUMN IF NOT EXISTS qr_image_data TEXT NOT NULL DEFAULT '';


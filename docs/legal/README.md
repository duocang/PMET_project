# docs/legal/

GDPR / DSGVO compliance evidence — copies of legal documents we rely on but don't control. Stored here so the chain of evidence survives even if a vendor relocates the URL.

## What's in here

| File | Source | Captured | Why we have it |
|---|---|---|---|
| [`DigitalOcean-DPA-2026-05-17.pdf`](./DigitalOcean-DPA-2026-05-17.pdf) | <https://www.digitalocean.com/legal/data-processing-agreement> | 2026-05-17 | GDPR Art. 28(3) requires the Auftragsverarbeitungsvertrag to be retained "in writing, including electronic form." DigitalOcean's [GDPR FAQ](https://www.digitalocean.com/legal/gdpr-faq) confirms: *"By agreeing to our terms of service, you are automatically accepting our DPA and do not need to sign a separate document."* This PDF is the captured version of the DPA we accepted when the DigitalOcean account was created. |

## How to refresh

When DigitalOcean (or any other vendor we add here) publishes a new DPA version, capture a new snapshot:

```bash
mkdir -p docs/legal
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    --headless --disable-gpu --no-pdf-header-footer \
    --print-to-pdf="docs/legal/<Vendor>-DPA-$(date +%Y-%m-%d).pdf" \
    "<vendor-DPA-URL>"
```

Keep the old PDF too — the date stamp matters for "which version were we operating under when X happened" audits. Don't overwrite.

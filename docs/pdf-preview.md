# Authenticated PDF preview

PDF attachment cards open a same-origin portal viewer in a new tab with page navigation, zoom, accessible page text and a separate original-file download. The in-app browser failed to render the initial native-viewer candidate, so the deployed correction uses locally vendored Mozilla PDF.js 6.5.438 (Apache-2.0; provenance, integrity and file hashes under `web/assets/intake/pdfjs/`). No PDF, credential or signed upstream URL is sent to an external viewer/CDN. No package install scripts run.

Only exact selected-job attachment paths are accepted by the viewer. Its fetch still passes through the existing authenticated session/role/project/file checks. Existing CSP (including object-src none and frame-ancestors none), nosniff and no-store remain unchanged; no iframe, eval, XFA, PDF scripting or external links/actions are enabled. Canvas font paths avoid new blob/font/eval CSP permissions. Vendored source is excluded only from ORNL palette lint, not credential scanning.

Explicit `?preview=1` returns PDF bytes only when MIME and `%PDF-` signature agree. This is a format guard, not complete validation. Default PDF requests and `?download=1` retain forced download; download wins. The viewer handles one page at a time with a 16M-pixel canvas cap, at most 20MB source, and a download fallback for unsupported/password PDFs. This DEV qualification is one synthetic one-page PDF; complex forms, encrypted PDFs, large/multipage documents and requester/My Requests remain outside live test scope. Session-local demo blobs retain their existing browser behavior.

Source API: https://mozilla.github.io/pdf.js/examples/

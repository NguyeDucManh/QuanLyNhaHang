# Pinned map renderer for Leaflet

MapLibre GL JS 5.24.0 (BSD-3-Clause), CSP build + separate worker, and
@maplibre/maplibre-gl-leaflet 0.1.4 (ISC). Downloaded from their official npm
archives, SHA-512 archive integrity verified against npm package metadata.
License files are preserved. Only unavailable sourceMappingURL trailers removed.

MapLibre renders the OpenFreeMap vector background; Leaflet owns GPS markers,
restaurant marker, radius, controls and viewport. Libraries load only on map pages.
The CSP worker is served by Django static/WhiteNoise, never a third-party script.

Provider: https://openfreemap.org/quick_start/ ; https://openfreemap.org/tos/
No API key, account or paid subscription. Attribution remains visible through
Leaflet. Public service is best effort, without SLA; do not prefetch/offline cache.

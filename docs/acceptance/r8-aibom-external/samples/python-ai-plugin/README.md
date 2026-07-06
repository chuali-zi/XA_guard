# R8 Python AI Plugin Sample

This is a minimal local scan target for R8 external AIBOM/CycloneDX generator acceptance preparation.

It intentionally contains only public sample metadata:

- a Python package manifest;
- a simple MCP server manifest;
- a prompt file;
- a tiny importable module.

It does not contain secrets, model weights, network calls, or executable business logic. Use it only as a local directory input for an external BOM generator such as `@cyclonedx/cdxgen`.

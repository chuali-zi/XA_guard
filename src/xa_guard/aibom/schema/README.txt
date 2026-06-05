CycloneDX 1.6 Schema Subset — XA-Guard AIBOM
=============================================

File: cyclonedx-1.6.subset.schema.json

This is a hand-authored faithful SUBSET of the official CycloneDX 1.6 JSON Schema.

Official schema source:
  https://cyclonedx.org/schema/bom-1.6.schema.json

License: Apache License 2.0 (same as CycloneDX specification)
  https://github.com/CycloneDX/specification/blob/master/LICENSE

Fields covered:
  - Top-level: bomFormat, specVersion, version, serialNumber, metadata, components,
    dependencies, vulnerabilities, services, externalReferences, compositions, properties
  - component: type (full enum), name, version, bom-ref, purl, hashes, licenses, properties
  - hash: alg (full enum), content
  - dependency: ref, dependsOn, provides
  - vulnerability: id, ratings[].severity (full enum)

XA-Guard extension keys ('findings', 'rating') are NOT validated by this schema.
The wrapper in schema_validator.py explicitly strips and permits these keys.

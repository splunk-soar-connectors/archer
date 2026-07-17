**Unreleased**

* Escaped dynamic Archer widget values before embedding them in inline JavaScript handlers.
* Enabled TLS certificate verification by default for RSA Archer connections.
* Rejected DTDs and bounded RSA Archer XML responses before parsing them with external entities disabled.
* Hardened embedded Archer group lookup XML and corrected its primary XPath expression.
* Required positive numeric content IDs before constructing Archer record API paths.
* Restarted scheduled ingestion from page one when a persisted Archer page no longer exists.
* Serialized Type 6 values-list fields and rejected unsupported field types instead of silently dropping writes.

# Official model retrieval

The host found TI's UCC28180 product-page links for SLUM528 and SLUM423. A sandboxed curl initially could not resolve www.ti.com. The authorized read was retried with network access; both official archives downloaded successfully.

- `https://www.ti.com/lit/zip/slum528`:9083 bytes. `UCC28180_TRANS.LIB` starts with `<Encrypted Library>`.
- `https://www.ti.com/lit/zip/slum423`: PSpice average model library uses `$CDNENCSTART` encrypted sections.

Archives are preserved unchanged under `controller/sources`. The actual blocker is simulator compatibility/encryption, not absence of a manufacturer model. No decryption or unsupported conversion was attempted.

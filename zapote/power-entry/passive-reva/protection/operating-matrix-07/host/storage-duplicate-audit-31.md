# Storage duplicate audit 31

Read-only snapshot for the operating-matrix campaign. No files were deleted, moved, recompressed, hardlinked, or edited. The live prefix `line-load-native-runner-27/full-LL06/` was excluded from byte reads and hashes.

## Snapshot

- `rg --files --hidden --no-ignore` entries: **3125**.
- Regular files with successful stat: **3125**.
- Large-file threshold: **52428800 bytes (50 MiB)**.
- Large regular files outside excluded prefix: **30**, totaling **34,236,377,702 bytes (31.89 GiB)**.
- Filesystem available at snapshot: **15,253,741,568 bytes (14.21 GiB)**.

## Exact duplicate groups

Only equal-size groups were hashed. Every member below has a distinct inode and `hardlink_count=1`; these are separate copies.

### 94,196,533 bytes — exact duplicate: `true`

- `controller-finite-edge-safe/integrated.tsv` — inode `140987119`, hardlinks `1`, SHA-256 `f46bd3d7d78663155a1fd9f4efb97f36d3ab0a6c516bac8afb2366e56f5ad968`
- `controller-finite-edge/integrated.tsv` — inode `140977016`, hardlinks `1`, SHA-256 `f46bd3d7d78663155a1fd9f4efb97f36d3ab0a6c516bac8afb2366e56f5ad968`

### 103,333,095 bytes — exact duplicate: `true`

- `numerical-repair/driver-vendor-comphys-candidate/authored-late.tsv` — inode `141133362`, hardlinks `1`, SHA-256 `67668931692668b6190ab5a25ffb13a4484c06b5b5f25e4a606c6147e503f553`
- `numerical-repair/driver-vendor-comphys-native-candidate/authored-late.tsv` — inode `141133859`, hardlinks `1`, SHA-256 `67668931692668b6190ab5a25ffb13a4484c06b5b5f25e4a606c6147e503f553`

### 138,336,040 bytes — exact duplicate: `true`

- `controller-finite-edge-safe/soft-start.tsv` — inode `140987091`, hardlinks `1`, SHA-256 `ba35699dd68f30b5417bcf177238553d4ab8d19abd41b4bf98aee0bd1cc6cec8`
- `controller-finite-edge/soft-start.tsv` — inode `140976981`, hardlinks `1`, SHA-256 `ba35699dd68f30b5417bcf177238553d4ab8d19abd41b4bf98aee0bd1cc6cec8`

## Disposition

The three groups are byte-identical and represent **335,865,668 bytes (0.313 GiB)** of duplicate logical bytes. This is a logical upper bound, not measured physical space recoverable: distinct inodes and link counts do not reveal APFS shared extents. The possible gain is too small to resolve the remaining campaign shortfall, so no mutation is recommended.

`controller-finite-edge-safe` explicitly records its fixture traces as byte-identical to the `controller-finite-edge` intermediate candidate; the safe directory is the complete candidate and is receipt-tracked. The duplicate intermediate traces still sit under a separate candidate path, so the audit preserves both paths and bytes. Hardlinking could preserve both names and content hashes but would couple later writes; it is not warranted for this small possible gain.

`driver-vendor-comphys-native-candidate/authored-late.tsv` is documented as an exact-match parser-compatibility result against the prior hybrid candidate. The equal bytes are evidence for that claim, so neither copy is treated as disposable by this audit.

No equal-size group was found outside the three groups above. Unique-size files were not hashed. The excluded live LL06 prefix was not read or hashed. This read-only audit supplies no useful multi-gigabyte recovery opportunity and recommends preserving the artifacts.

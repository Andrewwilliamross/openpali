"""The unified spatiotemporal state model and its cloud-native storage layer.

Every spatial primitive in the system — LARIAC mesh vertices, registered
crowdsourced points, trained 3D Gaussian Splats — is one row of the state
vector:

    x = [ X_ecef, Y_ecef, Z_ecef,   absolute position (m, WGS84 ECEF)
          T_epoch,                  acquisition time (unix seconds, float64)
          S (3,),                   Gaussian scale (m; isotropic ε for raw points)
          R (4,),                   rotation quaternion, wxyz, unit norm
          alpha,                    opacity in [0, 1]
          Psi (K, 3),               spherical-harmonics colour coefficients
          APN ]                     canonical 10-digit unhyphenated parcel key

Storage is a hive-partitioned Parquet dataset (NO per-parcel flat JSON files):

    store/gaussians/h3_08=<cell>/<epoch_label>-<kind>.parquet

partitioned by the resolution-8 H3 cell of each point (≈0.7 km² hexes — ~80
cells cover the fire footprint), with a per-row resolution-12 H3 index column
for fine spatial queries. The parcel-level asset index is a **GeoParquet 1.1**
file (`store/assets.parquet`) carrying one row per (APN, kind, epoch) with a
WKB geometry footprint — readable by GDAL/QGIS/DuckDB directly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import h3
import numpy as np
import pyarrow as pa
import pyarrow.dataset as pa_ds
import pyarrow.parquet as pq

from .geodesy import ecef_to_wgs84

# SH degree 0..3 → coefficient count per colour channel
SH_COEFFS = {0: 1, 1: 4, 2: 9, 3: 16}
H3_PARTITION_RES = 8  # directory partitioning (~0.74 km² cells)
H3_INDEX_RES = 12  # per-row fine index (~307 m² cells)
POINT_EPSILON_SCALE = 0.01  # isotropic scale (m) representing a raw point sample

_IDENTITY_QUAT = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)


@dataclass
class GaussianBatch:
    """Struct-of-arrays batch of N spatiotemporal primitives.

    Raw point clouds are degenerate Gaussians: scale=ε, identity rotation,
    alpha=1, DC-only SH. This keeps one schema across modalities.
    """

    xyz_ecef: np.ndarray  # (N, 3) float64
    t_epoch: np.ndarray  # (N,)  float64
    scale: np.ndarray  # (N, 3) float32
    rot: np.ndarray  # (N, 4) float32, wxyz
    alpha: np.ndarray  # (N,)  float32
    sh: np.ndarray  # (N, K, 3) float32
    apn: np.ndarray  # (N,)  <U10
    kind: str = "points"  # points | splats | mesh_vertices
    source: str = ""

    def __post_init__(self) -> None:
        n = len(self.xyz_ecef)
        shapes = {
            "xyz_ecef": (self.xyz_ecef.shape, (n, 3)),
            "t_epoch": (self.t_epoch.shape, (n,)),
            "scale": (self.scale.shape, (n, 3)),
            "rot": (self.rot.shape, (n, 4)),
            "alpha": (self.alpha.shape, (n,)),
            "apn": (self.apn.shape, (n,)),
        }
        for name, (got, want) in shapes.items():
            if got != want:
                raise ValueError(f"{name}: shape {got}, expected {want}")
        if self.sh.ndim != 3 or self.sh.shape[0] != n or self.sh.shape[2] != 3:
            raise ValueError(f"sh: shape {self.sh.shape}, expected (N, K, 3)")
        if self.sh.shape[1] not in SH_COEFFS.values():
            raise ValueError(f"sh: K={self.sh.shape[1]} is not a valid SH band size")
        norms = np.linalg.norm(self.rot, axis=1)
        bad = np.abs(norms - 1.0) > 1e-3
        if bad.any():
            # normalise rather than reject — upstream quantisation drifts slightly
            self.rot = (self.rot / np.maximum(norms, 1e-12)[:, None]).astype(np.float32)

    def __len__(self) -> int:
        return len(self.xyz_ecef)

    @property
    def sh_degree(self) -> int:
        k = self.sh.shape[1]
        return {v: d for d, v in SH_COEFFS.items()}[k]

    # ---------- constructors ----------

    @classmethod
    def from_points(cls, xyz_ecef: np.ndarray, t_epoch: float | np.ndarray,
                    apn: str | np.ndarray, *, rgb: np.ndarray | None = None,
                    kind: str = "points", source: str = "") -> "GaussianBatch":
        """Lift a raw point cloud into the unified state model."""
        xyz = np.asarray(xyz_ecef, dtype=np.float64).reshape(-1, 3)
        n = len(xyz)
        t = np.full(n, t_epoch, dtype=np.float64) if np.isscalar(t_epoch) else np.asarray(t_epoch, np.float64)
        a = np.full(n, apn, dtype="<U10") if isinstance(apn, str) else np.asarray(apn, dtype="<U10")
        sh = np.zeros((n, 1, 3), dtype=np.float32)
        if rgb is not None:
            # DC band: c = (rgb - 0.5) / Y00 with Y00 = 0.2820948
            sh[:, 0, :] = (np.asarray(rgb, np.float32).reshape(-1, 3) - 0.5) / 0.2820948
        return cls(
            xyz_ecef=xyz,
            t_epoch=t,
            scale=np.full((n, 3), POINT_EPSILON_SCALE, dtype=np.float32),
            rot=np.tile(_IDENTITY_QUAT, (n, 1)),
            alpha=np.ones(n, dtype=np.float32),
            sh=sh,
            apn=a,
            kind=kind,
            source=source,
        )

    @classmethod
    def concat(cls, batches: list["GaussianBatch"]) -> "GaussianBatch":
        if not batches:
            raise ValueError("nothing to concat")
        k = max(b.sh.shape[1] for b in batches)
        shs = []
        for b in batches:
            if b.sh.shape[1] < k:  # pad lower-degree SH with zero higher bands
                pad = np.zeros((len(b), k - b.sh.shape[1], 3), dtype=np.float32)
                shs.append(np.concatenate([b.sh, pad], axis=1))
            else:
                shs.append(b.sh)
        return cls(
            xyz_ecef=np.concatenate([b.xyz_ecef for b in batches]),
            t_epoch=np.concatenate([b.t_epoch for b in batches]),
            scale=np.concatenate([b.scale for b in batches]),
            rot=np.concatenate([b.rot for b in batches]),
            alpha=np.concatenate([b.alpha for b in batches]),
            sh=np.concatenate(shs),
            apn=np.concatenate([b.apn for b in batches]),
            kind=batches[0].kind,
            source=batches[0].source,
        )

    # ---------- spatial indexing ----------

    def h3_cells(self, res: int = H3_INDEX_RES) -> np.ndarray:
        """Per-point H3 cell (uint64) at the given resolution."""
        lon, lat, _ = ecef_to_wgs84(self.xyz_ecef)
        return np.array(
            [h3.str_to_int(h3.latlng_to_cell(la, lo, res)) for la, lo in zip(lat, lon)],
            dtype=np.uint64,
        )

    # ---------- arrow interop ----------

    def to_arrow(self) -> pa.Table:
        n, k = len(self), self.sh.shape[1]
        h12 = self.h3_cells(H3_INDEX_RES)
        h8 = np.array([h3.str_to_int(h3.cell_to_parent(h3.int_to_str(c), H3_PARTITION_RES)) for c in h12],
                      dtype=np.uint64)
        sh_flat = pa.FixedSizeListArray.from_arrays(
            pa.array(self.sh.reshape(-1).astype(np.float32)), k * 3
        )
        return pa.table(
            {
                "x_ecef": self.xyz_ecef[:, 0],
                "y_ecef": self.xyz_ecef[:, 1],
                "z_ecef": self.xyz_ecef[:, 2],
                "t_epoch": self.t_epoch,
                "sx": self.scale[:, 0],
                "sy": self.scale[:, 1],
                "sz": self.scale[:, 2],
                "qw": self.rot[:, 0],
                "qx": self.rot[:, 1],
                "qy": self.rot[:, 2],
                "qz": self.rot[:, 3],
                "alpha": self.alpha,
                "sh": sh_flat,
                "sh_degree": pa.array(np.full(n, self.sh_degree, dtype=np.int8)),
                "apn": pa.array(self.apn).dictionary_encode(),
                "h3_12": h12,
                "h3_08": h8,
                "kind": pa.array(np.full(n, self.kind)).dictionary_encode(),
                "source": pa.array(np.full(n, self.source)).dictionary_encode(),
            }
        )

    @classmethod
    def from_arrow(cls, t: pa.Table) -> "GaussianBatch":
        def col(name: str) -> np.ndarray:
            c = t.column(name)
            if pa.types.is_dictionary(c.type):
                c = c.cast(c.type.value_type)
            return c.to_numpy(zero_copy_only=False)

        n = len(t)
        sh_col = t.column("sh").combine_chunks()
        k3 = sh_col.type.list_size
        sh = np.asarray(sh_col.flatten(), dtype=np.float32).reshape(n, k3 // 3, 3)
        kind = col("kind")[0] if n else "points"
        source = col("source")[0] if n else ""
        return cls(
            xyz_ecef=np.stack([col("x_ecef"), col("y_ecef"), col("z_ecef")], axis=1),
            t_epoch=col("t_epoch"),
            scale=np.stack([col("sx"), col("sy"), col("sz")], axis=1).astype(np.float32),
            rot=np.stack([col("qw"), col("qx"), col("qy"), col("qz")], axis=1).astype(np.float32),
            alpha=col("alpha").astype(np.float32),
            sh=sh,
            apn=col("apn").astype("<U10"),
            kind=str(kind),
            source=str(source),
        )


# ---------------------------------------------------------------------------
# storage
# ---------------------------------------------------------------------------


@dataclass
class SpatialStore:
    """Partitioned Parquet dataset for primitives + GeoParquet asset index."""

    root: Path
    _asset_rows: list[dict] = field(default_factory=list)

    @property
    def gaussians_dir(self) -> Path:
        return self.root / "gaussians"

    @property
    def assets_path(self) -> Path:
        return self.root / "assets.parquet"

    # ----- primitives -----

    def write_batch(self, batch: GaussianBatch, *, epoch_label: str) -> int:
        """Append a batch, partitioned by its res-8 H3 cells.

        File names carry a content-stable batch id (hash of the batch's APN
        set): re-running the same batch overwrites its own files (idempotent),
        while different batches sharing an H3 cell never collide.
        """
        import hashlib

        batch_id = hashlib.sha1(
            "|".join(sorted(set(batch.apn.tolist()))).encode()
        ).hexdigest()[:12]
        t = batch.to_arrow()
        n_files = 0
        for cell in pa.compute.unique(t.column("h3_08")).to_pylist():
            part = t.filter(pa.compute.equal(t.column("h3_08"), cell))
            part_dir = self.gaussians_dir / f"h3_08={h3.int_to_str(cell)}"
            part_dir.mkdir(parents=True, exist_ok=True)
            out = part_dir / f"{epoch_label}-{batch.kind}-{batch_id}.parquet"
            pq.write_table(part.drop_columns(["h3_08"]), out, compression="zstd")
            n_files += 1
        return n_files

    def read(self, *, apn: str | None = None, kind: str | None = None,
             h3_cells_r8: list[str] | None = None) -> GaussianBatch | None:
        """Read primitives back, optionally filtered by APN / kind / partition."""
        if not self.gaussians_dir.exists():
            return None
        ds = pa_ds.dataset(self.gaussians_dir, format="parquet", partitioning="hive")
        flt = None
        if apn is not None:
            flt = pa_ds.field("apn") == apn
        if kind is not None:
            f2 = pa_ds.field("kind") == kind
            flt = f2 if flt is None else (flt & f2)
        if h3_cells_r8 is not None:
            f3 = pa_ds.field("h3_08").isin(h3_cells_r8)
            flt = f3 if flt is None else (flt & f3)
        t = ds.to_table(filter=flt)
        if len(t) == 0:
            return None
        t = t.drop_columns(["h3_08"])  # partition col re-derived on write
        return GaussianBatch.from_arrow(t)

    # ----- asset index (GeoParquet) -----

    def index_asset(self, *, apn: str, kind: str, t_epoch: float, n_points: int,
                    geometry_wkb: bytes, status: str, source: str,
                    anomaly: str | None = None) -> None:
        self._asset_rows.append(
            {
                "apn": apn,
                "kind": kind,
                "t_epoch": t_epoch,
                "n_points": n_points,
                "geometry": geometry_wkb,
                "status": status,  # live | static_baseline | stale_cached
                "source": source,
                "anomaly": anomaly,
            }
        )

    def flush_assets(self, *, merge_existing: bool = True) -> int:
        """Write the GeoParquet asset index. Latest row per (apn, kind) wins."""
        rows = list(self._asset_rows)
        if merge_existing and self.assets_path.exists():
            prev = pq.read_table(self.assets_path)
            rows = prev.to_pylist() + rows
        if not rows:
            return 0
        # de-dup: keep the newest (t_epoch) row per (apn, kind)
        best: dict[tuple[str, str], dict] = {}
        for r in rows:
            key = (r["apn"], r["kind"])
            if key not in best or r["t_epoch"] >= best[key]["t_epoch"]:
                best[key] = r
        final = sorted(best.values(), key=lambda r: (r["apn"], r["kind"]))
        t = pa.table(
            {
                "apn": [r["apn"] for r in final],
                "kind": [r["kind"] for r in final],
                "t_epoch": pa.array([r["t_epoch"] for r in final], pa.float64()),
                "n_points": pa.array([r["n_points"] for r in final], pa.int64()),
                "geometry": pa.array([r["geometry"] for r in final], pa.binary()),
                "status": [r["status"] for r in final],
                "source": [r["source"] for r in final],
                "anomaly": [r["anomaly"] for r in final],
            }
        )
        geo_meta = {
            "version": "1.1.0",
            "primary_column": "geometry",
            "columns": {
                "geometry": {"encoding": "WKB", "geometry_types": ["Polygon", "MultiPolygon", "Point"]}
            },
        }
        t = t.replace_schema_metadata({b"geo": json.dumps(geo_meta).encode()})
        self.root.mkdir(parents=True, exist_ok=True)
        pq.write_table(t, self.assets_path, compression="zstd")
        self._asset_rows.clear()
        return len(final)

    def iter_assets(self) -> Iterator[dict]:
        if not self.assets_path.exists():
            return iter(())
        return iter(pq.read_table(self.assets_path).to_pylist())

"""Idempotently create the object-store buckets (Compose job service)."""

from __future__ import annotations

from openpali.storage.objects import ALL_BUCKETS, ObjectStore


def main() -> int:
    store = ObjectStore()
    for bucket in ALL_BUCKETS:
        store.ensure_bucket(bucket)
        print(f"bucket ready: {bucket}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

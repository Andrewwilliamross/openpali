"""Read hash-verified immutable evidence artifacts; never infer latest per source."""
from functools import lru_cache
import json
from pathlib import Path
import re
from openpali.intelligence.build import digest


class EvidenceRepository:
    def __init__(self, root):
        self.root=Path(root)
        # (release, file) pairs whose bytes have matched their manifest hash.
        # Releases are immutable, so one verification per process is enough:
        # re-hashing megabytes on every request bought nothing.
        self._verified=set()

    def current(self):
        return json.loads((self.root/'current.json').read_bytes())

    @lru_cache(maxsize=8)
    def manifest(self, release_id):
        if not re.fullmatch(r'evidence-[a-f0-9]{24}',release_id):
            raise ValueError('invalid release identifier')
        manifest=json.loads((self.root/release_id/'manifest.json').read_bytes())
        if manifest['release_id'] != release_id:
            raise ValueError('manifest identity mismatch')
        return manifest

    @lru_cache(maxsize=8)
    def release(self, release_id):
        manifest=self.manifest(release_id)
        body=(self.root/release_id/'release.json').read_bytes()
        if digest(body)!=manifest['artifacts']['release.json']['sha256']:
            raise ValueError('release integrity failure')
        data=json.loads(body)
        if data['release_id']!=release_id: raise ValueError('release identity mismatch')
        return data

    def artifact(self, release_id, name, gzip=False):
        """(body, sha256, encoding). `gzip=True` returns the release's own
        pre-compressed sibling when it has one; encoding is then 'gzip'."""
        self.release(release_id)
        entry=self.manifest(release_id)['artifacts'].get(name)
        if entry is None or Path(name).name != name:
            raise FileNotFoundError(name)
        packed=entry.get('gzip') if gzip else None
        filename,expected=(name+'.gz',packed['sha256']) if packed else (name,entry['sha256'])
        body=(self.root/release_id/filename).read_bytes()
        key=(release_id,filename)
        if key not in self._verified:
            if digest(body)!=expected:
                raise ValueError('artifact integrity failure')
            self._verified.add(key)
        return body,expected,('gzip' if packed else None)

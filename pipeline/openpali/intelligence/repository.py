"""Read hash-verified immutable evidence artifacts; never infer latest per source."""
from functools import lru_cache
import json
from pathlib import Path
import re
from openpali.intelligence.build import digest


class EvidenceRepository:
    def __init__(self, root):
        self.root=Path(root)

    def current(self):
        return json.loads((self.root/'current.json').read_bytes())

    @lru_cache(maxsize=8)
    def release(self, release_id):
        if not re.fullmatch(r'evidence-[a-f0-9]{24}',release_id):
            raise ValueError('invalid release identifier')
        directory=self.root/release_id
        manifest=json.loads((directory/'manifest.json').read_bytes())
        if manifest['release_id'] != release_id:
            raise ValueError('manifest identity mismatch')
        body=(directory/'release.json').read_bytes()
        if digest(body)!=manifest['artifacts']['release.json']['sha256']:
            raise ValueError('release integrity failure')
        data=json.loads(body)
        if data['release_id']!=release_id: raise ValueError('release identity mismatch')
        return data

    def artifact(self, release_id, name):
        self.release(release_id)
        directory=self.root/release_id
        manifest=json.loads((directory/'manifest.json').read_bytes())
        if name not in manifest['artifacts'] or Path(name).name != name:
            raise FileNotFoundError(name)
        body=(directory/name).read_bytes()
        sha=digest(body)
        if sha!=manifest['artifacts'][name]['sha256']:
            raise ValueError('artifact integrity failure')
        return body,sha

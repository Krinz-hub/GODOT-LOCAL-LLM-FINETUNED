import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import unittest

from logic_pipeline.provenance import compute_sha256, ProvenanceMetadata


class TestProvenance(unittest.TestCase):
    def test_sha256_computation(self):
        text = "extends Node\nfunc _ready():\n    pass\n"
        h1 = compute_sha256(text)
        h2 = compute_sha256(text)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)

    def test_provenance_lifecycle(self):
        prov = ProvenanceMetadata(
            source_id="local:sample:player.gd",
            source_type="local",
            source_url="file:///path/to/player.gd",
            repository="sample_repo",
            license="MIT",
            raw_hash="abcdef12345",
        )
        prov.add_transformation("normalize")
        prov.add_transformation("clean")

        self.assertEqual(len(prov.transformations), 2)
        self.assertTrue(prov.transformations[0].startswith("normalize@"))

        # Test dictionary serialization and restoration
        d = prov.to_dict()
        restored = ProvenanceMetadata.from_dict(d)
        self.assertEqual(restored.source_id, "local:sample:player.gd")
        self.assertEqual(restored.license, "MIT")
        self.assertEqual(len(restored.transformations), 2)

    def test_provenance_merging(self):
        p1 = ProvenanceMetadata(source_id="s1", source_type="local", source_url="url1", license="MIT")
        p2 = ProvenanceMetadata(source_id="s2", source_type="github", source_url="url2", license="Apache-2.0")

        p1.merge_with(p2)
        self.assertEqual(len(p1.secondary_sources), 1)
        self.assertEqual(p1.secondary_sources[0]["source_id"], "s2")
        self.assertEqual(p1.secondary_sources[0]["license"], "Apache-2.0")


if __name__ == "__main__":
    unittest.main()

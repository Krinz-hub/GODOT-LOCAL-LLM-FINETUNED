import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import tempfile
import unittest

from logic_pipeline.checkpoints import CheckpointManager


class TestResume(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.ckpt_path = Path(self.tmp_dir.name) / "test_checkpoint.json"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_checkpoint_lifecycle(self):
        # 1. Initialize checkpoint and mark items
        ckpt = CheckpointManager(self.ckpt_path)
        self.assertFalse(ckpt.is_completed("item_1"))
        ckpt.mark_completed("item_1", {"status": "ok"})
        ckpt.mark_completed("item_2")
        ckpt.save()

        self.assertTrue(self.ckpt_path.exists())

        # 2. Re-load from disk
        ckpt_reloaded = CheckpointManager(self.ckpt_path)
        self.assertTrue(ckpt_reloaded.is_completed("item_1"))
        self.assertTrue(ckpt_reloaded.is_completed("item_2"))
        self.assertFalse(ckpt_reloaded.is_completed("item_3"))
        self.assertEqual(ckpt_reloaded.metadata.get("item_1"), {"status": "ok"})

    def test_checkpoint_clear(self):
        ckpt = CheckpointManager(self.ckpt_path)
        ckpt.mark_completed("item_1")
        ckpt.save()

        ckpt.clear()
        self.assertFalse(ckpt.is_completed("item_1"))
        self.assertFalse(self.ckpt_path.exists())


if __name__ == "__main__":
    unittest.main()

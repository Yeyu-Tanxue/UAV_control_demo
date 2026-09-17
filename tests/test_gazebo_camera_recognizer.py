import json
import tempfile
import unittest
from pathlib import Path

from uav_demo.recognition import GazeboCameraRecognizer


class GazeboCameraRecognizerTests(unittest.IsolatedAsyncioTestCase):
    async def test_copies_only_frames_created_during_recognition_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "spool"
            source.mkdir()
            output = root / "captures"
            calls = 0

            async def fake_sleep(delay_s: float) -> None:
                nonlocal calls
                calls += 1
                if calls == 1:
                    (source / "camera_0001.png").write_bytes(b"valid-png-placeholder")

            recognizer = GazeboCameraRecognizer(
                duration_s=3.0,
                source_dir=source,
                output_root=output,
                sleep=fake_sleep,
            )

            result = await recognizer.recognize(1)
            cycle_dir = recognizer.output_dir / "cycle_01"
            copied = list(cycle_dir.glob("frame_*.png"))
            metadata = json.loads((cycle_dir / "metadata.json").read_text())

        self.assertTrue(result.accepted)
        self.assertEqual(len(copied), 1)
        self.assertEqual(copied[0].name, "frame_0001.png")
        self.assertEqual(metadata["frame_count"], 1)
        self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()

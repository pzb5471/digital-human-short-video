import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_remotion import PreparationError, prepare_remotion


class PrepareRemotionTests(unittest.TestCase):
    def test_copies_owned_assets_and_uses_public_paths_and_ceil_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "assets").mkdir()
            for name in ("original.mp4", "logo.png", "product.png", "bgm.mp3"):
                (root / "assets" / name).write_bytes(name.encode())
            project = {"provider_original":"assets/original.mp4","logo":"assets/logo.png","bgm":"assets/bgm.mp3","broll":[{"path":"assets/product.png","start_ms":1,"end_ms":1001}],"cta":"现在购买","hook":"新品发布"}
            project_path=root/"project.json"; project_path.write_text(json.dumps(project),encoding="utf-8")
            props=prepare_remotion(project_path, root/"template"/"public"/"project")
            self.assertEqual("project/original.mp4",props["primaryVideo"])
            self.assertEqual(1,props["broll"][0]["from"])
            self.assertEqual(30,props["broll"][0]["durationInFrames"])
            self.assertTrue((root/"template"/"public"/"project"/"product.png").is_file())
            self.assertGreater(props["durationInFrames"], 0)

    def test_rejects_asset_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); outside=root.parent/"outside.mp4"; outside.write_bytes(b"x")
            project=root/"project.json"; project.write_text(json.dumps({"provider_original":"../outside.mp4"}),encoding="utf-8")
            with self.assertRaises(PreparationError): prepare_remotion(project,root/"template"/"public"/"project")

    def test_requires_primary_and_exact_ceil_boundary_and_fixed_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); project=root/"project.json"; project.write_text("{}",encoding="utf-8")
            with self.assertRaises(PreparationError): prepare_remotion(project,root/"template"/"public"/"project")
            (root/"primary.mp4").write_bytes(b"video")
            project.write_text(json.dumps({"provider_original":"primary.mp4","duration_ms":1001}),encoding="utf-8")
            with self.assertRaises(PreparationError): prepare_remotion(project,root/"wrong")
            props=prepare_remotion(project,root/"template"/"public"/"project")
            self.assertEqual(31,props["durationInFrames"])

    def test_rejects_windows_absolute_symlink_escape_and_name_collision(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/"a").mkdir(); (root/"b").mkdir()
            (root/"a"/"card.png").write_bytes(b"a"); (root/"b"/"card.png").write_bytes(b"b")
            project=root/"project.json"
            project.write_text(json.dumps({"provider_original":r"C:\\outside.mp4"}),encoding="utf-8")
            with self.assertRaises(PreparationError): prepare_remotion(project,root/"template"/"public"/"project")
            project.write_text(json.dumps({"provider_original":"a/card.png","broll":[{"path":"b/card.png","start_ms":0,"end_ms":1000}]}),encoding="utf-8")
            with self.assertRaises(PreparationError): prepare_remotion(project,root/"template"/"public"/"project")
            link=root/"a"/"escape.png"
            try: link.symlink_to(root.parent/"outside.png")
            except OSError: self.skipTest("symlink creation unavailable")
            project.write_text(json.dumps({"provider_original":"a/escape.png"}),encoding="utf-8")
            with self.assertRaises(PreparationError): prepare_remotion(project,root/"template"/"public"/"project")

    def test_template_contract_integrates_timed_captions_and_sections(self):
        template=Path(__file__).resolve().parents[1]/"template"/"src"
        video=(template/"Video.tsx").read_text(encoding="utf-8")
        root=(template/"Root.tsx").read_text(encoding="utf-8")
        self.assertIn("<Captions",video)
        self.assertIn("from={durationInFrames-90}",video)
        self.assertIn("durationInFrames={90}",video)
        self.assertIn("calculateMetadata",root)
        self.assertIn("volume={(frame)=>",video)
        self.assertIn("objectFit:'cover'",video)
        self.assertIn("zIndex:0",video)
        self.assertIn("zIndex:1",video)
        package=(template.parent/"package.json").read_text(encoding="utf-8")
        self.assertIn("verify-render.mjs",package)
        fixtures=(template/"fixtures.ts").read_text(encoding="utf-8")
        self.assertIn("captions",fixtures)
        self.assertIn("broll",fixtures)
        captions=(template/"Captions.tsx").read_text(encoding="utf-8")
        self.assertIn("visualLines",captions)
        self.assertNotIn("<div>{cue.words.map",captions)

    def test_prepare_maps_multiple_words_to_at_most_two_visual_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/"primary.mp4").write_bytes(b"video")
            cue={"start_ms":0,"end_ms":1000,"lines":["第一行文本","第二行文本"],"words":[{"text":"第一行","start_ms":0,"end_ms":400,"highlight":True},{"text":"文本","start_ms":400,"end_ms":500,"highlight":False},{"text":"第二行","start_ms":500,"end_ms":800,"highlight":True},{"text":"文本","start_ms":800,"end_ms":1000,"highlight":False}]}
            project=root/"project.json";project.write_text(json.dumps({"provider_original":"primary.mp4","captions":[cue]}),encoding="utf-8")
            props=prepare_remotion(project,root/"template"/"public"/"project")
            self.assertEqual([0,0,1,1],[word["line"] for word in props["captions"][0]["words"]])

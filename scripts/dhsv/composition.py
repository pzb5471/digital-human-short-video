import json
import os
import subprocess
from pathlib import Path

from prepare_remotion import prepare_remotion

from .verify import verify_video, write_verification_manifest


class RemotionComposer:
    def __init__(self, project_file, runtime, template_dir):
        self.project_file = Path(project_file).resolve()
        self.project_root = self.project_file.parent
        self.runtime = Path(runtime).resolve()
        self.template_dir = Path(template_dir).resolve()

    def _atomic_json(self, path, value):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def _composition_document(self, original, state):
        project = json.loads(self.project_file.read_text(encoding="utf-8"))
        script_path = Path(str(state.artifacts["script_draft_path"]))
        script = json.loads(script_path.read_text(encoding="utf-8"))
        captions_path = Path(str(state.artifacts["captions_json_path"]))
        captions = json.loads(captions_path.read_text(encoding="utf-8"))
        hook = next(
            (
                str(segment.get("subtitle_text") or segment.get("spoken_text") or "")
                for segment in script.get("segments", [])
                if segment.get("role") == "hook"
            ),
            "",
        )
        cta = next(
            (
                str(segment.get("subtitle_text") or segment.get("spoken_text") or "")
                for segment in script.get("segments", [])
                if segment.get("role") == "cta"
            ),
            "",
        )
        if isinstance(project.get("hook"), str):
            hook = project["hook"]
        if isinstance(project.get("cta"), str):
            cta = project["cta"]
        document = {
            "provider_original": str(Path(original).resolve().relative_to(self.project_root)),
            "duration_ms": captions["duration_ms"],
            "captions": captions["cues"],
            "hook": hook,
            "cta": cta,
        }
        for name in ("logo", "brand_background", "bgm", "broll"):
            if name in project:
                document[name] = project[name]
        return document

    def __call__(self, original, destination, state):
        composition_path = self.runtime / "composition.json"
        self._atomic_json(composition_path, self._composition_document(original, state))
        props_path = self.template_dir / "src" / "fixture-props.json"
        original_props = props_path.read_bytes() if props_path.is_file() else None
        executable = self.template_dir / "node_modules" / ".bin" / (
            "remotion.cmd" if os.name == "nt" else "remotion"
        )
        if not executable.is_file():
            raise RuntimeError(
                f"Remotion is not installed under {self.template_dir}; run npm install"
            )
        destination = Path(destination).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            prepare_remotion(
                composition_path,
                self.template_dir / "public" / "project",
                project_root=self.project_root,
            )
            subprocess.run(
                [
                    str(executable),
                    "render",
                    "src/index.ts",
                    "DigitalHumanShortVideo",
                    str(destination),
                    "--props=src/fixture-props.json",
                    "--codec=h264",
                    "--pixel-format=yuv420p",
                    "--concurrency=2",
                ],
                cwd=self.template_dir,
                check=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
            )
        finally:
            if original_props is None:
                if props_path.exists():
                    props_path.unlink()
            else:
                props_path.write_bytes(original_props)
        return {
            "watermark_layers_omitted": True,
            "watermark_removal_postprocessing": False,
        }


class ProductVerifier:
    def __init__(self, runtime):
        self.runtime = Path(runtime).resolve()

    def __call__(self, output, state):
        manifest_path = self.runtime / "verification-manifest.json"
        report_dir = self.runtime / "verification"
        write_verification_manifest(state, manifest_path)
        report = verify_video(
            output,
            state.artifacts["captions_json_path"],
            state.artifacts["narration_path"],
            manifest_path,
            report_dir,
        )
        return {
            **report,
            "manifest_path": str(manifest_path),
            "report_path": str(report_dir / "verification.json"),
        }

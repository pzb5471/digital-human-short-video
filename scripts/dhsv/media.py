import subprocess
import json
from pathlib import Path


class MediaError(RuntimeError): pass

class FFmpegMedia:
    def __init__(self, runner=subprocess.run): self.runner = runner
    def concat_and_normalize(self, inputs, output):
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        command = ["ffmpeg", "-y"]
        filters, stream_index = [], 0
        for path, pause_ms in inputs:
            command.extend(["-i", str(path)])
            filters.append(f"[{stream_index}:a]")
            stream_index += 1
            if pause_ms:
                command.extend(["-f", "lavfi", "-t", f"{pause_ms / 1000:.3f}", "-i", "anullsrc=r=24000:cl=mono"])
                filters.append(f"[{stream_index}:a]")
                stream_index += 1
        command.extend(["-filter_complex", "".join(filters) + f"concat=n={stream_index}:v=0:a=1,loudnorm=I=-16:TP=-1:LRA=11[a]", "-map", "[a]", str(output)])
        self.runner(command, check=True)
    def duration_ms(self, path):
        try:
            result = self.runner(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)], check=True, capture_output=True, text=True)
            duration = float(json.loads(result.stdout)["format"]["duration"])
        except (subprocess.CalledProcessError, OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise MediaError(f"cannot probe audio duration: {path}") from exc
        if duration <= 0:
            raise MediaError("audio duration must be positive")
        return round(duration * 1000)

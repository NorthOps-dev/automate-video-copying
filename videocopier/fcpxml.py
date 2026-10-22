from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from videocopier.models import CutList


def _ts(seconds: float, fps: int = 30) -> str:
    frames = int(round(max(seconds, 0) * fps))
    return f"{frames}/{fps}s"


def write_fcpxml(cutlist: CutList, dest: Path, name: str = "VideoCopier") -> Path:
    assets: list[str] = []
    clips: list[str] = []
    offset = 0.0
    asset_ids: dict[str, str] = {}
    n = 1
    for slot in cutlist.slots:
        if slot.status != "filled" or not slot.source_path:
            offset += slot.duration
            continue
        src = Path(slot.source_path).resolve()
        key = str(src)
        if key not in asset_ids:
            aid = f"r{n}"
            n += 1
            asset_ids[key] = aid
            uri = src.as_uri()
            assets.append(
                f'      <asset id="{aid}" name="{escape(src.stem)}" src="{escape(uri)}" '
                f'start="0s" duration="{_ts(slot.source_out or slot.duration)}" hasVideo="1" hasAudio="1"/>'
            )
        aid = asset_ids[key]
        start = slot.source_in or 0.0
        clips.append(
            f'            <asset-clip ref="{aid}" offset="{_ts(offset)}" duration="{_ts(slot.duration)}" '
            f'start="{_ts(start)}" name="{escape(src.stem)}"/>'
        )
        offset += slot.duration

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.11">
  <resources>
    <format id="r0" name="FFVideoFormat1080p30" frameDuration="1/30s" width="1080" height="1920"/>
{chr(10).join(assets)}
  </resources>
  <library>
    <event name="{escape(name)}">
      <project name="{escape(name)}">
        <sequence format="r0" duration="{_ts(cutlist.duration)}" tcStart="0s" tcFormat="NDF">
          <spine>
{chr(10).join(clips)}
          </spine>
        </sequence>
      </project>
    </event>
  </library>
</fcpxml>
"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(xml, encoding="utf-8")
    return dest

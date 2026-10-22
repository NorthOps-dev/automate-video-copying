from __future__ import annotations

from pathlib import Path

from videocopier.analyze import analyze_reference
from videocopier.compile import compile_cut
from videocopier.fcpxml import write_fcpxml
from videocopier.index import index_footage
from videocopier.match import match_footage
from videocopier.media import list_videos
from videocopier.models import JobSpec, JobState
from videocopier.sources import resolve_footage, resolve_reference

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".work" / "jobs"


def job_dir(job_id: str) -> Path:
    return WORK / job_id


def load_state(job_id: str) -> JobState:
    path = job_dir(job_id) / "job.json"
    return JobState.model_validate_json(path.read_text())


def save_state(state: JobState) -> None:
    d = job_dir(state.id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "job.json").write_text(state.model_dump_json(indent=2))


def _log(state: JobState, message: str) -> None:
    state.step = message
    state.log.append(message)
    save_state(state)


def run_job(job_id: str) -> JobState:
    state = load_state(job_id)
    work = job_dir(job_id)
    state.status = "running"
    save_state(state)
    spec: JobSpec = state.spec
    try:
        _log(state, "Resolving reference video…")
        reference = resolve_reference(spec.reference, work, progress=lambda m: _log(state, m))
        _log(state, "Resolving footage folder…")
        footage = resolve_footage(spec.footage, work, progress=lambda m: _log(state, m))
        videos = list_videos(footage)
        if not videos:
            raise FileNotFoundError("No video files found in that footage folder.")
        _log(state, f"Using {len(videos)} clips")

        _log(state, "Analyzing reference edit…")
        blueprint = analyze_reference(reference, work / "ref", progress=lambda m: _log(state, m))
        (work / "blueprint.json").write_text(blueprint.model_dump_json(indent=2))

        _log(state, "Indexing your footage…")
        index = index_footage(footage, work / "idx", progress=lambda m: _log(state, m))
        (work / "index.json").write_text(index.model_dump_json(indent=2))

        _log(state, "Matching shots to clips…")
        cutlist = match_footage(blueprint, index, threshold=spec.match_threshold)
        cutlist_path = work / "cutlist.json"
        cutlist_path.write_text(cutlist.model_dump_json(indent=2))

        music = Path(spec.music).expanduser() if spec.music else None
        if music and not music.exists():
            music = None

        output = work / "output.mp4"
        compile_cut(
            blueprint,
            cutlist,
            work / "render",
            output,
            caption_mode=spec.caption_mode,
            music=music,
            progress=lambda m: _log(state, m),
        )
        xml_path = work / "output.fcpxml"
        write_fcpxml(cutlist, xml_path, name=f"VideoCopier-{job_id[:8]}")

        state.output_mp4 = str(output)
        state.output_xml = str(xml_path)
        state.output_cutlist = str(cutlist_path)
        state.unfilled = cutlist.unfilled
        state.status = "done"
        _log(state, "Done")
        return state
    except Exception as exc:
        state.status = "error"
        state.error = str(exc)
        _log(state, f"Error: {exc}")
        return state

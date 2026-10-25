from __future__ import annotations

from pathlib import Path

from videocopier.models import JobSpec, JobState

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
    from videocopier.board import BoardError, get_slot
    from videocopier.compile import compile_cut
    from videocopier.fcpxml import write_fcpxml
    from videocopier.knowledge import load_brief
    from videocopier.media import list_videos
    from videocopier.sources import resolve_footage, resolve_reference
    from videocopier.web_remake import remake_from_uploads

    state = load_state(job_id)
    work = job_dir(job_id)
    state.status = "running"
    save_state(state)
    spec: JobSpec = state.spec
    try:
        slot = None
        brief = {}
        if spec.reference.startswith("board:"):
            try:
                slot = get_slot(spec.reference.split(":", 1)[1])
            except BoardError as exc:
                _log(state, f"Board unavailable ({exc}); remaking from the video.")
                slot = None
            if slot:
                brief = load_brief(slot.get("clientId") or spec.client_id, slot.get("clientName") or "")
                who = brief.get("name") or slot.get("clientName") or "the client"
                _log(state, f"Remaking for {who}: {slot.get('hook') or 'approved format'}")

        _log(state, "Loading the approved format video…")
        reference = resolve_reference(spec.reference, work, progress=lambda m: _log(state, m))
        _log(state, "Loading uploaded footage…")
        footage = resolve_footage(
            spec.footage,
            work,
            progress=lambda m: _log(state, m),
            extra_paths=spec.footage_paths,
        )
        videos = list_videos(footage)
        if not videos:
            raise FileNotFoundError("Upload at least one video.")
        _log(state, f"Using {len(videos)} clip{'s' if len(videos) != 1 else ''}")

        blueprint, cutlist = remake_from_uploads(
            reference,
            footage,
            slot or {},
            brief,
            progress=lambda m: _log(state, m),
        )
        (work / "blueprint.json").write_text(blueprint.model_dump_json(indent=2))
        cutlist_path = work / "cutlist.json"
        cutlist_path.write_text(cutlist.model_dump_json(indent=2))

        output = work / "output.mp4"
        compile_cut(
            blueprint,
            cutlist,
            work / "render",
            output,
            caption_mode=spec.caption_mode,
            progress=lambda m: _log(state, m),
        )
        xml_path = work / "output.fcpxml"
        write_fcpxml(cutlist, xml_path, name=f"Prophet-{job_id[:8]}")

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

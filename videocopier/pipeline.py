from __future__ import annotations

from pathlib import Path

from videocopier.adapt import captions_from_design, tiktok_cards
from videocopier.rewrite import coalesce_cards, remake_for_client
from videocopier.analyze import analyze_reference
from videocopier.board import BoardError, get_slot
from videocopier.compile import compile_cut
from videocopier.fcpxml import write_fcpxml
from videocopier.index import index_footage
from videocopier.knowledge import load_brief
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
        slot = None
        brief = {}
        if spec.reference.startswith("board:"):
            try:
                slot = get_slot(spec.reference.split(":", 1)[1])
            except BoardError as exc:
                _log(state, f"Board script unavailable ({exc}); using reference analysis.")
                slot = None
            if slot:
                brief = load_brief(slot.get("clientId") or spec.client_id, slot.get("clientName") or "")
                who = brief.get("name") or slot.get("clientName") or "the client"
                _log(state, f"Remaking for {who}: {slot.get('hook') or 'approved format'}")
                if brief.get("one_liner"):
                    _log(state, f"Brief — {brief['one_liner']}")
                if slot.get("shotDirection"):
                    _log(state, "Using Board shot direction to pick takes.")

        _log(state, "Resolving the approved format video…")
        reference = resolve_reference(spec.reference, work, progress=lambda m: _log(state, m))
        _log(state, "Gathering client footage…")
        footage = resolve_footage(
            spec.footage,
            work,
            progress=lambda m: _log(state, m),
            extra_paths=spec.footage_paths,
        )
        videos = list_videos(footage)
        if not videos:
            raise FileNotFoundError("No video files found in that footage folder.")
        _log(state, f"Using {len(videos)} clips")

        _log(state, "Reading the approved cut (pacing + shot order)…")
        blueprint = analyze_reference(reference, work / "ref", progress=lambda m: _log(state, m))
        if spec.caption_mode != "footage":
            on_video = tiktok_cards(blueprint.captions)
            if on_video and spec.caption_mode in {"client", "auto"}:
                remade = coalesce_cards(remake_for_client(on_video, slot or {}, brief))
                blueprint.captions = remade or on_video
                _log(state, f"Using the words on the TikTok ({len(blueprint.captions)} cards)")
                for card in blueprint.captions:
                    preview = card.text.replace("\n", " / ")
                    _log(state, f"  {card.start:.1f}s  {preview[:80]}")
            elif on_video:
                blueprint.captions = on_video
                _log(state, f"Using the TikTok on-screen text ({len(on_video)} cards)")
            elif spec.caption_mode in {"client", "auto"} and slot:
                client_caps = captions_from_design(slot, brief, blueprint.captions, blueprint.duration)
                if client_caps:
                    blueprint.captions = client_caps
                    _log(state, f"No TikTok cards — using Board copy ({len(client_caps)} cards)")
        (work / "blueprint.json").write_text(blueprint.model_dump_json(indent=2))

        _log(state, "Indexing your footage…")
        index = index_footage(footage, work / "idx", progress=lambda m: _log(state, m))
        (work / "index.json").write_text(index.model_dump_json(indent=2))

        _log(state, "Picking the strongest takes for this format…")
        cutlist = match_footage(
            blueprint,
            index,
            threshold=spec.match_threshold,
            shot_direction=(slot or {}).get("shotDirection") or "",
        )
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

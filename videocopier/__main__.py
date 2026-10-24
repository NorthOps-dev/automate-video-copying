from __future__ import annotations

import argparse
from pathlib import Path

from videocopier.models import JobSpec, JobState
from videocopier.pipeline import run_job, save_state


def main() -> None:
    parser = argparse.ArgumentParser(prog="prophet", description="NorthOps Prophet — remake an approved TikTok format for a client.")
    sub = parser.add_subparsers(dest="cmd")

    serve = sub.add_parser("serve", help="Open the local web app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    run = sub.add_parser("run", help="Run a job from the CLI")
    run.add_argument("--reference", required=True, help="Local file, TikTok/YouTube URL, or Drive link")
    run.add_argument("--footage", required=True, help="Local folder or Google Drive folder link")
    run.add_argument("--music", default=None, help="Optional licensed/original track")
    run.add_argument("--captions", default="client", choices=["client", "auto", "reference", "footage"])
    run.add_argument("--out", default=None, help="Copy finished mp4 here")

    parser.set_defaults(cmd="serve", host="127.0.0.1", port=8000)
    args = parser.parse_args()

    if args.cmd == "run":
        spec = JobSpec(
            reference=args.reference,
            footage=args.footage,
            music=args.music,
            caption_mode=args.captions,
        )
        job_id = "cli"
        save_state(JobState(id=job_id, spec=spec))
        state = run_job(job_id)
        if state.status != "done" or not state.output_mp4:
            raise SystemExit(state.error or "Job failed")
        if args.out:
            dest = Path(args.out).expanduser()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(Path(state.output_mp4).read_bytes())
            print(dest)
        else:
            print(state.output_mp4)
        if state.unfilled:
            print("Film these missing shots:")
            for item in state.unfilled:
                print(f"  - {item}")
        return

    import uvicorn

    print(f"NorthOps Prophet → http://{args.host}:{args.port}")
    uvicorn.run("videocopier.server:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()

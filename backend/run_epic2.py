"""End-to-end check of Epic 2: transcript.json -> clean (Nano) -> topic split (Nano).

Usage (from backend/):  python run_epic2.py <transcript.json> [--job JOB_ID]

Creates a fresh job in the storage (backend/.data/ by default, ignored by git), saves the transcript,
runs clean_job and split_job, prints the sections table and the cost of THIS job from the call log.
--job JOB_ID reuses an existing job id: cleaning then only calls the batches that have no saved
checkpoint (see clean.py). Real calls: about $0.02 for a 10-minute lecture.
"""
import json
import sys
import time

from dotenv import load_dotenv

load_dotenv()

import clean
import llm
import topics
from schemas import Segment
from storage import save_transcript


def run(transcript_path: str, job_id: str | None = None, storage=None, client=None) -> dict:
    segments = [Segment(**s) for s in json.loads(open(transcript_path, encoding="utf-8").read())]
    job_id = job_id or time.strftime("job_e2e_%Y%m%d_%H%M%S")
    save_transcript(job_id, segments, storage)
    started = time.time()
    cleaned = clean.clean_job(job_id, storage=storage, client=client)
    split = topics.split_job(job_id, storage=storage, client=client)
    return {
        "job_id": job_id,
        "clean_report": cleaned.report,
        "topics_report": split.report,
        "sections": split.sections,
        "summary": llm.summarize_log(job_id=job_id),
        "wall_sec": time.time() - started,
    }


def format_result(r: dict) -> str:
    cr, tr = r["clean_report"], r["topics_report"]
    lines = [f"job {r['job_id']}: {cr['total_segments']} segments, {r['wall_sec']:.0f} s",
             f"clean: {cr['batches']} batches ({cr['resumed_batches']} resumed), changed {cr['changed_count']}, "
             f"reverted {cr['reverted_count']} {cr['reverted_by_reason']}",
             f"topics: {tr['section_count']} sections, fallback used: {tr['used_fallback']}, flagged: {len(tr['flagged'])}",
             "", "id      start-end        segs  title"]
    for s in r["sections"]:
        lines.append(f"{s.id}  {s.start:7.1f}-{s.end:7.1f}  {len(s.segment_ids):4d}  {s.title}")
    lines += ["", "cost of this job (call log):", llm.format_summary(r["summary"])]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = [a for a in argv if not a.startswith("--")]
    job = argv[argv.index("--job") + 1] if "--job" in argv else None
    if job:
        args.remove(job)
    if len(args) != 1:
        print(__doc__)
        return 2
    print(format_result(run(args[0], job_id=job)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

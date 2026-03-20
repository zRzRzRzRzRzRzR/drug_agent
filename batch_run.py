import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from src.llm_client import GLMClient
from src.ocr import get_pdf_text
from src.ocr import init_extractor as init_ocr
from src.pipeline import DrugExtractionPipeline


def is_file_completed(file_path: Path, output_dir: Path) -> bool:
    """
    Check whether a file has already been fully processed.
    A file is considered complete if its output sub-directory contains final.json.
    """
    stem = file_path.stem
    final_file = output_dir / stem / "final.json"
    return final_file.exists()


def process_single_file(
    file_path: Path,
    pipeline: DrugExtractionPipeline,
    output_dir: Path,
    resume: bool = False,
) -> dict:
    t0 = time.time()

    # File-level skip: if final.json already exists, skip entirely
    if resume and is_file_completed(file_path, output_dir):
        final_file = output_dir / file_path.stem / "final.json"
        with open(final_file, "r", encoding="utf-8") as f:
            existing = json.load(f)
        n_effects = len(existing.get("effect_estimates", []))

        return {
            "file": file_path.name,
            "status": "skipped",
            "n_effects": n_effects,
            "elapsed_sec": 0,
            "error": None,
        }

    try:
        result = pipeline.run(
            pdf_path=str(file_path),
            output_dir=str(output_dir),
            resume=resume,
        )
        n_effects = len(result.get("effect_estimates", []))
        elapsed = round(time.time() - t0, 1)

        return {
            "file": file_path.name,
            "status": "success",
            "n_effects": n_effects,
            "confidence": result.get("metadata", {}).get("confidence", "?"),
            "elapsed_sec": elapsed,
            "error": None,
        }
    except Exception as e:
        elapsed = round(time.time() - t0, 1)
        print(f"  [ERROR] {file_path.name}: {e}", file=sys.stderr)
        return {
            "file": file_path.name,
            "status": "failed",
            "n_effects": 0,
            "elapsed_sec": elapsed,
            "error": str(e),
        }


def collect_files_from_dir(directory: Path) -> list[Path]:
    return sorted(directory.glob("*.pdf"))


def collect_batches(input_dir: Path) -> dict[str, list[Path]]:
    batches = {}
    subdirs = sorted([d for d in input_dir.iterdir() if d.is_dir()])
    for subdir in subdirs:
        files = collect_files_from_dir(subdir)
        if files:
            batches[subdir.name] = files
    if not batches:
        files = collect_files_from_dir(input_dir)
        if files:
            batches["_root"] = files
    return batches


def filter_completed_files(
    batches: dict[str, list[Path]], output_dir: Path
) -> tuple[dict[str, list[Path]], int]:
    filtered = {}
    n_skipped = 0
    for batch_name, files in batches.items():
        batch_output = output_dir if batch_name == "_root" else output_dir / batch_name
        pending = []
        for f in files:
            if is_file_completed(f, batch_output):
                n_skipped += 1
            else:
                pending.append(f)
        if pending:
            filtered[batch_name] = pending
    return filtered, n_skipped


def process_batch(
    batch_name: str,
    files: list[Path],
    pipeline: DrugExtractionPipeline,
    output_dir: Path,
    resume: bool,
    max_workers: int,
) -> list[dict]:
    batch_output = output_dir if batch_name == "_root" else output_dir / batch_name
    batch_output.mkdir(parents=True, exist_ok=True)

    results = []

    if max_workers <= 1:
        for idx, file_path in enumerate(files, 1):
            print(f"    [{idx}/{len(files)}] {file_path.name}", file=sys.stderr)
            summary = process_single_file(file_path, pipeline, batch_output, resume)
            summary["batch"] = batch_name
            results.append(summary)
            tag = {
                "skipped": "SKIP",
                "success": "OK",
            }.get(summary["status"], "FAIL")
            print(
                f"      [{tag}] {summary['n_effects']} effects, {summary['elapsed_sec']}s",
                file=sys.stderr,
            )
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {
                executor.submit(
                    process_single_file, p, pipeline, batch_output, resume
                ): p
                for p in files
            }
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    summary = future.result()
                except Exception as e:
                    summary = {
                        "file": file_path.name,
                        "status": "failed",
                        "n_effects": 0,
                        "elapsed_sec": 0,
                        "error": str(e),
                    }
                summary["batch"] = batch_name
                results.append(summary)
                tag = {
                    "skipped": "SKIP",
                    "success": "OK",
                }.get(summary["status"], "FAIL")
                print(
                    f"      [{tag}] {file_path.name}: {summary['n_effects']} effects, "
                    f"{summary['elapsed_sec']}s",
                    file=sys.stderr,
                )

    return results


def main():
    parser = argparse.ArgumentParser(description="Batch drug evidence extraction")
    parser.add_argument(
        "-i", "--input-dir", default="./evidence_card",
        help="Parent dir containing sub-folders of PDFs, or a flat dir of PDFs",
    )
    parser.add_argument("-o", "--output-dir", default="./output")
    parser.add_argument("--ocr-dir", default="./cache_ocr")
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--no-validate-pages", action="store_true")
    parser.add_argument("--model", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument(
        "--resume", action="store_true",
        help="Skip files whose final.json already exists",
    )
    parser.add_argument(
        "--batch-size", type=int, default=0,
        help="Max NEW files to process (0 = no limit)",
    )
    parser.add_argument(
        "--batches", nargs="*", default=None,
        help="Only process these sub-folder names",
    )

    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_batches = collect_batches(input_dir)
    if args.batches is not None:
        selected = set(args.batches)
        all_batches = {k: v for k, v in all_batches.items() if k in selected}

    total_found = sum(len(v) for v in all_batches.values())
    n_skipped_completed = 0
    if args.resume:
        all_batches, n_skipped_completed = filter_completed_files(all_batches, output_dir)

    if args.batch_size > 0:
        capped: dict[str, list[Path]] = {}
        remaining = args.batch_size
        for k, v in all_batches.items():
            take = v[:remaining]
            if take:
                capped[k] = take
            remaining -= len(take)
            if remaining <= 0:
                break
        all_batches = capped

    total_files = sum(len(v) for v in all_batches.values())

    print(f"{'='*60}", file=sys.stderr)
    print(f"Batch Drug Evidence Extraction", file=sys.stderr)
    print(f"  Input:   {input_dir.resolve()}", file=sys.stderr)
    print(f"  Output:  {output_dir.resolve()}", file=sys.stderr)
    print(f"  Batches: {len(all_batches)}", file=sys.stderr)
    print(f"  Total found: {total_found}", file=sys.stderr)
    if args.resume:
        print(f"  Already completed (skipped): {n_skipped_completed}", file=sys.stderr)
    print(f"  To process: {total_files}", file=sys.stderr)
    print(f"  Workers: {args.max_workers}", file=sys.stderr)
    print(f"  Resume:  {args.resume}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    if total_files == 0:
        if n_skipped_completed > 0:
            print(f"All {n_skipped_completed} files already completed.", file=sys.stderr)
        else:
            print("No input files found.", file=sys.stderr)
        sys.exit(0)

    client = GLMClient(api_key=args.api_key, base_url=args.base_url, model=args.model)

    pipeline = DrugExtractionPipeline(
        client=client,
        ocr_text_func=get_pdf_text,
        ocr_init_func=init_ocr,
        ocr_output_dir=args.ocr_dir,
        ocr_dpi=args.dpi,
        ocr_validate_pages=not args.no_validate_pages,
    )

    all_results = []
    batch_summaries = {}
    t_start = time.time()

    for batch_idx, (batch_name, files) in enumerate(all_batches.items(), 1):
        print(f"\n{'━'*60}", file=sys.stderr)
        print(
            f"  BATCH [{batch_idx}/{len(all_batches)}]: {batch_name} ({len(files)} PDFs)",
            file=sys.stderr,
        )
        print(f"{'━'*60}", file=sys.stderr)

        t_batch = time.time()
        batch_results = process_batch(
            batch_name=batch_name,
            files=files,
            pipeline=pipeline,
            output_dir=output_dir,
            resume=args.resume,
            max_workers=args.max_workers,
        )
        batch_elapsed = round(time.time() - t_batch, 1)

        all_results.extend(batch_results)

        n_ok = sum(1 for r in batch_results if r["status"] == "success")
        n_skip = sum(1 for r in batch_results if r["status"] == "skipped")
        n_effects = sum(r["n_effects"] for r in batch_results)
        batch_summaries[batch_name] = {
            "files": len(files),
            "success": n_ok,
            "skipped": n_skip,
            "failed": len(files) - n_ok - n_skip,
            "total_effects": n_effects,
            "elapsed_sec": batch_elapsed,
        }

    total_elapsed = round(time.time() - t_start, 1)
    n_success = sum(1 for r in all_results if r["status"] == "success")
    n_skipped = sum(1 for r in all_results if r["status"] == "skipped")
    n_failed = len(all_results) - n_success - n_skipped

    global_summary = {
        "total_files_found": total_found,
        "total_files_processed": total_files,
        "total_batches": len(all_batches),
        "success": n_success,
        "skipped": n_skipped + n_skipped_completed,
        "failed": n_failed,
        "total_effects": sum(r["n_effects"] for r in all_results),
        "total_elapsed_sec": total_elapsed,
        "batch_summaries": batch_summaries,
        "details": all_results,
    }

    summary_path = output_dir / "_batch_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(global_summary, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}", file=sys.stderr)
    print(
        f"Complete: {n_success}/{total_files} succeeded, "
        f"{n_skipped} skipped, {n_failed} failed, "
        f"{global_summary['total_effects']} total effects, {total_elapsed}s",
        file=sys.stderr,
    )
    print(f"  Summary: {summary_path}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    sys.exit(1 if n_failed == total_files else 0)


if __name__ == "__main__":
    main()

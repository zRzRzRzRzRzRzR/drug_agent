import argparse
import sys
from pathlib import Path


def clear_directory(dir_path: Path, dry_run: bool = False, indent: str = "") -> int:
    count = 0
    for item in sorted(dir_path.iterdir()):
        if item.is_dir():
            count += clear_directory(item, dry_run, indent=indent + "  ")
            if not dry_run:
                item.rmdir()
            print(f"{indent}  rmdir {item.name}", file=sys.stderr)
        else:
            count += 1
            if not dry_run:
                item.unlink()
            print(f"{indent}  rm {item.name}", file=sys.stderr)
    return count


def main():
    parser = argparse.ArgumentParser(
        description="清理未生成 final.json 的中间状态文件夹"
    )
    parser.add_argument("-o", "--output-dir", default="./output")
    parser.add_argument(
        "--batches", nargs="*", default=None, help="只清理指定的一级子文件夹名称"
    )
    parser.add_argument("--start", default=None, help="起始一级子文件夹名称（包含）")
    parser.add_argument("--end", default=None, help="结束一级子文件夹名称（包含）")
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if not output_dir.exists():
        print(f"输出目录不存在: {output_dir.resolve()}", file=sys.stderr)
        sys.exit(1)

    first_level_dirs = sorted([d for d in output_dir.iterdir() if d.is_dir()])

    if args.batches is not None:
        selected = set(args.batches)
        first_level_dirs = [d for d in first_level_dirs if d.name in selected]
    else:
        names = [d.name for d in first_level_dirs]
        start_idx = 0
        end_idx = len(names)
        if args.start:
            if args.start not in names:
                print(f"起始批次不存在: {args.start}", file=sys.stderr)
                sys.exit(1)
            start_idx = names.index(args.start)
        if args.end:
            if args.end not in names:
                print(f"结束批次不存在: {args.end}", file=sys.stderr)
                sys.exit(1)
            end_idx = names.index(args.end) + 1
        first_level_dirs = first_level_dirs[start_idx:end_idx]

    total_cleared = 0
    total_skipped = 0
    total_files = 0

    for first_dir in first_level_dirs:
        print(f"\n[{first_dir.name}]", file=sys.stderr)
        second_level_dirs = sorted([d for d in first_dir.iterdir() if d.is_dir()])
        for second_dir in second_level_dirs:
            if (second_dir / "final.json").exists() or (
                second_dir / "final_1.json"
            ).exists():
                print(f"  SKIP  {second_dir.name} (final.json exists)", file=sys.stderr)
                total_skipped += 1
                continue

            action = "would CLEAR" if args.dry_run else "CLEAR"
            print(f"  {action} {second_dir.name}", file=sys.stderr)
            n_files = clear_directory(second_dir, dry_run=args.dry_run, indent="  ")
            total_files += n_files
            total_cleared += 1

    print(f"\n{'='*60}", file=sys.stderr)
    mode_str = "Dry-run" if args.dry_run else "Done"
    print(
        f"{mode_str}: {total_cleared} dirs cleared, {total_skipped} dirs skipped, "
        f"{total_files} files removed",
        file=sys.stderr,
    )
    print(f"{'='*60}", file=sys.stderr)


if __name__ == "__main__":
    main()

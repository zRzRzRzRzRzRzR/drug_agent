import argparse
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path


def pack_one(batch_dir: Path, dst_dir: Path, level: int, overwrite: bool):
    out = dst_dir / f"{batch_dir.name}.tar.zst"
    if out.exists() and not overwrite:
        return batch_dir.name, "skip", out.stat().st_size

    tmp = out.with_suffix(".tar.zst.tmp")
    cmd = [
        "tar",
        "--use-compress-program", f"zstd -{level} -T0",
        "-cf", str(tmp),
        "-C", str(batch_dir.parent),
        batch_dir.name,
    ]
    try:
        subprocess.run(cmd, check=True, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        tmp.unlink(missing_ok=True)
        return batch_dir.name, f"error: {e.stderr.decode()[:200]}", 0
    tmp.rename(out)
    return batch_dir.name, "done", out.stat().st_size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path, help="源目录,里面包含 batch_* 子目录")
    ap.add_argument("dst", type=Path, help="输出目录,每个 batch 一个 .tar.zst")
    ap.add_argument("-j", "--jobs", type=int, default=4, help="并行数 (默认 4)")
    ap.add_argument("-l", "--level", type=int, default=10,
                    help="zstd 压缩等级 1-22 (默认 10,想更小用 19)")
    ap.add_argument("--pattern", default="batch_*", help="batch 目录匹配模式")
    ap.add_argument("--overwrite", action="store_true", help="覆盖已存在的压缩包")
    args = ap.parse_args()

    if not args.src.is_dir():
        sys.exit(f"源目录不存在: {args.src}")
    args.dst.mkdir(parents=True, exist_ok=True)

    batches = sorted(p for p in args.src.glob(args.pattern) if p.is_dir())
    if not batches:
        sys.exit(f"在 {args.src} 下没找到 {args.pattern}")

    print(f"待打包: {len(batches)} 个 batch -> {args.dst} "
          f"(并行={args.jobs}, zstd -{args.level})")

    total_size = 0
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        futs = {ex.submit(pack_one, b, args.dst, args.level, args.overwrite): b
                for b in batches}
        for i, fut in enumerate(as_completed(futs), 1):
            name, status, size = fut.result()
            total_size += size
            mb = size / 1e6
            print(f"[{i}/{len(batches)}] {name}  {status}  {mb:.1f}MB")

    print(f"\n完成,累计 {total_size/1e9:.2f} GB")


if __name__ == "__main__":
    main()
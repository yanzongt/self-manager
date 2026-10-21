"""统一处理运行参数、输出目录及图表保存。"""

import argparse
import json
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def create_parser(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--output-dir", type=Path, help="自定义输出目录（相对当前工作目录）"
    )
    parser.add_argument("--no-show", action="store_true", help="只保存图表，不打开窗口")
    cache_mode = parser.add_mutually_exclusive_group()
    cache_mode.add_argument(
        "--refresh-data",
        action="store_true",
        help="重新下载本次标的的完整历史并更新缓存",
    )
    cache_mode.add_argument(
        "--offline", action="store_true", help="只读取缓存，缺失时报错，禁止联网"
    )
    return parser


def prepare_run(name, description, config, *, args=None):
    if args is None:
        args = create_parser(description).parse_args()
    if args.no_show:
        import matplotlib

        matplotlib.use("Agg")
    output_dir = args.output_dir
    if output_dir is None:
        output_dir = (
            PROJECT_ROOT
            / "outputs"
            / name
            / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        )
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "script": name,
        "created_at": datetime.now().astimezone().isoformat(),
        "config": config,
        "data_options": {"refresh": args.refresh_data, "offline": args.offline},
    }
    (output_dir / "run_config.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"输出目录: {output_dir}")
    return (
        output_dir,
        not args.no_show,
        {
            "refresh": args.refresh_data,
            "offline": args.offline,
            "report_path": output_dir / "run_config.json",
        },
    )


def save_plot(output_dir, filename, show=True):
    import matplotlib.pyplot as plt

    plt.savefig(output_dir / filename, dpi=150, bbox_inches="tight")
    if show:
        plt.show()
    plt.close()

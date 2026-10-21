import argparse
import importlib
import sys


def main():
    parser = argparse.ArgumentParser(
        description="金融数据分析脚本入口",
        usage="%(prog)s SCRIPT [--output-dir DIR] [--no-show] [--refresh-data | --offline]",
    )
    parser.add_argument(
        "script",
        choices=[
            "correlation_analysis",
            "rebalance_comparison",
            "rebalance_analysis",
            "etf_pair_scan",
            "single_stock_backtest",
            "portfolio_backtest",
            "web",
        ],
    )
    parser.add_argument("args", nargs=argparse.REMAINDER, help="传递给分析脚本的参数")
    args = parser.parse_args()
    sys.argv = [args.script, *args.args]
    importlib.import_module(f"scripts.{args.script}").main()


if __name__ == "__main__":
    main()

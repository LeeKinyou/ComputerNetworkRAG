"""学习路径构建脚本（docs/09 §3.3 / Task 5.5）。

在仓库根目录运行（`.env` 与 `data/lightrag` 都按当前目录解析）：

  uv run python -m scripts.build_learning_path --all              # 物化 + 全部章
  uv run python -m scripts.build_learning_path --chapter 4        # 只重建第 4 章的边
  uv run python -m scripts.build_learning_path --all --nodes-only # 只物化归章，不调 LLM

`--nodes-only` 零额度消耗，也是大屏"章节知识点分布"那张图的数据来源；
带 LLM 的抽边每一步都要花钱，所以刻意不挂任何 HTTP 接口，只能手动跑。
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings                       # noqa: E402
from app.rag import lightrag_factory                      # noqa: E402
from app.services import path_service                     # noqa: E402
from app.storage.sqlite_repo import SqliteRepository      # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构建学习路径（物化知识点 + 章内前驱边）")
    parser.add_argument("--all", action="store_true", help="处理物化结果里出现的全部章节")
    parser.add_argument("--chapter", type=int, action="append", dest="chapters",
                        default=[], metavar="N", help="章号，可重复")
    parser.add_argument("--top-n", type=int, default=path_service.DEFAULT_TOP_N,
                        help=f"每章参与抽边的知识点上限（默认 {path_service.DEFAULT_TOP_N}）")
    parser.add_argument("--nodes-only", action="store_true", help="只物化归章，不调 LLM")
    return parser.parse_args(argv)


async def main(argv=None) -> int:
    args = parse_args(argv)
    if not args.all and not args.chapters:
        print("至少要给 --all 或 --chapter N", file=sys.stderr)
        return 2

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    print(f"模型 {settings.LLM_MODEL}｜每章 Top {args.top_n} 知识点｜"
          f"预计 LLM 调用 {len(args.chapters) or '全部章'} 次")

    repo = SqliteRepository(DATA_DIR / "app.db")
    await repo.init()
    await lightrag_factory.init_lightrag()
    try:
        built = await path_service.materialize(repo)
        relinked = await repo.relink_touch_kp_ids()
        print(f"物化知识点 {built['nodes']} 个：归章 {built['in_chapter']}、"
              f"未识别 {built['no_chapter']}；章节 {sorted(built['chapters'])}；"
              f"回填触达 {relinked} 行")
        if args.nodes_only:
            return 0

        chapters = sorted(set(args.chapters)) if not args.all else sorted(built["chapters"])
        failed = []
        for chapter in chapters:
            report = await path_service.build_chapter(
                repo, chapter, lightrag_factory.complete, top_n=args.top_n
            )
            flag = "OK " if report["passed"] else "FAIL"
            print(f"[{flag}] 第 {chapter} 章：知识点 {report['nodes']}，"
                  f"保留边 {report['kept']}，丢弃 {sum(report['dropped'].values())} "
                  f"{report['dropped']}，破环 {report['removed_cycles']}，"
                  f"丢弃率 {report['drop_rate']:.0%}")
            if not report["passed"]:
                failed.append(chapter)

        if failed:
            print(f"丢弃率超 {path_service.MAX_DROP_RATE:.0%} 的章节：{failed}"
                  "——prompt 或知识点选取有问题，需人工介入", file=sys.stderr)
            return 1
        return 0
    finally:
        await lightrag_factory.close_lightrag()
        await repo.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

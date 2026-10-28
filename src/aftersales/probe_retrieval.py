"""独立开发问句探测；不是 E01–E15 正式评测器。"""

import argparse
import json
from pathlib import Path

from aftersales.data import load_dataset
from aftersales.retrieval import PolicyRetriever

DEVELOPMENT_QUERIES = (
    ("七天无理由退货的期限如何计算", "P01"),
    ("商品退回验货后原路到账需要几天", "P04"),
    ("不喜欢衣服退回邮费由谁承担", "P03"),
    ("衣服吊牌剪掉了是否影响退货", "P02"),
    ("退款多久能到账", "P04"),
    ("退货的钱多久返回账户", "P04"),
    ("你们支持花呗分期吗？", None),
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    dataset = load_dataset()
    retriever = PolicyRetriever(dataset.policies)
    results = []
    for query, expected in DEVELOPMENT_QUERIES:
        hits = retriever.search(query)
        results.append(
            {
                "query": query,
                "expected": expected,
                "threshold": float(dataset.settings.retrieval_threshold),
                "hits": [
                    {"id": h.policy.id, "score": h.score, "matched_field": h.matched_field}
                    for h in hits
                ],
            }
        )
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

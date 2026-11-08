#!/usr/bin/env python3
"""ModelTrace MCP 服务（stdio 传输）。

把 ModelTrace 的模型指纹归因能力包装为 MCP 工具，供 Codex 等 MCP 客户端调用：

- get_challenges      生成归因挑战题。会话内的主代理亲自逐题作答（不要调用任何
                      工具生成数字），再把答案交给 attribute_outputs，即可在
                      不提供任何 API Key 的情况下检测「当前会话主代理所用模型」
                      的指纹。
- attribute_outputs   对 1~3 份挑战回答做归因，返回模型家族与具体模型的概率。
- fingerprint_model   通过 OpenAI / Anthropic 兼容 API 自动探测指定模型：
                      程序自动发送挑战、收集回答并归因。base_url / api_key /
                      model 可省略，缺省时读环境变量 MODELTRACE_BASE_URL /
                      MODELTRACE_API_KEY / MODELTRACE_MODEL。
- list_bank_models    查看内置统一指纹库收录的模型与家族。

归因结果是当前指纹库内、均匀先验下的闭集概率，仅供参考，并非决定性证据；
未收录的模型会被归到最相似的现有候选。

运行：python mcp_server.py（stdio；日志打到 stderr，不污染协议通道）
"""
from __future__ import annotations

import os
from pathlib import Path

# 注意：stdio 传输要求 stdout 只承载 JSON-RPC 协议，本模块不要向 stdout 打印。
from mcp.server.fastmcp import FastMCP  # noqa: E402

from enrollment import bank_summary, test_automatic  # noqa: E402
from fingerprint import analyze_global_outputs, generate_challenges, load_bank  # noqa: E402

PROJECT = Path(__file__).resolve().parent
BANK_FILE = PROJECT / "data" / "unified_bank.json"

_bank: dict | None = None


def get_bank() -> dict:
    global _bank
    if _bank is None:
        _bank = load_bank(BANK_FILE)
    return _bank


def _summarize(result: dict) -> dict:
    """把归因原始结果压缩成适合智能体阅读的摘要。"""
    top = [
        {
            "model": item["model"],
            "display_name": item["display_name"],
            "family": item.get("family_name") or item.get("family"),
            "probability": round(float(item["probability"]), 4),
            "profile_similarity": round(float(item["profile_similarity"]), 4),
        }
        for item in result["results"][:5]
    ]
    summary = {
        "prediction": result["prediction"],
        "prediction_name": result["prediction_name"],
        "probability": round(float(result["probability"]), 4),
        "family_prediction": result.get("family_prediction_name") or result.get("family_prediction"),
        "family_probability": round(float(result.get("family_probability", 0.0)), 4),
        "family_probabilities": [
            {"family": fam["display_name"], "probability": round(float(fam["probability"]), 4)}
            for fam in result.get("family_probabilities", [])
        ],
        "top_candidates": top,
        "used_outputs": result["used_outputs"],
        "diagnostics": result["diagnostics"],
        "calibration": result.get("calibration"),
        "note": "闭集概率（仅在指纹库收录的模型之间比较），仅供参考，并非决定性证据。",
    }
    if "api_test" in result:
        summary["api_test"] = result["api_test"]
    return summary


mcp = FastMCP("modeltrace")


@mcp.tool()
def get_challenges(count: int = 3) -> dict:
    """生成 ModelTrace 归因挑战题（默认 3 条）。

    用途：在 Codex 等会话内检测「当前会话主代理所使用的模型」。
    流程：调用本工具拿到挑战题后，由主代理本人逐题直接作答——每题输出一串
    整数序列，不要调用任何工具、代码或随机数生成器；然后把每题的完整输出
    按顺序传给 attribute_outputs 完成归因。
    """
    if count < 1 or count > 3:
        raise ValueError("count 必须在 1 到 3 之间（归因校准按最多 3 份回答）。")
    challenges = generate_challenges(count)
    return {
        "challenges": challenges,
        "instructions": (
            "请由当前会话的主代理逐题作答：直接输出每题要求的整数序列，"
            "不要借助任何工具或代码。答完后，把每题的完整输出原文按顺序放进 "
            "attribute_outputs 的 responses 参数，并把每题的 expected_count "
            "按顺序放进 expected_counts 参数。"
        ),
    }


@mcp.tool()
def attribute_outputs(responses: list[str], expected_counts: list[int] | None = None) -> dict:
    """对挑战回答做模型指纹归因。

    responses: 1~3 份挑战回答的完整原文（只含数字序列的输出即可）。
    expected_counts: 与 responses 对应的每题期望数字个数（来自 get_challenges
    的 expected_count），可省略；省略时按最少 80 个有效数字验收。
    """
    if not responses:
        raise ValueError("responses 不能为空。")
    if expected_counts is not None and len(expected_counts) != len(responses):
        raise ValueError("expected_counts 必须与 responses 等长。")
    outputs = [
        {
            "text": text,
            "expected_count": (expected_counts[index] if expected_counts else 0),
        }
        for index, text in enumerate(responses)
    ]
    result = analyze_global_outputs(outputs, get_bank())
    return _summarize(result)


@mcp.tool()
def fingerprint_model(
    base_url: str = "",
    api_key: str = "",
    model: str = "",
    api_format: str = "auto",
    temperature: float | None = None,
) -> dict:
    """通过 API 自动探测某个模型的指纹并归因。

    程序会向 base_url 指向的 OpenAI Chat Completions 或 Anthropic Messages
    兼容接口自动发送 3 条挑战，收集有效回答后归因。

    参数缺省时依次读取环境变量：MODELTRACE_BASE_URL、MODELTRACE_API_KEY、
    MODELTRACE_MODEL。api_format 可为 auto / openai / anthropic。
    """
    base_url = (base_url or os.environ.get("MODELTRACE_BASE_URL", "")).strip()
    api_key = (api_key or os.environ.get("MODELTRACE_API_KEY", "")).strip()
    model = (model or os.environ.get("MODELTRACE_MODEL", "")).strip()
    missing = [
        name
        for name, value in (
            ("base_url / MODELTRACE_BASE_URL", base_url),
            ("api_key / MODELTRACE_API_KEY", api_key),
            ("model / MODELTRACE_MODEL", model),
        )
        if not value
    ]
    if missing:
        raise ValueError("缺少参数：" + "、".join(missing))
    if api_format not in ("auto", "openai", "anthropic"):
        raise ValueError("api_format 只能是 auto、openai 或 anthropic。")
    result = test_automatic(
        base_url=base_url,
        api_key=api_key,
        api_model=model,
        temperature=temperature,
        bank=get_bank(),
        api_format=api_format,
    )
    summary = _summarize(result)
    summary["tested_model_name"] = model
    summary["base_url"] = base_url
    return summary


@mcp.tool()
def list_bank_models() -> dict:
    """查看内置统一指纹库收录的家族与模型。"""
    bank = get_bank()
    families: dict[str, list[str]] = {}
    for model in bank["models"]:
        family = model.get("family_name") or model.get("family") or "models"
        families.setdefault(family, []).append(model["display_name"])
    return {"families": families, "summary": bank_summary(bank)}


if __name__ == "__main__":
    mcp.run(transport="stdio")

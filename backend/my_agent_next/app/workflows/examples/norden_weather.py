"""Example draft: Mabel extracts parameters, a Skill queries weather, Norden answers."""

import json
import re

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from my_agent_next.workflow_sdk import WorkflowRuntime


class Input(TypedDict):
    message: str


class State(Input, total=False):
    city: str
    weather_result: str
    answer: str


class Output(TypedDict):
    answer: str


async def extract_parameters(
    state: State,
    runtime: Runtime[WorkflowRuntime],
) -> dict:
    result = await runtime.context.call_agent(
        "mabel",
        {
            "message": (
                "你现在只负责填写天气工具参数。仅返回一个 JSON 对象，不要解释、不要代码块："
                '{"city":"城市或地区"}。如果用户没有提供地点，city 填 @auto_location。'
                "必须保留用户给出的地点，不要使用 IP 定位替代明确地点。用户输入：" + state["message"]
            )
        },
    )
    answer = str(result.get("answer", ""))
    match = re.search(r"\{.*?\}", answer, re.DOTALL)
    if not match:
        raise ValueError("梅贝尔没有返回天气参数 JSON。")
    payload = json.loads(match.group(0))
    city = str(payload.get("city", "")).strip()
    if not city:
        raise ValueError("梅贝尔返回的 city 为空。")
    return {"city": city}


async def query_weather(
    state: State,
    runtime: Runtime[WorkflowRuntime],
) -> dict:
    result = await runtime.context.call_skill(
        "weather-skill",
        {"city": state["city"]},
    )
    return {"weather_result": str(result.get("output", result))}


async def norden_answers(
    state: State,
    runtime: Runtime[WorkflowRuntime],
) -> dict:
    result = await runtime.context.call_agent(
        "analysis",
        {
            "message": (
                "请根据实际天气查询结果回答用户。不要编造结果中没有的数据。\n"
                "用户问题：" + state["message"] + "\n"
                "查询地点：" + state["city"] + "\n"
                "天气 Skill 结果：" + state["weather_result"]
            )
        },
    )
    return {"answer": str(result.get("answer", ""))}


def build_workflow():
    graph = StateGraph(
        State,
        context_schema=WorkflowRuntime,
        input_schema=Input,
        output_schema=Output,
    )
    graph.add_node("mabel_extracts_parameters", extract_parameters)
    graph.add_node("weather_skill", query_weather)
    graph.add_node("norden_answers", norden_answers)
    graph.add_edge(START, "mabel_extracts_parameters")
    graph.add_edge("mabel_extracts_parameters", "weather_skill")
    graph.add_edge("weather_skill", "norden_answers")
    graph.add_edge("norden_answers", END)
    return graph.compile()

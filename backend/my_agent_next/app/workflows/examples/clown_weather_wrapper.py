"""Nested example: Clown wraps the existing Norden weather workflow."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from my_agent_next.workflow_sdk import WorkflowRuntime


class Input(TypedDict):
    message: str


class State(Input, total=False):
    prepared_message: str
    weather_answer: str
    answer: str


class Output(TypedDict):
    answer: str


async def clown_opens(
    state: State,
    runtime: Runtime[WorkflowRuntime],
) -> dict:
    result = await runtime.context.call_agent(
        "xiaochou",
        {
            "message": (
                "先用一句简短有趣的话回应用户，再原样保留用户要查询的地点和天气意图，"
                "整理成可以继续交给天气工作流的问题。不要自行回答天气。\n"
                "用户输入：" + state["message"]
            )
        },
    )
    return {"prepared_message": str(result.get("answer", state["message"]))}


async def run_weather_workflow(
    state: State,
    runtime: Runtime[WorkflowRuntime],
) -> dict:
    result = await runtime.context.call_workflow(
        "weather_query",
        {"message": state["prepared_message"]},
    )
    return {"weather_answer": str(result.get("answer", ""))}


async def clown_closes(
    state: State,
    runtime: Runtime[WorkflowRuntime],
) -> dict:
    result = await runtime.context.call_agent(
        "xiaochou",
        {
            "message": (
                "下面是天气工作流已经核实的回答。请完整保留关键天气数据，"
                "用你自己的幽默风格给用户最终回答，不要编造新数据。\n"
                "用户原问题：" + state["message"] + "\n"
                "天气工作流回答：" + state["weather_answer"]
            )
        },
    )
    return {"answer": str(result.get("answer", state["weather_answer"]))}


def build_workflow():
    graph = StateGraph(
        State,
        context_schema=WorkflowRuntime,
        input_schema=Input,
        output_schema=Output,
    )
    graph.add_node("clown_opens", clown_opens)
    graph.add_node("norden_weather_workflow", run_weather_workflow)
    graph.add_node("clown_closes", clown_closes)
    graph.add_edge(START, "clown_opens")
    graph.add_edge("clown_opens", "norden_weather_workflow")
    graph.add_edge("norden_weather_workflow", "clown_closes")
    graph.add_edge("clown_closes", END)
    return graph.compile()

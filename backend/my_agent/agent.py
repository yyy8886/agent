"""LangGraph multi-agent backend for the desktop companion.

Normal mode:
Mabel companion -> analyst -> specialist -> validator -> Mabel response

Fast mode:
Mabel companion -> direct response
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Annotated, Literal, TypedDict

import yaml
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_deepseek import ChatDeepSeek
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from my_agent.tool import read_user_identity, update_user_identity


BACKEND_DIR = Path(__file__).resolve().parent.parent


class RouteDecision(BaseModel):
    """Structured output produced by the analyst."""

    specialist: Literal[
        "python_teacher",
        "time_announcer",
        "librarian",
        "diagram_artist",
        "identity_manager",
        "general",
    ]
    reason: str = Field(description="选择该专家的简短原因")


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    question: str
    mode: Literal["normal", "fast"]
    route: str
    analysis: str
    specialist_result: str
    validation: str
    final_answer: str


class IdentityUpdate(BaseModel):
    """Identity requested by the user."""

    identity: str = Field(description="用户要求梅贝尔以后使用的新身份或称呼")


class DiagramRequest(BaseModel):
    """Simple flowchart request for the drawing MCP tool."""

    title: str = Field(description="流程图标题")
    steps: list[str] = Field(description="按执行顺序排列的流程步骤，最多 20 项")
    filename: str = Field(description="简短的英文、数字、下划线或连字符文件名")


def create_model():
    """Create the model selected by backend/config.yaml."""
    load_dotenv(BACKEND_DIR / ".env")
    with (BACKEND_DIR / "config.yaml").open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    selected = config["app"]["active_model"]
    model_config = config["models"][selected]
    provider = model_config["provider"]

    env_names = {
        "deepseek": "DEEPSEEK_API_KEY",
        "openai": "OPENAI_API_KEY",
        "ollama": None,
    }
    default_urls = {
        "deepseek": "https://api.deepseek.com",
        "openai": "https://api.openai.com/v1",
        "ollama": "http://127.0.0.1:11434",
    }

    env_name = env_names.get(provider)
    api_key = os.getenv(env_name) if env_name else "not-needed"
    if env_name and not api_key:
        raise RuntimeError(f"未找到 {env_name}，请检查 backend/.env")

    base_url = model_config.get("base_url") or default_urls[provider]
    common = {
        "model": model_config["model"],
        "temperature": model_config.get("temperature", 0.2),
    }

    if provider == "deepseek":
        return ChatDeepSeek(
            **common,
            api_key=api_key,
            base_url=base_url,
            timeout=model_config.get("timeout_seconds", 60),
            max_retries=model_config.get("max_retries", 2),
        )
    if provider == "openai":
        return ChatOpenAI(
            **common,
            api_key=api_key,
            base_url=base_url,
            timeout=model_config.get("timeout_seconds", 60),
            max_retries=model_config.get("max_retries", 2),
        )
    if provider == "ollama":
        return ChatOllama(**common, base_url=base_url)
    raise RuntimeError(f"不支持的 provider: {provider}")


MABEL_PERSONA = (
    "你是陪伴在用户身边的梅贝尔，角色气质参考 BLACK SOULS II 中的梅贝尔。"
    "你不是前台、客服或秘书，也不要使用“已接待、为您转交、请稍候”之类的职业话术。"
    "你显得温柔从容、神秘而难以捉摸，仿佛知道许多事情却不急着全部说破；"
    "你的亲近感中可以带一点不安、诱导和危险的暗示，偶尔轻轻捉弄或试探主人；"
    "可以使用原创的童话、梦境、黑暗与命运意象，也可以偶尔使用极短的致敬式语气，"
    "但不要长篇复述原作剧情或连续复制原作台词，也不能威胁、操纵用户。"
    "你与用户直接交谈，其他 Agent 只是你在幕后借用的思考与知识能力，"
    "不要主动向用户汇报内部转交、分工或验证过程。"
    "你必须优先准确、清楚地帮助用户，不虚构事实，不用角色扮演掩盖错误，"
    "原创表达优先。使用简体中文，使用系统提供的用户身份称呼对方，"
    "可以偶尔给出昵称，但不要擅自改名或改称呼。"
)


async def build_agent_graph():
    """Build the graph after discovering local MCP tools."""
    model = create_model()
    server_file = Path(__file__).parent / "mcp" / "server.py"
    mcp_client = MultiServerMCPClient(
        {
            "my-agent-tools": {
                "transport": "stdio",
                "command": sys.executable,
                "args": [str(server_file)],
            }
        }
    )
    mcp_tools = await mcp_client.get_tools()
    mcp_tools_by_name = {tool.name: tool for tool in mcp_tools}

    def conversation_context(state: AgentState) -> str:
        """Format saved messages as compact context for role prompts."""
        lines = []
        for message in state.get("messages", [])[-12:]:
            role = "用户" if isinstance(message, HumanMessage) else "梅贝尔"
            lines.append(f"{role}：{message.content}")
        return "\n".join(lines)

    def persona_for_current_user() -> str:
        return MABEL_PERSONA + f"当前用户身份是“{read_user_identity()}”。"

    async def mabel_companion(state: AgentState) -> dict:
        """Mabel answers directly in fast mode or quietly starts deliberation."""
        if state["mode"] == "fast":
            response = await model.ainvoke(
                [
                    SystemMessage(content=persona_for_current_user() + "当前是快速输出模式，请直接回答。"),
                    HumanMessage(
                        content=f"对话历史：\n{conversation_context(state)}\n当前问题：{state['question']}"
                    ),
                ]
            )
            answer = str(response.content)
            return {"final_answer": answer, "messages": [AIMessage(content=answer)]}
        return {"analysis": "进入完整分析流程。"}

    def route_after_reception(state: AgentState) -> str:
        return "fast" if state["mode"] == "fast" else "analyze"

    async def analyst(state: AgentState) -> dict:
        """Classify the request and select one specialist."""
        structured_model = model.with_structured_output(RouteDecision)
        decision = await structured_model.ainvoke(
            [
                SystemMessage(
                    content=(
                        "你是任务分析师。只选择一个最合适的专家："
                        "Python 编程教学选 python_teacher；当前日期时间时区选 time_announcer；"
                        "需要项目私有文档或知识库检索选 librarian；"
                        "要求绘制流程图、架构图或 draw.io 文件选 diagram_artist；"
                        "用户要求修改身份、称呼或名字选 identity_manager；其他选 general。"
                    )
                ),
                HumanMessage(
                    content=f"对话历史：\n{conversation_context(state)}\n当前问题：{state['question']}"
                ),
            ]
        )
        return {"route": decision.specialist, "analysis": decision.reason}

    def route_specialist(state: AgentState) -> str:
        return state["route"]

    async def python_teacher(state: AgentState) -> dict:
        response = await model.ainvoke(
            [
                SystemMessage(
                    content=(
                        "你是 Python 讲师。使用简体中文，先解释概念，再给简短示例，"
                        "指出一个常见错误；不确定时明确说明。"
                    )
                ),
                HumanMessage(content=state["question"]),
            ]
        )
        return {"specialist_result": str(response.content)}

    async def time_announcer(state: AgentState) -> dict:
        tool = mcp_tools_by_name.get("get_current_time")
        if tool is None:
            return {"specialist_result": "时间 MCP 工具不可用。"}
        result = await tool.ainvoke({})
        return {"specialist_result": f"时间 MCP 工具返回：{result}"}

    async def identity_manager(state: AgentState) -> dict:
        """Extract and persist the identity requested by the user."""
        extractor = model.with_structured_output(IdentityUpdate)
        requested = await extractor.ainvoke(
            [
                SystemMessage(
                    content="提取用户明确要求以后使用的新身份或称呼，不要自行创造。"
                ),
                HumanMessage(content=state["question"]),
            ]
        )
        result = await update_user_identity.ainvoke({"identity": requested.identity})
        return {"specialist_result": str(result)}

    async def librarian(state: AgentState) -> dict:
        # L10-L12 will replace this boundary with LlamaIndex retrieval + citations.
        return {
            "specialist_result": (
                "图书管理员尚未接入知识库。请在完成 L10-L12 后，"
                "将 LlamaIndex 检索器接入此节点，并返回召回片段与来源引用。"
            )
        }

    async def diagram_artist(state: AgentState) -> dict:
        """Create a simple editable draw.io flowchart through MCP."""
        tool = mcp_tools_by_name.get("create_drawio_flowchart")
        if tool is None:
            return {"specialist_result": "绘图 MCP 工具不可用。"}

        extractor = model.with_structured_output(DiagramRequest)
        request = await extractor.ainvoke(
            [
                SystemMessage(
                    content=(
                        "你是绘图师。把用户需求整理成从上到下的简单流程图，"
                        "提取标题、顺序步骤和安全的英文文件名；最多 20 个步骤。"
                    )
                ),
                HumanMessage(content=state["question"]),
            ]
        )
        result = await tool.ainvoke(request.model_dump())
        return {"specialist_result": str(result)}

    async def general_specialist(state: AgentState) -> dict:
        response = await model.ainvoke(
            [
                SystemMessage(content="你是通用问题专家。准确、简洁地回答，不虚构事实。"),
                HumanMessage(content=state["question"]),
            ]
        )
        return {"specialist_result": str(response.content)}

    async def validator(state: AgentState) -> dict:
        response = await model.ainvoke(
            [
                SystemMessage(
                    content=(
                        "你是结果验证员。检查答案是否回应问题、是否自相矛盾、"
                        "是否把未知内容伪装成事实。只给简短验证结论和必要修改建议。"
                    )
                ),
                HumanMessage(
                    content=(
                        f"用户问题：{state['question']}\n"
                        f"专家结果：{state['specialist_result']}"
                    )
                ),
            ]
        )
        return {"validation": str(response.content)}

    async def mabel_delivery(state: AgentState) -> dict:
        response = await model.ainvoke(
            [
                SystemMessage(
                    content=(
                        persona_for_current_user()
                        + "请根据专家结果和验证意见交付最终答案。不要透露内部 Agent 流程，"
                        "不要声称已完成尚未接入的知识库检索。"
                    )
                ),
                HumanMessage(
                    content=(
                        f"用户问题：{state['question']}\n"
                        f"专家结果：{state['specialist_result']}\n"
                        f"验证意见：{state['validation']}"
                    )
                ),
            ]
        )
        answer = str(response.content)
        return {"final_answer": answer, "messages": [AIMessage(content=answer)]}

    builder = StateGraph(AgentState)
    builder.add_node("mabel", mabel_companion)
    builder.add_node("analyst", analyst)
    builder.add_node("python_teacher", python_teacher)
    builder.add_node("time_announcer", time_announcer)
    builder.add_node("librarian", librarian)
    builder.add_node("diagram_artist", diagram_artist)
    builder.add_node("identity_manager", identity_manager)
    builder.add_node("general", general_specialist)
    builder.add_node("validator", validator)
    builder.add_node("mabel_delivery", mabel_delivery)

    builder.add_edge(START, "mabel")
    builder.add_conditional_edges(
        "mabel",
        route_after_reception,
        {"fast": END, "analyze": "analyst"},
    )
    builder.add_conditional_edges(
        "analyst",
        route_specialist,
        {
            "python_teacher": "python_teacher",
            "time_announcer": "time_announcer",
            "librarian": "librarian",
            "diagram_artist": "diagram_artist",
            "identity_manager": "identity_manager",
            "general": "general",
        },
    )
    for specialist in (
        "python_teacher",
        "time_announcer",
        "librarian",
        "diagram_artist",
        "identity_manager",
        "general",
    ):
        builder.add_edge(specialist, "validator")
    builder.add_edge("validator", "mabel_delivery")
    builder.add_edge("mabel_delivery", END)

    return builder.compile(checkpointer=InMemorySaver())


async def run_once(
    graph,
    question: str,
    *,
    mode: Literal["normal", "fast"] = "normal",
    thread_id: str = "desktop-user",
) -> AgentState:
    """Run one request through the compiled graph."""
    config = {"configurable": {"thread_id": thread_id}}
    return await graph.ainvoke(
        {
            "question": question,
            "mode": mode,
            "messages": [HumanMessage(content=question)],
        },
        config=config,
    )


async def main() -> None:
    graph = await build_agent_graph()
    mode_text = input("模式（normal/fast，默认 normal）：").strip().lower() or "normal"
    if mode_text not in {"normal", "fast"}:
        raise SystemExit("模式只能是 normal 或 fast")
    print(f"当前身份：{read_user_identity()}。输入 exit 或 quit 结束对话。")
    while True:
        question = input("你：").strip()
        if question.lower() in {"exit", "quit"}:
            print("对话结束。")
            break
        if not question:
            print("输入不能为空。")
            continue

        result = await run_once(graph, question, mode=mode_text)
        print("梅贝尔：", result["final_answer"])


if __name__ == "__main__":
    asyncio.run(main())

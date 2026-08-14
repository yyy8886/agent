# Workflow 代码契约（第 1 版）

当前版本已经实现源码保存、静态检查、不可变运行产物、独立 Worker 执行、
SSE 事件、子工作流、会话持久化、取消和超时。本文描述用户源码必须遵守的稳定边界。

## 入口和运行上下文

每份源码必须提供无参数同步函数 `build_workflow()`。该函数只构建并返回已经
`compile()` 的 LangGraph。一次运行需要的能力通过 LangGraph 的
`context_schema=WorkflowRuntime` 注入，不能闭包进构图函数。

```python
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from my_agent_next.workflow_sdk import WorkflowRuntime


class Input(TypedDict):
    message: str


class State(Input, total=False):
    answer: str


class Output(TypedDict):
    answer: str


async def ask_agent(state: State, runtime: Runtime[WorkflowRuntime]) -> dict:
    result = await runtime.context.call_agent(
        "mabel",
        {"message": state["message"]},
        step_id="ask_agent",
        route="START -> ask_agent -> END",
    )
    return {"answer": str(result.get("answer", ""))}


def build_workflow():
    graph = StateGraph(
        State,
        context_schema=WorkflowRuntime,
        input_schema=Input,
        output_schema=Output,
    )
    graph.add_node("ask_agent", ask_agent)
    graph.add_edge(START, "ask_agent")
    graph.add_edge("ask_agent", END)
    return graph.compile()
```

`step_id` 和 `route` 是可选的工作流认知信息。简化 `Workflow` Builder 和可视化
工作流会自动填写；手写高级 LangGraph 时建议显式提供。Worker 会把工作流 ID、当前
步骤、完整路线、调用层级、权限模式和子工作流依赖作为独立 SystemMessage 交给 Agent。
所有 Agent 还会获得启用 Agent 的精简名称/ID/职责目录，但不会加载其他 Agent 的完整
persona，以免发生角色混淆。

输入、输出以及 Runtime 调用参数的顶层都必须是 JSON 对象。路径、字节、集合、
Python 对象、`NaN` 和 `Infinity` 均不属于公开协议。

`WorkflowRuntime` 是 LangGraph 支持的 dataclass context，因此可以生成 context JSON
Schema。它只包含运行元数据和已声明的依赖键；Agent、Tool 和子工作流的实际执行能力
由 Worker 在运行期间单独绑定，不进入 Schema，也不闭包进编译图。

子工作流只能通过发布时声明的依赖键调用，例如：

```python
result = await runtime.context.call_workflow(
    "summarizer",
    {"text": state["answer"]},
)
```

发布清单负责把 `summarizer` 固定到具体 `workflow_id + workflow_version`。执行引擎按该
不可变映射创建父子 `run_id`、检查循环依赖并传播取消。源码不能导入另一份工作流、
传入任意工作流 ID，或者在运行时选择子版本。

## 安全边界

`validate_workflow_source()` 只做 AST 静态检查，并且保证不导入、不执行提交的源码。
它用于尽早报告语法、入口、导入和明显危险调用问题，**不是安全沙箱**。校验通过只
表示符合代码契约，不能作为允许代码在宿主进程执行的安全授权。

当前执行器遵守：

- 仅管理员可以提交高级代码工作流。
- 源码永远不能在 FastAPI Web 进程中 `exec()`、`eval()` 或 import。
- Windows 和 Linux 都通过独立 Worker 进程运行，并配置超时、取消和环境变量白名单。
- 正式对外部署前，Worker 还需要低权限系统用户或容器级文件、网络和资源隔离。
- API Key、Repository、Service 和宿主文件系统不直接暴露给源码。
- Agent、Tool 和子工作流调用必须经过 `WorkflowRuntime`，继续服从权限规则。

## 执行和输出

发布时，应用按照源码内容生成 SHA-256 标识的不可变 Python 产物。运行管理器启动独立
Worker，Worker 导入该产物、调用 `build_workflow()`，再通过 LangGraph 原生
`astream()` 执行。源码不会被转换成应用自定义的节点描述。

界面输入统一为包含 `message` 的 JSON 对象。工作流可以在 State 中维护任意符合公开
JSON 协议的中间字段，但最终输出必须包含字符串字段 `answer`，用于页面显示和
`chat_messages` 持久化。

Worker 会发送工作流、节点、Agent、Tool、Skill、子工作流和最终输出事件。父子运行使用
独立 `run_id` 并保留父运行关系。用户取消时先设置协作取消信号；未及时退出的 Worker
会在宽限时间后被强制终止。总运行时间和 LangGraph 递归次数也有独立上限。

LangGraph 的条件边、回边以及节点内 Python `if`、`for`、`while` 都由原生运行时处理。
业务代码仍应提供明确退出条件，递归限制和强制终止只能作为保护措施。

当前允许导入的模块是保守白名单。应用自身只允许从单文件公开入口
`my_agent_next.workflow_sdk` 导入明确列出的符号；`app.workflows` 下的校验器、未来的
Repository 和 Worker 都不属于用户 SDK。增加模块时需要同时说明用途和权限影响，
不能通过放宽到整个 `my_agent_next` 包来绕过业务边界。

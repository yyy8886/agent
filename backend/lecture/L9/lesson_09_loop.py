# L9 — LangGraph 循环与 Checkpointer
# 相比 L8 的核心区别：
#
# ┌──────────┬──────────────────────────────────────┬──────────────────────────┐
# │  课程    │  图的新能力                           │  状态是否持久化？         │
# ├──────────┼──────────────────────────────────────┼──────────────────────────┤
# │  L8      │  节点 + 固定边 + 条件边（无循环）       │  否，invoke 结束就没了    │
# │  L9 ←本课│  自循环 + Checkpointer + 多线程       │  是，可跨 invoke 保留     │
# └──────────┴──────────────────────────────────────┴──────────────────────────┘
#
# L9 在 L8 基础上新增三个关键能力：
#
# ── 新增 1：自循环（Self-loop）───────────────────────────────────────────────
#
#   L8 的图是有向无环图（DAG），数据只能向前走，不能回到之前的节点：
#     START → read_question → answer_xxx → END
#
#   L9 的图有 循环：节点可以回到自己，反复执行直到满足条件：
#     START → increase_count ──→ increase_count ──→ increase_count ──→ END
#              ↑               ↑               ↑
#              count=1          count=2          count=3（满足条件，stop）
#
#   实现方式：add_conditional_edges 中，映射表的一个值指向节点自身。
#   这就是 while 循环的图形式：L8 的图 = 函数调用，L9 的图 = while 循环。
#
# ── 新增 2：Checkpointer（状态检查点/持久化）────────────────────────────────
#
#   L8 的 graph.invoke() 结束后 state 就丢了，下次调用从头开始。
#   L9 引入 InMemorySaver（内存中的状态保存器），每次节点执行后自动存档。
#
#   效果：
#   - graph.invoke() 结束后，状态依然保留在 checkpointer 中
#   - 同 thread_id 的下一次 invoke 会从上次的断点继续（而非从头开始）
#   - 可以查询历史快照（graph.get_state_history()）
#
#   对比 L4 的 history 列表：
#     L4 手动维护：history.append(HumanMessage) → 只有用户可见的消息
#     L9 自动维护：每次节点执行后 LangGraph 自动存快照 → 包含所有内部状态
#
# ── 新增 3：多线程隔离（thread_id）──────────────────────────────────────────
#
#   L8 的图只能同时处理一个对话，因为只有一份 state。
#   L9 通过 config["configurable"]["thread_id"] 区分不同"会话线程"。
#
#   不同 thread_id = 各自独立的状态空间：
#     thread_id="lesson-thread"   → 自己的 count、自己的历史
#     thread_id="another-thread"  → 另一个独立的 count、独立的历史
#
#   类比：同一个游戏引擎，两个玩家的存档互相独立。
# =============================================================================
# 1. 导入依赖
# =============================================================================
from typing import TypedDict

# L8 学过的：StateGraph + START + END
from langgraph.graph import END, START, StateGraph

# L9 新增：InMemorySaver — 内存中的状态保存器
# 在每次节点（更准确地说是每个 super-step）执行后将 state 写入内存，
# 支持后续查询、恢复、回放。适合开发和学习，生产环境可换持久化方案。
from langgraph.checkpoint.memory import InMemorySaver


# =============================================================================
# 2. 定义状态 — 只有一个计数字段
# =============================================================================
# L8 的 LessonState 有两个字段（question + answer），各走一次就结束。
# L9 的 LoopState 只有一个字段 count，但会 反复更新，这就是循环的意义。
#
# total=False 仍然表示字段可选，但这里 count 每次都会传入。
class LoopState(TypedDict):
    count: int      # 当前计数值，每次循环 +1


# =============================================================================
# 3. 定义节点函数 — 唯一节点，但会被反复执行
# =============================================================================
def increase_count(state: LoopState) -> dict:
    """把计数增加 1。"""
    new_count = state["count"] + 1
    print(f"正在执行 increase_count：{new_count}")
    return {"count": new_count}    # 返回更新后的 count，LangGraph 自动合并入 state


# =============================================================================
# 4. 定义条件路由函数 — 决定继续循环还是结束
# =============================================================================
# L8 的 route_question 返回两个不同的下游节点名（"python" / "general"）。
# L9 的 route_after_count 返回 "continue"（回到自己，形成循环）
#                         或 "stop"（走向 END，退出循环）。
#
# 这就是图版本的 while 循环条件：
#   while count < 3:      ← Python 写法
#       increase_count()
#
#   等于图中：
#   increase_count → route_after_count → "continue" 则回到 increase_count
#                                      → "stop"     则走向 END
def route_after_count(state: LoopState) -> str:
    """计数未达到 3 时继续，否则结束。"""
    if state["count"] < 3:
        return "continue"    # 回到 increase_count，再来一轮
    return "stop"            # 去 END，退出循环


# =============================================================================
# 5. 构建图 — 自循环的边结构
# =============================================================================
builder = StateGraph(LoopState)

builder.add_node("increase_count", increase_count)

# START → increase_count：入口不变
builder.add_edge(START, "increase_count")

# 条件边：从 increase_count 出发，根据 route_after_count 的返回值决定
#   "continue" → increase_count（回到自己！这是与 L8 最大的区别）
#   "stop"     → END
#
# L8 的条件边：两个不同的下游节点（answer_python / answer_general）
# L9 的条件边：一个下游是 END，另一个是节点自身 → 形成循环
builder.add_conditional_edges(
    "increase_count",
    route_after_count,
    {
        "continue": "increase_count",  # ← 自循环！L8 中没有这种写法
        "stop": END,
    },
)

# =============================================================================
# 6. 编译图（带 Checkpointer）— L9 的关键一步
# =============================================================================
# compile(checkpointer=checkpointer) vs compile()：
#
#   L8：graph = builder.compile()
#        无参数，状态在 invoke 结束后消失
#
#   L9：graph = builder.compile(checkpointer=checkpointer)
#        传入 checkpointer，LangGraph 在每个节点执行后自动保存状态快照
#
# InMemorySaver 把快照存在内存里，进程重启会丢失。
# 生产环境可换成 SqliteSaver 或 PostgresSaver 实现持久化。
checkpointer = InMemorySaver()
graph = builder.compile(checkpointer=checkpointer)


# =============================================================================
# 7. 配置线程 ID — 多会话隔离的钥匙
# =============================================================================
# config 中的 thread_id 类似于"会话 ID"或"存档槽位"。
# 同一个 thread_id 的多次 invoke 共享一份状态历史。
# 不同的 thread_id 之间完全隔离，互不影响。
#
# 类比：
#   老式游戏机（无存档）：每次开机从第一关开始 → L8
#   带存档卡带的游戏：      每个卡带独立存档 → L9 + checkpointer + thread_id
config = {
    "configurable": {
        "thread_id": "lesson-thread",     # 线程标识，可以是任意字符串
    }
}

# =============================================================================
# 8. 第一次调用 — 见证循环
# =============================================================================
# 传入初始 state {count: 0} 和 config。
#
# 执行流程（LangGraph 自动完成）：
#   1. START → increase_count，count 0→1，打印 "正在执行 increase_count：1"
#   2. 自动保存快照到 checkpointer（thread_id="lesson-thread"）
#   3. route_after_count：count=1 < 3 → 返回 "continue"
#   4. increase_count 再次执行，count 1→2，打印 "正在执行 increase_count：2"
#   5. 自动保存快照
#   6. route_after_count：count=2 < 3 → 返回 "continue"
#   7. increase_count 再次执行，count 2→3，打印 "正在执行 increase_count：3"
#   8. 自动保存快照
#   9. route_after_count：count=3 不小于 3 → 返回 "stop"
#  10. END，返回最终 state {"count": 3}
#
# 节点 increase_count 被执行了 3 次，无需手动写 while 循环！
result = graph.invoke(
    {"count": 0},
    config=config,
)
print("最终 State：", result)   # {"count": 3}


# =============================================================================
# 9. 查询保存的状态 — L9 独有能力
# =============================================================================
# graph.get_state(config)：读取指定线程的 最新 状态快照。
#
# L8 中没有这个能力——invoke 返回后就结束了，无法回头查看。
# L9 因为有 checkpointer，可以随时查询任何 thread_id 的最新状态。
snapshot = graph.get_state(config)

# snapshot.values：当前 state 的字段值 {"count": 3}
print("保存的 State：", snapshot.values)

# snapshot.next：下一步会执行哪些节点
# 如果图还在运行中，返回待执行的节点名列表
# 如果图已结束，返回空元组 ()
print("下一节点：", snapshot.next)   # ()  因为已经 END 了


# =============================================================================
# 10. 多线程隔离 — 不同 thread_id 互不干扰
# =============================================================================
# 创建第二个线程，使用不同的 thread_id。
# 这是 L9 的另一个核心能力：同一个 graph 可以同时服务多个独立会话。
#
# 实际应用场景：
#   thread_id="user-001"  → 用户 001 的对话
#   thread_id="user-002"  → 用户 002 的对话
#   每个用户有自己的计数、自己的状态、不互相串
second_config = {
    "configurable": {
        "thread_id": "another-thread",      # 不同的 thread_id，独立的状态空间
    }
}

# 第二条线程从 count=1 开始（而非 0），循环 2 次到 3
second_result = graph.invoke(
    {"count": 1},
    config=second_config,
)
print("第二条线程结果：", second_result)   # {"count": 3}

# 分别查询两条线程的状态 —— 各自独立存储
print("第一条线程 State：", graph.get_state(config).values)         # {"count": 3}
print("第二条线程 State：", graph.get_state(second_config).values)  # {"count": 3}


# =============================================================================
# 11. 查询状态历史 — 回放完整执行过程
# =============================================================================
# graph.get_state_history(config)：返回该线程的 所有 历史快照列表。
#
# 每条线程的快照数量取决于该线程执行了多少个节点：
#   thread "lesson-thread"：  count 0→1→2→3，共执行 3 次 increase_count
#                             每个节点执行后保存一次 → 3 个快照
#   thread "another-thread"：count 1→2→3，共执行 2 次 increase_count
#                             每个节点执行后保存一次 → 2 个快照
#
# 这个能力在 L1~L8 中完全不存在。
# 可以用于：调试（"第几步出错了？"）、审计（"谁在什么时候改了什么？"）、
#          时间旅行（回退到某个历史快照重新执行）
first_history = list(graph.get_state_history(config))
second_history = list(graph.get_state_history(second_config))

print("第一条线程快照数量：", len(first_history))    # 3
print("第二条线程快照数量：", len(second_history))   # 2


# ── L9 小结 ──────────────────────────────────────────────────────────────────
#
# L8 → L9 的演进：
#   L8 学会了"画图"（节点 + 边 + 条件分支）
#   L9 学会了"循环"（自循环边）+ "记忆"（Checkpointer）+ "多用户"（thread_id）
#
# 三个新概念的本质：
#   1. 自循环边：add_conditional_edges 映射回自身 → 图版本的 while 循环
#   2. Checkpointer：每个节点执行后自动存档 → 状态持久化 + 可查询历史
#   3. thread_id：不同会话的状态隔离 → 一个图服务多个用户
#
# 如果你想象 L8 是一个"流程图"，
# 那么 L9 就是一个"带存档功能、可以反复刷同一关的游戏引擎"。
#
# L10+ 将在此基础上加入真正的 LLM 节点，实现完整的 Agent 工作流。

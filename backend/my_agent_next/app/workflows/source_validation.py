"""Static validation for workflow source without importing or executing it."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from .contract import PUBLIC_WORKFLOW_SDK_SYMBOLS, WORKFLOW_ENTRYPOINT


@dataclass(frozen=True, slots=True)
class WorkflowSourcePolicy:
    """Conservative source policy used before code reaches an isolated worker."""

    max_source_bytes: int
    allowed_exact_imports: frozenset[str]
    allowed_import_prefixes: tuple[str, ...]
    blocked_calls: frozenset[str]


DEFAULT_SOURCE_POLICY = WorkflowSourcePolicy(
    max_source_bytes=256 * 1024,
    allowed_exact_imports=frozenset(
        {
            "__future__",
            "my_agent_next.workflow_sdk",
        }
    ),
    allowed_import_prefixes=(
        "collections",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "functools",
        "json",
        "langchain_core.messages",
        "langgraph",
        "math",
        "operator",
        "pydantic",
        "re",
        "statistics",
        "typing",
        "typing_extensions",
        "uuid",
    ),
    blocked_calls=frozenset(
        {
            "__import__",
            "breakpoint",
            "compile",
            "eval",
            "exec",
            "input",
            "open",
        }
    ),
)


@dataclass(frozen=True, slots=True)
class WorkflowSourceIssue:
    code: str
    message: str
    line: int | None = None
    column: int | None = None


@dataclass(frozen=True, slots=True)
class WorkflowSourceValidation:
    issues: tuple[WorkflowSourceIssue, ...]
    imports: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.issues


def validate_workflow_source(
    source: str,
    policy: WorkflowSourcePolicy = DEFAULT_SOURCE_POLICY,
) -> WorkflowSourceValidation:
    """Inspect source structure only; this function never imports or executes it."""

    issues: list[WorkflowSourceIssue] = []
    imports: list[str] = []
    if not isinstance(source, str) or not source.strip():
        return WorkflowSourceValidation(
            issues=(WorkflowSourceIssue("empty_source", "工作流代码不能为空。"),)
        )
    try:
        source_size = len(source.encode("utf-8"))
    except UnicodeEncodeError:
        return WorkflowSourceValidation(
            issues=(
                WorkflowSourceIssue(
                    "invalid_encoding",
                    "工作流代码包含无效的 Unicode 字符。",
                ),
            )
        )
    if source_size > policy.max_source_bytes:
        return WorkflowSourceValidation(
            issues=(
                WorkflowSourceIssue(
                    "source_too_large",
                    f"工作流代码不能超过 {policy.max_source_bytes} 字节。",
                ),
            )
        )

    try:
        tree = ast.parse(source, filename="<workflow>")
    except SyntaxError as exc:
        return WorkflowSourceValidation(
            issues=(
                WorkflowSourceIssue(
                    "syntax_error",
                    exc.msg,
                    exc.lineno,
                    exc.offset,
                ),
            )
        )

    entrypoints = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == WORKFLOW_ENTRYPOINT
    ]
    if not entrypoints:
        issues.append(
            WorkflowSourceIssue(
                "missing_entrypoint",
                f"必须定义顶层函数 {WORKFLOW_ENTRYPOINT}()。",
            )
        )
    elif len(entrypoints) > 1:
        issues.append(
            WorkflowSourceIssue(
                "duplicate_entrypoint",
                f"只能定义一个 {WORKFLOW_ENTRYPOINT}()。",
                entrypoints[1].lineno,
                entrypoints[1].col_offset + 1,
            )
        )
    else:
        entrypoint = entrypoints[0]
        if isinstance(entrypoint, ast.AsyncFunctionDef):
            issues.append(
                WorkflowSourceIssue(
                    "async_entrypoint",
                    f"{WORKFLOW_ENTRYPOINT}() 只负责构图，必须使用同步函数。",
                    entrypoint.lineno,
                    entrypoint.col_offset + 1,
                )
            )
        arguments = entrypoint.args
        if (
            arguments.posonlyargs
            or arguments.args
            or arguments.kwonlyargs
            or arguments.vararg
            or arguments.kwarg
        ):
            issues.append(
                WorkflowSourceIssue(
                    "invalid_entrypoint_signature",
                    f"{WORKFLOW_ENTRYPOINT}() 不能接收参数；运行能力由 LangGraph context 注入。",
                    entrypoint.lineno,
                    entrypoint.col_offset + 1,
                )
            )

    for node in tree.body:
        if _is_allowed_module_declaration(node):
            continue
        issues.append(
            WorkflowSourceIssue(
                "module_side_effect",
                "模块顶层只能包含导入、声明和无调用的常量赋值。",
                getattr(node, "lineno", None),
                (getattr(node, "col_offset", 0) + 1),
            )
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
                _check_import(alias.name, node, policy, issues)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                issues.append(
                    WorkflowSourceIssue(
                        "relative_import",
                        "工作流代码不能使用相对导入。",
                        node.lineno,
                        node.col_offset + 1,
                    )
                )
                continue
            module = node.module or ""
            imports.append(module)
            _check_import(module, node, policy, issues)
            _check_imported_members(module, node, issues)
            if any(alias.name == "*" for alias in node.names):
                issues.append(
                    WorkflowSourceIssue(
                        "wildcard_import",
                        "工作流代码不能使用星号导入。",
                        node.lineno,
                        node.col_offset + 1,
                    )
                )
        elif isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            if call_name in policy.blocked_calls:
                issues.append(
                    WorkflowSourceIssue(
                        "blocked_call",
                        f"工作流代码不能调用 {call_name}()。",
                        node.lineno,
                        node.col_offset + 1,
                    )
                )
            builtin_name = _builtins_subscript_name(node.func)
            if builtin_name in policy.blocked_calls:
                issues.append(
                    WorkflowSourceIssue(
                        "blocked_call",
                        f"工作流代码不能通过 __builtins__ 调用 {builtin_name}()。",
                        node.lineno,
                        node.col_offset + 1,
                    )
                )
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            assigned_value = node.value
            if (
                isinstance(assigned_value, ast.Name)
                and assigned_value.id in policy.blocked_calls
            ):
                issues.append(
                    WorkflowSourceIssue(
                        "blocked_call_alias",
                        f"工作流代码不能为 {assigned_value.id}() 创建别名。",
                        node.lineno,
                        node.col_offset + 1,
                    )
                )

    return WorkflowSourceValidation(
        issues=tuple(issues),
        imports=tuple(dict.fromkeys(imports)),
    )


def _check_import(
    module: str,
    node: ast.AST,
    policy: WorkflowSourcePolicy,
    issues: list[WorkflowSourceIssue],
) -> None:
    allowed = any(
        module == prefix or module.startswith(prefix + ".")
        for prefix in policy.allowed_import_prefixes
    )
    allowed = allowed or module in policy.allowed_exact_imports
    if not allowed:
        issues.append(
            WorkflowSourceIssue(
                "blocked_import",
                f"工作流代码不能导入 {module or '<unknown>'}。",
                getattr(node, "lineno", None),
                (getattr(node, "col_offset", 0) + 1),
            )
        )


def _check_imported_members(
    module: str,
    node: ast.ImportFrom,
    issues: list[WorkflowSourceIssue],
) -> None:
    if module == "__future__":
        allowed_members = {"annotations"}
    elif module == "my_agent_next.workflow_sdk":
        allowed_members = PUBLIC_WORKFLOW_SDK_SYMBOLS
    else:
        return
    for alias in node.names:
        if alias.name not in allowed_members:
            issues.append(
                WorkflowSourceIssue(
                    "blocked_import_member",
                    f"不能从 {module} 导入未公开符号 {alias.name}。",
                    node.lineno,
                    node.col_offset + 1,
                )
            )


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    return None


def _builtins_subscript_name(node: ast.expr) -> str | None:
    if not isinstance(node, ast.Subscript):
        return None
    if not isinstance(node.value, ast.Name) or node.value.id != "__builtins__":
        return None
    if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
        return node.slice.value
    return None


def _is_allowed_module_declaration(node: ast.stmt) -> bool:
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return True
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        expressions = [
            *node.decorator_list,
            *node.args.defaults,
            *(default for default in node.args.kw_defaults if default is not None),
        ]
        return not any(
            isinstance(child, ast.Call)
            for expression in expressions
            for child in ast.walk(expression)
        )
    if isinstance(node, ast.ClassDef):
        expressions = [*node.decorator_list, *node.bases]
        expressions.extend(keyword.value for keyword in node.keywords)
        if any(
            isinstance(child, ast.Call)
            for expression in expressions
            for child in ast.walk(expression)
        ):
            return False
        return all(_is_allowed_class_declaration(child) for child in node.body)
    if isinstance(node, ast.Expr):
        return isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
    if isinstance(node, ast.Assign):
        return not any(isinstance(child, ast.Call) for child in ast.walk(node.value))
    if isinstance(node, ast.AnnAssign):
        return node.value is None or not any(
            isinstance(child, ast.Call) for child in ast.walk(node.value)
        )
    return False


def _is_allowed_class_declaration(node: ast.stmt) -> bool:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return _is_allowed_module_declaration(node)
    if isinstance(node, ast.Expr):
        return isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
    if isinstance(node, ast.Pass):
        return True
    if isinstance(node, ast.Assign):
        return not any(isinstance(child, ast.Call) for child in ast.walk(node.value))
    if isinstance(node, ast.AnnAssign):
        return node.value is None or not any(
            isinstance(child, ast.Call) for child in ast.walk(node.value)
        )
    return False

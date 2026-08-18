from PyInstaller.utils.hooks import collect_submodules, copy_metadata


hiddenimports = []
for package in (
    "my_agent_next",
    "langchain_deepseek",
    "langchain_mcp_adapters",
    "langchain_ollama",
    "langchain_openai",
    "uvicorn",
):
    hiddenimports += [
        name for name in collect_submodules(package)
        if not name.startswith("my_agent_next.tests")
    ]

datas = [
    ("my_agent_next/config.yaml", "my_agent_next"),
    ("my_agent_next/app/static", "my_agent_next/app/static"),
    ("my_agent_next/skills", "my_agent_next/skills"),
]
for distribution in ("fastapi", "langchain", "langchain-core", "langgraph", "mcp"):
    try:
        datas += copy_metadata(distribution)
    except Exception:
        pass

a = Analysis(
    ["my_agent_next/desktop_backend.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="my-agent-next-backend", debug=False,
    bootloader_ignore_signals=False, strip=False, upx=True,
    console=False, disable_windowed_traceback=False,
)
coll = COLLECT(
    exe, a.binaries, a.datas, strip=False, upx=True,
    upx_exclude=[], name="my-agent-next-backend",
)

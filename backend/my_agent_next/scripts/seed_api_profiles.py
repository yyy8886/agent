# seed_api_profiles.py — 数据库种子脚本
# =============================================================================
# 初次使用时运行此脚本，向 app.db 写入预设的 API 配置。
# 预置了 4 个配置：OpenAI 代理、DeepSeek Chat、OpenAI GPT、本地 Ollama。
#
# 运行方式：
#   python -m my_agent_next.scripts.seed_api_profiles
#
# 注意：此脚本可重复运行，重复的 ID 会以 UPSERT 方式更新而非报错。"""

from my_agent_next.app.api_profile_service import ApiProfileService


PROFILES = [
    {"id":"openai_proxy","name":"OpenAI 兼容代理","provider":"openai","model":"gpt-5.5","base_url":"https://sapi.nyro.lol/v1","api_key_env":"OPENAI_API_KEY","temperature":0.2,"timeout_seconds":60,"max_retries":2},
    {"id":"deepseek_chat","name":"DeepSeek Chat","provider":"deepseek","model":"deepseek-chat","base_url":"https://api.deepseek.com","api_key_env":"DEEPSEEK_API_KEY","temperature":0.2,"timeout_seconds":60,"max_retries":2,"is_default":True},
    {"id":"openai_gpt","name":"OpenAI GPT","provider":"openai","model":"gpt-5.6-sol","base_url":"https://api.openai.com/v1","api_key_env":"OPENAI_API_KEY","temperature":0.2,"timeout_seconds":60,"max_retries":2},
    {"id":"ollama_local","name":"本地 Ollama","provider":"ollama","model":"qwen3:8b","base_url":"http://127.0.0.1:11434","temperature":0.2,"timeout_seconds":60,"max_retries":2},
]


def main():
    service = ApiProfileService()
    for profile in PROFILES:
        service.save(profile)
    print(f"已写入 {len(service.list())} 个 API 配置。")


if __name__ == "__main__":
    main()


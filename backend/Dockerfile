FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY my_agent_next ./my_agent_next

RUN python -m pip install --upgrade pip \
    && python -m pip install . \
    && mkdir -p /app/my_agent_next/data/attachments \
                    /app/my_agent_next/data/agent-runs \
                    /app/my_agent_next/skills

EXPOSE 19845

CMD ["python", "-m", "uvicorn", "my_agent_next.app.web_server:app", "--host", "0.0.0.0", "--port", "19845"]

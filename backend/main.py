import enum
import os
import uuid
import asyncio
from datetime import datetime
from typing import Any, Dict, Literal, Optional

import orjson
import redis.asyncio as redis
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import AnyUrl, BaseModel, Field
from sqlalchemy import DateTime, Enum, String, delete, func, select
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# -------------------------
# Конфигурация (через env)
# -------------------------
POSTGRES_DSN = os.getenv(
    "POSTGRES_DSN",
    "postgresql+asyncpg://postgres:postgres@db:5432/taskservice",
)
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
API_PREFIX = os.getenv("API_PREFIX", "/api")
TASK_CACHE_TTL_SECONDS = int(os.getenv("TASK_CACHE_TTL_SECONDS", "60"))

# -------------------------
# База данных (PostgreSQL)
# -------------------------
engine = create_async_engine(POSTGRES_DSN, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with SessionLocal() as s:
        yield s


# -------------------------
# Redis (кеш)
# -------------------------
redis_client: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    assert redis_client is not None, "Redis не инициализирован"
    return redis_client


def cache_key(task_id: uuid.UUID) -> str:
    return f"task:{task_id}"


# -------------------------
# Модель данных
# -------------------------
class SiteType(str, enum.Enum):
    marketplace = "marketplace"
    news = "news"
    ecommerce = "ecommerce"
    classifieds = "classifieds"
    other = "other"


class TaskStatus(str, enum.Enum):
    created = "created"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)

    site_type: Mapped[SiteType] = mapped_column(
        Enum(SiteType, name="site_type"),
        nullable=False,
        default=SiteType.other,
    )
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status"),
        nullable=False,
        default=TaskStatus.created,
    )

    criteria: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# -------------------------
# Схемы (Pydantic) для API
# -------------------------
SiteTypeLiteral = Literal["marketplace", "news", "ecommerce", "classifieds", "other"]
TaskStatusLiteral = Literal["created", "running", "paused", "completed", "failed"]


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200, description="Название задачи")
    url: AnyUrl = Field(description="URL стартовой страницы для парсинга")
    site_type: SiteTypeLiteral = Field("other", description="Тип сайта/источника")
    criteria: Dict[str, Any] = Field(default_factory=dict, description="Критерии/правила сбора (JSON)")


class TaskUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200, description="Название задачи")
    url: Optional[AnyUrl] = Field(default=None, description="URL стартовой страницы")
    site_type: Optional[SiteTypeLiteral] = Field(default=None, description="Тип сайта/источника")
    status: Optional[TaskStatusLiteral] = Field(default=None, description="Статус выполнения задачи")
    criteria: Optional[Dict[str, Any]] = Field(default=None, description="Критерии/правила сбора (JSON)")


class TaskOut(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    site_type: SiteTypeLiteral
    status: TaskStatusLiteral
    criteria: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class TaskListOut(BaseModel):
    items: list[TaskOut]
    total: int
    limit: int
    offset: int


# -------------------------
# Приложение FastAPI
# -------------------------
app = FastAPI(
    title="TaskService — сервис задач парсинга",
    description=(
        "Микросервис для CRUD-операций по задачам парсинга.\n\n"
        "Хранит параметры задачи (название, URL, тип сайта, критерии сбора) и статус выполнения.\n"
        "PostgreSQL используется для хранения, Redis — для кеширования чтения задачи по id."
    ),
    version="0.1.0",
)

# -------------------------
# CORS (для фронтенда)
# -------------------------
# По умолчанию разрешаем Vite dev-сервер. Можно переопределить через env FRONTEND_ORIGINS
# (CSV), например: FRONTEND_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"
_frontend_origins = [o.strip() for o in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(',') if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    global redis_client

    # ---
    # Docker Compose часто поднимает приложение раньше, чем готовы Postgres/Redis.
    # Чтобы не падать на старте с ConnectionRefusedError, ждём зависимости.
    # ---

    # Ждём Postgres
    last_err: Exception | None = None
    for _ in range(30):  # ~30 секунд
        try:
            async with engine.connect() as conn:
                await conn.execute(select(1))
            last_err = None
            break
        except Exception as e:
            last_err = e
            await asyncio.sleep(1)
    if last_err is not None:
        raise last_err

    # Ждём Redis
    last_err = None
    for _ in range(30):
        try:
            redis_client = redis.from_url(REDIS_URL, decode_responses=False)
            await redis_client.ping()
            last_err = None
            break
        except Exception as e:
            last_err = e
            await asyncio.sleep(1)
    if last_err is not None:
        raise last_err

    # Для dev/PoC — создаём таблицы автоматически (без Alembic).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# -------------------------
# Русская “главная страница”
# -------------------------
@app.get("/", response_class=HTMLResponse, summary="Главная страница", description="Короткая справка по сервису.")
async def index():
    return f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <title>TaskService</title>
      </head>
      <body style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Arial;
                   max-width:900px;margin:40px auto;line-height:1.5;">
        <h1>TaskService — сервис задач парсинга</h1>
        <p>
          Этот микросервис хранит задачи парсинга и их параметры (URL, тип сайта, критерии сбора, статус).
          Сервис не парсит сайты сам — он управляет заданиями для парсеров/воркеров.
        </p>
        <ul>
          <li><a href="/docs">Swagger UI</a> (кнопки интерфейса могут быть на английском, описания — на русском)</li>
          <li><a href="/redoc">ReDoc</a></li>
          <li><a href="/health">Проверка здоровья</a></li>
        </ul>

        <h2>Основные эндпоинты</h2>
        <ul>
          <li><code>POST {API_PREFIX}/tasks</code> — создать задачу</li>
          <li><code>GET {API_PREFIX}/tasks</code> — список задач</li>
          <li><code>GET {API_PREFIX}/tasks/{{id}}</code> — получить задачу</li>
          <li><code>PATCH {API_PREFIX}/tasks/{{id}}</code> — обновить задачу</li>
          <li><code>DELETE {API_PREFIX}/tasks/{{id}}</code> — удалить задачу</li>
        </ul>
      </body>
    </html>
    """


# -------------------------
# Health
# -------------------------
@app.get("/health", summary="Проверка здоровья", description="Возвращает OK, если сервис запущен.")
async def health():
    return {"status": "ok"}


# -------------------------
# CRUD: Tasks
# -------------------------
@app.post(
    f"{API_PREFIX}/tasks",
    response_model=TaskOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать задачу",
    description="Создаёт новую задачу парсинга и сохраняет её в PostgreSQL.",
)
async def create_task(payload: TaskCreate, db: AsyncSession = Depends(get_db)):
    t = Task(
        name=payload.name,
        url=str(payload.url),
        site_type=payload.site_type,
        criteria=payload.criteria,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return TaskOut.model_validate(t, from_attributes=True)


@app.get(
    f"{API_PREFIX}/tasks/{{task_id}}",
    response_model=TaskOut,
    summary="Получить задачу",
    description="Возвращает задачу по id. Использует Redis для кеширования.",
)
async def get_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    key = cache_key(task_id)
    cached = await r.get(key)
    if cached:
        return TaskOut.model_validate(orjson.loads(cached))

    res = await db.execute(select(Task).where(Task.id == task_id))
    t = res.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    out = TaskOut.model_validate(t, from_attributes=True)
    await r.setex(key, TASK_CACHE_TTL_SECONDS, orjson.dumps(out.model_dump()))
    return out


@app.get(
    f"{API_PREFIX}/tasks",
    response_model=TaskListOut,
    summary="Список задач",
    description="Возвращает список задач с пагинацией, фильтрами и поиском по названию.",
)
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=200, description="Сколько элементов вернуть"),
    offset: int = Query(0, ge=0, description="Смещение (для пагинации)"),
    status_: str | None = Query(default=None, alias="status", description="Фильтр по статусу"),
    site_type: str | None = Query(default=None, description="Фильтр по типу сайта"),
    q: str | None = Query(default=None, description="Поиск по названию (подстрока)"),
):
    stmt = select(Task)
    if status_:
        stmt = stmt.where(Task.status == status_)
    if site_type:
        stmt = stmt.where(Task.site_type == site_type)
    if q:
        stmt = stmt.where(Task.name.ilike(f"%{q}%"))

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = stmt.order_by(Task.created_at.desc()).limit(limit).offset(offset)

    items = (await db.execute(stmt)).scalars().all()
    return TaskListOut(
        items=[TaskOut.model_validate(x, from_attributes=True) for x in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.patch(
    f"{API_PREFIX}/tasks/{{task_id}}",
    response_model=TaskOut,
    summary="Обновить задачу",
    description="Частично обновляет задачу. После обновления сбрасывает кеш Redis для этой задачи.",
)
async def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    res = await db.execute(select(Task).where(Task.id == task_id))
    t = res.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    data = payload.model_dump(exclude_unset=True)
    if "url" in data and data["url"] is not None:
        data["url"] = str(data["url"])

    for k, v in data.items():
        setattr(t, k, v)

    await db.commit()
    await db.refresh(t)

    await r.delete(cache_key(task_id))  # сброс кеша
    return TaskOut.model_validate(t, from_attributes=True)


@app.delete(
    f"{API_PREFIX}/tasks/{{task_id}}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить задачу",
    description="Удаляет задачу по id и очищает её кеш в Redis.",
)
async def delete_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    exists = (await db.execute(select(Task.id).where(Task.id == task_id))).scalar_one_or_none()
    if not exists:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    await db.execute(delete(Task).where(Task.id == task_id))
    await db.commit()
    await r.delete(cache_key(task_id))
    return None

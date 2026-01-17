import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type { SiteType, Task, TaskStatus } from "./types";

const siteTypeRu: Record<SiteType, string> = {
  marketplace: "Маркетплейс",
  news: "Новости",
  ecommerce: "Интернет-магазин",
  classifieds: "Объявления",
  other: "Другое",
};

const statusRu: Record<TaskStatus, string> = {
  created: "Создана",
  running: "В работе",
  paused: "Пауза",
  completed: "Завершена",
  failed: "Ошибка",
};

export default function App() {
  const [items, setItems] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [q, setQ] = useState("");
  const [siteType, setSiteType] = useState<SiteType | "">("");
  const [status, setStatus] = useState<TaskStatus | "">("");

  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [createSiteType, setCreateSiteType] = useState<SiteType>("other");
  const [criteriaText, setCriteriaText] = useState<string>('{"depth": 1}');

  const filters = useMemo(
    () => ({
      limit: 50,
      offset: 0,
      q: q.trim() || undefined,
      site_type: siteType || undefined,
      status: status || undefined,
    }),
    [q, siteType, status]
  );

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const data = await api.listTasks(filters);
      setItems(data.items);
    } catch (e: any) {
      setErr(e?.message ?? "Ошибка загрузки");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.q, filters.site_type, filters.status]);

  async function onCreate() {
    setErr(null);
    if (!name.trim()) return setErr("Введите название задачи");
    if (!url.trim()) return setErr("Введите URL");

    let criteria: Record<string, unknown> = {};
    try {
      criteria = criteriaText.trim() ? JSON.parse(criteriaText) : {};
    } catch {
      return setErr("Критерии должны быть валидным JSON");
    }

    setLoading(true);
    try {
      await api.createTask({
        name: name.trim(),
        url: url.trim(),
        site_type: createSiteType,
        criteria,
      });
      setName("");
      setUrl("");
      setCriteriaText('{"depth": 1}');
      await load();
    } catch (e: any) {
      setErr(e?.message ?? "Ошибка создания");
    } finally {
      setLoading(false);
    }
  }

  async function onDelete(id: string) {
    if (!confirm("Удалить задачу?")) return;
    setLoading(true);
    setErr(null);
    try {
      await api.deleteTask(id);
      await load();
    } catch (e: any) {
      setErr(e?.message ?? "Ошибка удаления");
    } finally {
      setLoading(false);
    }
  }

  async function onStatus(id: string, newStatus: TaskStatus) {
    setLoading(true);
    setErr(null);
    try {
      await api.updateStatus(id, newStatus);
      await load();
    } catch (e: any) {
      setErr(e?.message ?? "Ошибка обновления статуса");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: 1100, margin: "24px auto", fontFamily: "-apple-system, system-ui, Segoe UI, Roboto, Arial" }}>
      <h1 style={{ marginBottom: 6 }}>TaskService — задачи парсинга</h1>
      <div style={{ color: "#555", marginBottom: 18 }}>
        Бэк: <code>http://localhost:8000</code> · API: <code>/api/tasks</code>
      </div>

      {err && (
        <div style={{ padding: 12, border: "1px solid #f0c", borderRadius: 10, marginBottom: 16 }}>
          <b>Ошибка:</b> {err}
        </div>
      )}

      <div style={{ padding: 16, border: "1px solid #ddd", borderRadius: 12, marginBottom: 18 }}>
        <h2 style={{ marginTop: 0 }}>Создать задачу</h2>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 220px", gap: 12 }}>
          <label>
            Название
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Напр. Парсинг каталога"
              style={{ width: "100%", padding: 10, marginTop: 6 }} />
          </label>

          <label>
            URL
            <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com"
              style={{ width: "100%", padding: 10, marginTop: 6 }} />
          </label>

          <label>
            Тип сайта
            <select value={createSiteType} onChange={(e) => setCreateSiteType(e.target.value as SiteType)}
              style={{ width: "100%", padding: 10, marginTop: 6 }}>
              {Object.entries(siteTypeRu).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </label>
        </div>

        <label style={{ display: "block", marginTop: 12 }}>
          Критерии (JSON)
          <textarea value={criteriaText} onChange={(e) => setCriteriaText(e.target.value)} rows={6}
            style={{ width: "100%", padding: 10, marginTop: 6, fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }} />
        </label>

        <button onClick={onCreate} disabled={loading}
          style={{ marginTop: 12, padding: "10px 14px", borderRadius: 10, border: "1px solid #333", cursor: "pointer" }}>
          {loading ? "…" : "Создать"}
        </button>
      </div>

      <div style={{ padding: 16, border: "1px solid #ddd", borderRadius: 12, marginBottom: 12 }}>
        <h2 style={{ marginTop: 0 }}>Задачи</h2>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 220px 220px 140px", gap: 12, alignItems: "end" }}>
          <label>
            Поиск по названию
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="например, amazon"
              style={{ width: "100%", padding: 10, marginTop: 6 }} />
          </label>

          <label>
            Тип сайта
            <select value={siteType} onChange={(e) => setSiteType(e.target.value as any)}
              style={{ width: "100%", padding: 10, marginTop: 6 }}>
              <option value="">Все</option>
              {Object.entries(siteTypeRu).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </label>

          <label>
            Статус
            <select value={status} onChange={(e) => setStatus(e.target.value as any)}
              style={{ width: "100%", padding: 10, marginTop: 6 }}>
              <option value="">Все</option>
              {Object.entries(statusRu).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </label>

          <button onClick={load} disabled={loading}
            style={{ padding: "10px 14px", borderRadius: 10, border: "1px solid #333", cursor: "pointer" }}>
            Обновить
          </button>
        </div>
      </div>

      <div style={{ border: "1px solid #ddd", borderRadius: 12, overflow: "hidden" }}>
        <div style={{ display: "grid", gridTemplateColumns: "260px 1fr 160px 160px 220px 110px", background: "#f7f7f7", padding: 10, fontWeight: 600 }}>
          <div>Название</div>
          <div>URL</div>
          <div>Тип</div>
          <div>Статус</div>
          <div>Действия</div>
          <div></div>
        </div>

        {items.length === 0 && (
          <div style={{ padding: 14, color: "#666" }}>{loading ? "Загрузка…" : "Пока нет задач"}</div>
        )}

        {items.map((t) => (
          <div key={t.id} style={{ display: "grid", gridTemplateColumns: "260px 1fr 160px 160px 220px 110px", padding: 10, borderTop: "1px solid #eee", alignItems: "center" }}>
            <div title={t.name} style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.name}</div>
            <a href={t.url} target="_blank" rel="noreferrer" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.url}</a>
            <div>{siteTypeRu[t.site_type]}</div>
            <div>{statusRu[t.status]}</div>

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <select value={t.status} onChange={(e) => onStatus(t.id, e.target.value as TaskStatus)} style={{ padding: 8, borderRadius: 10 }}>
                {Object.entries(statusRu).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </div>

            <div>
              <button onClick={() => onDelete(t.id)} disabled={loading}
                style={{ padding: "8px 10px", borderRadius: 10, border: "1px solid #c00", cursor: "pointer" }}>
                Удалить
              </button>
            </div>
          </div>
        ))}
      </div>

      <div style={{ color: "#777", marginTop: 12, fontSize: 13 }}>
        Подсказка: “Критерии” сейчас редактируются при создании задачи. Если нужно — добавим редактирование JSON.
      </div>
    </div>
  );
}

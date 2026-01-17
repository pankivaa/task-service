export type SiteType = "marketplace" | "news" | "ecommerce" | "classifieds" | "other";
export type TaskStatus = "created" | "running" | "paused" | "completed" | "failed";

export type Task = {
  id: string;
  name: string;
  url: string;
  site_type: SiteType;
  status: TaskStatus;
  criteria: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type TaskList = {
  items: Task[];
  total: number;
  limit: number;
  offset: number;
};

export type TaskCreate = {
  name: string;
  url: string;
  site_type: SiteType;
  criteria: Record<string, unknown>;
};
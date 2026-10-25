export const API = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";
const AUTH_TOKEN_KEY = "lci_access_token";

export function getAuthToken() {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

export function setAuthToken(token: string | null) {
  if (token) localStorage.setItem(AUTH_TOKEN_KEY, token);
  else localStorage.removeItem(AUTH_TOKEN_KEY);
}

export interface Repo { id: number; name: string; url: string; status: string; created_at: string; file_count: number; symbol_count: number }
export interface AuthResponse { access_token: string; token_type: string; user: { id: number; email: string } }
export interface RepositorySummary {
  repository_id: number;
  languages: Record<string, number>;
  supported_files: number;
  unsupported_files: number;
  confidence: Record<string, number>;
  analysis: {
    job_id: string | null; created_at: string | null; source_commit: string | null;
    files: number; symbols: number; dependencies: number; parse_error_count: number;
    parse_errors: { file: string; error: string }[];
  };
  spotlight: { symbol_id: number; name: string; qualname: string; file_path: string; links: number } | null;
}
export interface UpdateCheck { supported: boolean; stale: boolean; analyzed_commit: string | null; remote_commit: string | null }
export interface Job { id: string; repository_id: number | null; kind: string; status: string; message: string; error: string | null; result: Record<string, unknown> | null; created_at: string; finished_at: string | null }
export interface FileInfo { path: string; language: string; size: number; line_count: number }
export interface Sym { id: number; qualname: string; name: string; kind: string; file_path: string; start_line: number; end_line: number; params: string[]; route: string | null; is_test: boolean }
export interface GraphNode { id: number; qualname: string; name: string; kind: string; file_path: string; depth: number; meta: { route?: string | null; is_test?: boolean } }
export interface GraphEdge { source: number; target: number; kind: string; confidence: string }
export interface Graph { nodes: GraphNode[]; edges: GraphEdge[] }
export interface Ref { id: number; name: string; kind: string; file_path: string; start_line: number; depth: number; route: string | null }
export interface Impact {
  target: { id: number; name: string; kind: string; file_path: string };
  risk: { level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"; score: number; max_score: number; disclaimer: string; factors: { factor: string; value: number; points: number; explanation: string }[] };
  summary: { affected_files: number; affected_functions: number; affected_apis: number; related_tests: number; max_depth: number };
  direct_dependents: Ref[]; affected_functions: Ref[]; affected_files: string[]; affected_apis: Ref[]; related_tests: Ref[];
  dependency_paths: { id: number; label: string; kind: string; file_path: string; heuristic_link: boolean }[][];
  reason: string;
}
export interface Link { id: number; name: string; file_path: string; confidence: string }
export interface Explanation {
  facts: { qualname: string; kind: string; file_path: string; lines: number[]; parameters: string[]; returns: string | null; route: string | null; calls: Link[]; called_by: Link[]; side_effects: string[] };
  analysis: { purpose: string; business_logic: string | null; concerns: string[]; inferences: string[] };
  source: string; provider: string;
}
export interface TestCase { id: number; symbol_id: number; code: string; source: string; status: string; output: string; exit_code: number | null; created_at: string }
export interface AnswerStep {
  title: string;
  detail: string;
  symbol_id?: number;
  symbol_name?: string;
  file_path?: string;
  start_line?: number;
}
export interface Answer {
  answer: string;
  sources: { symbol_id: number; qualname: string; file_path: string; start_line: number; end_line: number; score: number }[];
  source: string;
  provider: string;
  steps?: AnswerStep[];
  plan_source?: "llm" | "retrieval";
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    const token = getAuthToken();
    res = await fetch(`${API}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new Error(`Cannot reach the API at ${API}. Is the backend running?`);
  }
  if (!res.ok) {
    if (res.status === 401 && getAuthToken()) {
      setAuthToken(null);
      window.dispatchEvent(new Event("lci:unauthorized"));
    }
    const body = await res.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : `Request failed (${res.status})`;
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}
const post = <T,>(path: string, body?: unknown) => call<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });

export const api = {
  signup: (email: string, password: string) => post<AuthResponse>("/auth/signup", { email, password }),
  login: (email: string, password: string) => post<AuthResponse>("/auth/login", { email, password }),
  health: () => call<{ status: string; llm_provider: string; docker: boolean }>("/health"),
  repos: () => call<Repo[]>("/repositories"),
  repo: (id: number) => call<Repo>(`/repositories/${id}`),
  repositorySummary: (id: number) => call<RepositorySummary>(`/repositories/${id}/summary`),
  checkUpdates: (id: number) => post<UpdateCheck>(`/repositories/${id}/check-updates`),
  refresh: (id: number) => post<{ job_id: string; status: string }>(`/repositories/${id}/refresh`),
  addRepo: (repo_url: string, repo_name: string) => post<Repo>("/repositories", { repo_url, repo_name }),
  addDemo: () => post<Repo>("/repositories/demo"),
  analyze: (id: number) => post<{ job_id: string; status: string }>(`/repositories/${id}/analyze`),
  jobs: (repoId?: number) => call<Job[]>(`/jobs${repoId ? `?repository_id=${repoId}` : ""}`),
  job: (id: string) => call<Job>(`/jobs/${id}`),
  files: (id: number) => call<FileInfo[]>(`/repositories/${id}/files`),
  file: (id: number, path: string) => call<{ path: string; content: string }>(`/repositories/${id}/file?path=${encodeURIComponent(path)}`),
  symbols: (id: number) => call<Sym[]>(`/repositories/${id}/symbols`),
  graph: (id: number, sid: number, up = 2, down = 2) => call<Graph>(`/repositories/${id}/symbols/${sid}/graph?up=${up}&down=${down}`),
  explain: (id: number, sid: number) => post<Explanation>(`/repositories/${id}/symbols/${sid}/explain`),
  impact: (id: number, sid: number) => post<Impact>(`/repositories/${id}/symbols/${sid}/impact`),
  genTests: (id: number, sid: number) => post<TestCase>(`/repositories/${id}/symbols/${sid}/tests`),
  runTest: (id: number, tid: number) => post<TestCase>(`/repositories/${id}/tests/${tid}/run`),
  ask: (id: number, question: string) => post<Answer>(`/repositories/${id}/ask`, { question }),
};

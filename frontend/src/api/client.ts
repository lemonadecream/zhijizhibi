// Thin fetch wrapper around the FastAPI backend. No vendor SDKs here -- just
// the same JSON contract the backend exposes, including the
// {error:{code,message}} envelope used for all expected failures.

const TOKEN_KEY = "cdp_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(t: string): void {
  localStorage.setItem(TOKEN_KEY, t);
}
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(message: string, code: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (res.status === 204) return undefined as T;

  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    /* no json body */
  }

  if (!res.ok) {
    const err = (body as { error?: { code?: string; message?: string } } | null)?.error;
    const message = err?.message ?? `请求失败 (${res.status})`;
    const code = err?.code ?? "http_error";
    // 401 且确实携带了 token：会话已失效。除清 localStorage 外，广播事件让
    // AuthContext 同步清空 React 状态，RequireAuth 才能把用户送回登录页。
    // （只在带 token 的请求上广播，避免登录页的密码错误也触发登出。）
    if (res.status === 401 && token) {
      clearToken();
      window.dispatchEvent(new CustomEvent("cdp:auth-expired"));
    }
    throw new ApiError(message, code, res.status);
  }
  return body as T;
}

export const api = {
  // ----------------------------- auth -----------------------------
  register(input: { email?: string; phone?: string; password: string; name?: string }) {
    return request<{ access_token: string; token_type: string }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  login(input: { identifier: string; password: string }) {
    return request<{ access_token: string; token_type: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  me() {
    return request<{ user_id: number; email: string | null; phone: string | null }>("/api/auth/me");
  },

  // ----------------------------- runtime config (P0-1) -----------------------------
  // Read-only, non-sensitive: tells the UI whether a real AI provider is wired
  // up so it can show honest status badges (real / mock / degraded).
  getConfig() {
    return request<{ ai_provider: string; ai_available: boolean }>("/api/config");
  },

  // ----------------------------- resume / F1 -----------------------------
  uploadResume(file: File) {
    const fd = new FormData();
    fd.append("file", file);
    return request<ResumeStatus>("/api/resume/upload", { method: "POST", body: fd });
  },
  parseText(text: string) {
    return request<ResumeStatus>("/api/resume/parse-text", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
  },
  getResume(id: number) {
    return request<ResumeStatus>(`/api/resume/${id}`);
  },
  confirmResume(id: number, parsedJson: F1Parsed) {
    return request<{ confirmed: boolean }>(`/api/resume/${id}/confirm`, {
      method: "POST",
      body: JSON.stringify({ parsed_json: parsedJson }),
    });
  },

  // ----------------------------- experience (manual) -----------------------------
  saveManualExperience(input: ExperienceInput) {
    return request<{ saved: boolean }>("/api/experience", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  // ----------------------------- profile / F2 -----------------------------
  generateProfile(payload: { resume_id?: number }) {
    return request<{ status: string; profile_id: number | null }>("/api/profile/generate", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  getProfile() {
    return request<ProfileOut>("/api/profile");
  },
  updateProfile(input: ProfileUpdate) {
    return request<{ status: string; version: number | null }>("/api/profile", {
      method: "PUT",
      body: JSON.stringify(input),
    });
  },

  // ----------------------------- onboarding (Phase 1B) -----------------------------
  getOnboardingSession() {
    return request<OnboardingSession>("/api/onboarding/session");
  },
  startOnboardingSession() {
    return request<OnboardingSession>("/api/onboarding/session", { method: "POST" });
  },
  bootstrapOnboarding(input: { entry_method: string; resume_id?: number | null }) {
    return request<OnboardingSession>("/api/onboarding/bootstrap", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  onboardingStep(message: string) {
    return request<OnboardingStepResult>("/api/onboarding/step", {
      method: "POST",
      body: JSON.stringify({ message }),
    });
  },
  /** 访谈流式版本：SSE 增量回调 + 最终结果回调；失败走 onError（调用方可回退非流式）。 */
  async streamOnboardingStep(
    message: string,
    h: { onDelta(t: string): void; onDone(res: OnboardingStepResult): void; onError(m: string): void }
  ): Promise<void> {
    const headers = new Headers({ "Content-Type": "application/json" });
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const res = await fetch(`${API_BASE}/api/onboarding/step/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify({ message }),
    });
    if (!res.ok || !res.body) {
      h.onError(`流式连接失败 (${res.status})`);
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        let event = "message";
        let data = "";
        for (const line of block.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) data += line.slice(5).trim();
        }
        if (!data) continue;
        try {
          const parsed = JSON.parse(data);
          if (event === "delta") h.onDelta(String(parsed.text ?? ""));
          else if (event === "done") h.onDone(parsed as OnboardingStepResult);
          else if (event === "error") h.onError(String(parsed.message ?? "流式响应异常"));
        } catch {
          /* 忽略无法解析的块 */
        }
      }
    }
  },
  onboardingCorrect(input: { dimension: string; from_text?: string; to_text?: string }) {
    return request<OnboardingSession>("/api/onboarding/correct", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  onboardingFinalize() {
    return request<{ profile_id: number | null; status: string; version: number | null; ai_failed: boolean }>(
      "/api/onboarding/finalize",
      { method: "POST" }
    );
  },

  // ----------------------------- explore (Phase 2) -----------------------------
  getExploreState() {
    return request<ExploreHome>("/api/explore/state");
  },
  getRecommendations() {
    return request<{ recommendations: DirectionOut[] }>("/api/explore/recommendations");
  },
  postPreferenceText(text: string) {
    return request<ExploreStateResponse>("/api/explore/preferences/text", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
  },
  excludeDirection(directionId: number, excluded: boolean) {
    return request<ExploreStateResponse>(
      `/api/explore/directions/${directionId}/exclude`,
      { method: "POST", body: JSON.stringify({ excluded }) }
    );
  },
  toggleCandidate(directionId: number) {
    return request<ExploreStateResponse>(
      `/api/explore/directions/${directionId}/candidate`,
      { method: "POST" }
    );
  },
  toggleCompare(directionId: number) {
    return request<ExploreStateResponse>(
      `/api/explore/directions/${directionId}/compare`,
      { method: "POST" }
    );
  },
  setCompare(directionIds: number[]) {
    return request<ExploreStateResponse>("/api/explore/compare", {
      method: "POST",
      body: JSON.stringify({ direction_ids: directionIds }),
    });
  },
  getCompare() {
    return request<CompareResult>("/api/explore/compare");
  },
  getDirectionDetail(directionId: number) {
    return request<DirectionDetail>(`/api/explore/directions/${directionId}`);
  },
  getIndustryDetail(industryId: number) {
    return request<IndustryDetail>(`/api/explore/industries/${industryId}`);
  },
  getJobDetail(jobId: number) {
    return request<JobDetail>(`/api/explore/jobs/${jobId}`);
  },
  setTargetDirection(directionId: number) {
    return request<{ state: ExploreState; target_direction_id: number }>("/api/explore/target", {
      method: "POST",
      body: JSON.stringify({ direction_id: directionId }),
    });
  },

  // ----------------------------- target job (Phase 3) -----------------------------
  getTargetJobHome() {
    return request<TargetJobHome>("/api/target-job/home");
  },
  createTargetJob(input: { direction_id?: number | null; job_id?: number | null; job_title?: string; company?: string; city?: string; raw_jd?: string }) {
    return request<TargetJobOut>("/api/target-job/create", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  parseTargetJobJD(input: { target_job_id: number; raw_jd: string; job_title?: string; company?: string; city?: string; direction_id?: number | null }) {
    return request<{ target_job: TargetJobOut; parse_status: string }>("/api/target-job/parse", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  confirmTargetJob(targetJobId: number, input: { ability_model: AbilityModel; industry?: string; responsibilities?: string[]; other_requirements?: string[]; job_title?: string; company?: string; city?: string }) {
    return request<TargetJobOut>(`/api/target-job/${targetJobId}`, {
      method: "PUT",
      body: JSON.stringify(input),
    });
  },
  getTargetJob(targetJobId: number) {
    return request<TargetJobOut>(`/api/target-job/${targetJobId}`);
  },
  deleteTargetJob(targetJobId: number) {
    return request<{ deleted: boolean }>(`/api/target-job/${targetJobId}`, { method: "DELETE" });
  },
  // 「当前岗位」= 最近操作的岗位（后端按 updated_at 取最新）。切换即触碰时间戳。
  setCurrentTargetJob(targetJobId: number) {
    return request<TargetJobOut>(`/api/target-job/${targetJobId}/set-current`, { method: "POST" });
  },
  runTargetJobMatch(targetJobId: number) {
    return request<MatchResultPayload>(`/api/target-job/${targetJobId}/match`, { method: "POST" });
  },
  getTargetJobMatch(targetJobId: number) {
    return request<MatchResultPayload>(`/api/target-job/${targetJobId}/match`);
  },

  // ----------------------------- prepare (Phase 4) -----------------------------
  getPrepHome(targetJobId?: number) {
    const q = targetJobId ? `?target_job_id=${targetJobId}` : "";
    return request<PrepHome>(`/api/prepare/home${q}`);
  },
  generatePrepPlan(targetJobId: number) {
    return request<{ prep_plan: PrepPlan; tasks: PrepTask[]; ai_status: string }>("/api/prepare/generate", {
      method: "POST",
      body: JSON.stringify({ target_job_id: targetJobId }),
    });
  },
  updatePrepTask(taskId: number, input: { status?: string; priority?: string; user_note?: string; title?: string; reason?: string; action_suggestion?: string }) {
    return request<{ task: PrepTask }>(`/api/prepare/task/${taskId}`, {
      method: "PUT",
      body: JSON.stringify(input),
    });
  },
  generateInterviewFocus(targetJobId: number) {
    return request<{ interview_focus: InterviewFocusItem[]; ai_status: string }>("/api/prepare/interview", {
      method: "POST",
      body: JSON.stringify({ target_job_id: targetJobId }),
    });
  },
  getInterviewFocus(targetJobId: number) {
    return request<{ interview_focus: InterviewFocusItem[] }>(`/api/prepare/interview?target_job_id=${targetJobId}`);
  },
  generateResumeAdvice(targetJobId: number) {
    return request<{ resume_advice: ResumeAdviceItem[]; ai_status: string }>("/api/prepare/resume", {
      method: "POST",
      body: JSON.stringify({ target_job_id: targetJobId }),
    });
  },
  getResumeAdvice(targetJobId: number) {
    return request<{ resume_advice: ResumeAdviceItem[] }>(`/api/prepare/resume?target_job_id=${targetJobId}`);
  },

  // ----------------------------- tracking (Phase 5) -----------------------------
  getTrackingOverview() {
    return request<TrackingOverview>("/api/tracking/overview");
  },
  listApplications(status?: string) {
    const q = status ? `?status=${encodeURIComponent(status)}` : "";
    return request<{ items: ApplicationOut[]; total: number }>(`/api/tracking/applications${q}`);
  },
  createApplication(input: ApplicationIn) {
    return request<ApplicationOut>("/api/tracking/applications", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  getApplication(applicationId: number) {
    return request<ApplicationDetail>(`/api/tracking/applications/${applicationId}`);
  },
  updateApplication(applicationId: number, input: ApplicationUpdateIn) {
    return request<ApplicationOut>(`/api/tracking/applications/${applicationId}`, {
      method: "PUT",
      body: JSON.stringify(input),
    });
  },
  deleteApplication(applicationId: number) {
    return request<{ deleted: boolean }>(`/api/tracking/applications/${applicationId}`, { method: "DELETE" });
  },
  createInterview(applicationId: number, input: InterviewIn) {
    return request<InterviewOut>(`/api/tracking/applications/${applicationId}/interviews`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  updateInterview(interviewId: number, input: InterviewUpdateIn) {
    return request<InterviewOut>(`/api/tracking/interviews/${interviewId}`, {
      method: "PUT",
      body: JSON.stringify(input),
    });
  },
  deleteInterview(interviewId: number) {
    return request<{ deleted: boolean }>(`/api/tracking/interviews/${interviewId}`, { method: "DELETE" });
  },

  // ----------------------------- offer (Phase 6) -----------------------------
  listOffers(status?: string) {
    const q = status ? `?status=${encodeURIComponent(status)}` : "";
    return request<{ items: OfferOut[]; total: number }>(`/api/offer/applications${q}`);
  },
  createOffer(input: OfferIn) {
    return request<OfferOut>("/api/offer/applications", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  getOffer(offerId: number) {
    return request<OfferOut>(`/api/offer/applications/${offerId}`);
  },
  updateOffer(offerId: number, input: Partial<OfferIn>) {
    return request<OfferOut>(`/api/offer/applications/${offerId}`, {
      method: "PUT",
      body: JSON.stringify(input),
    });
  },
  deleteOffer(offerId: number) {
    return request<{ deleted: boolean }>(`/api/offer/applications/${offerId}`, { method: "DELETE" });
  },
  acceptOffer(offerId: number) {
    return request<OfferOut & { other_active_offers?: OfferOut[]; hint?: string | null }>(
      `/api/offer/applications/${offerId}/accept`, { method: "POST" }
    );
  },
  salaryCalc(offerId: number, input?: Record<string, unknown>) {
    return request<{ offer_id: number; city: string | null; results: SalaryResult; param_snapshot: Record<string, unknown> }>(
      `/api/offer/applications/${offerId}/salary_calc`,
      { method: "POST", body: JSON.stringify(input ?? {}) }
    );
  },
  listCities() {
    return request<{ cities: CityCost[]; user_overrides: CityCost[] }>("/api/offer/cities");
  },
  updateCity(city: string, input: Partial<CityCost>) {
    return request<CityCost>(`/api/offer/cities/${encodeURIComponent(city)}`, {
      method: "PUT",
      body: JSON.stringify(input),
    });
  },
  assessOffer(offerId: number, input?: { public_signals?: string[]; user_notes?: string }) {
    return request<{ offer_id: number; assessments: Record<string, OfferDimensionView>; ai_status: string }>(
      `/api/offer/applications/${offerId}/assess`, {
        method: "POST",
        body: JSON.stringify(input ?? {}),
      }
    );
  },
  getWeights() {
    return request<{ weights: Record<string, number>; preset_name: string | null }>("/api/offer/weights");
  },
  saveWeights(input: { weights: Record<string, number>; preset_name?: string | null }) {
    return request<{ weights: Record<string, number>; preset_name: string | null }>("/api/offer/weights", {
      method: "PUT",
      body: JSON.stringify(input),
    });
  },
  getComparison(offerIds?: number[]) {
    const q = offerIds && offerIds.length ? `?offer_ids=${offerIds.join(",")}` : "";
    return request<ComparisonResult>(`/api/offer/comparison${q}`);
  },
};

// ----------------------------- types -----------------------------
export interface F1Signal {
  type: string;
  text: string;
  evidence: string;
}
export interface F1Parsed {
  education: { school: string; major: string; degree?: string; start?: string; end?: string }[];
  internships: { company: string; role: string; start?: string; end?: string; duty?: string }[];
  projects: { name: string; role?: string; desc?: string }[];
  skills: { name: string; level?: number }[];
  interests: string[];
  signals: F1Signal[];
}

export interface ResumeStatus {
  resume_id: number;
  parse_status: "pending" | "parsing" | "parsed" | "failed";
  filename?: string | null;
  parsed_json?: F1Parsed | null;
  error?: string | null;
}

export interface ExperienceInput {
  education: Record<string, unknown>[];
  internships: Record<string, unknown>[];
  projects: Record<string, unknown>[];
  skills: Record<string, unknown>[];
  interests: string[];
}

export interface TagWithEvidence {
  tag: string;
  evidence: string;
}
export interface AbilityTag extends TagWithEvidence {
  level?: number | null;
  confidence?: number | null;
}
export interface Strength {
  item: string;
  evidence: string;
}
export interface Risk {
  item: string;
  evidence: string;
  strategy: string;
}
export interface ProfileOut {
  profile_id?: number | null;
  status?: string | null;
  version?: number | null;
  ability_tags: AbilityTag[];
  interest_tags: TagWithEvidence[];
  strengths: Strength[];
  risks: Risk[];
  preference_infer: Record<string, unknown>;
  ai_failed: boolean;
}
export interface ProfileUpdate {
  ability_tags: AbilityTag[];
  interest_tags: TagWithEvidence[];
  strengths: Strength[];
  risks: Risk[];
  preference_infer: Record<string, unknown>;
}

// ----------------------------- onboarding (Phase 1B) -----------------------------
export interface DimensionState {
  dimension: string;
  covered: boolean;
  confidence: number;
  note: string;
}
export interface OnboardingUnderstanding {
  tags: string[];
  sentences: string[];
  evidence: Record<string, string>;
}
export interface OnboardingSession {
  session_id: number;
  status: string;
  entry_method?: string | null;
  resume_id?: number | null;
  understanding: OnboardingUnderstanding;
  wants_to_know: string[];
  dimension_state: DimensionState[];
  history: { role: string; text: string; ts?: string }[];
  corrections: { dimension: string; from: string; to: string; ts?: string }[];
  summary_pending: { ready?: boolean; summary?: string };
}
export interface OnboardingStepResult extends OnboardingSession {
  ai_response: string;
  questions: string[];
  completion_ready: boolean;
  summary_candidate: string;
  ai_status: string;
}

// ----------------------------- explore (Phase 2) -----------------------------
export interface ProfileSummary {
  positioning: string;
  tendencies: unknown[];
  motivations: string[];
  gaps: unknown[];
  career_goal: string;
  ability_tags: string[];
  interest_tags: string[];
  strengths: string[];
  risks: unknown[];
}

export interface DirectionOut {
  direction_id: number;
  name: string;
  summary: string;
  description: string;
  core_abilities: string[];
  work_styles: string[];
  industry_ids: number[];
  job_ids: number[];
  attributes: Record<string, number>;
  not_good_for: string[];
  growth_path: string;
  score: number;
  match_basis: string[];
  reason: string;
  reason_status: string;
  status: string;
}

export interface ExploreState {
  preferences: Record<string, unknown>;
  excluded_direction_ids: number[];
  candidate_direction_ids: number[];
  compare_direction_ids: number[];
  target_direction_id: number | null;
}

export interface ExploreStateResponse {
  state: ExploreState;
  recommendations?: DirectionOut[];
  parsed?: Record<string, unknown>;
}

export interface ExploreHome {
  has_profile: boolean;
  profile: ProfileSummary | null;
  recommendations: DirectionOut[];
  state: ExploreState;
}

export interface CompareRow {
  direction_id: number;
  name: string;
  summary: string;
  score: number;
  work_styles: string[];
  core_abilities: string[];
  attributes: Record<string, number>;
  not_good_for: string[];
  growth_path: string;
}

export interface CompareResult {
  rows: CompareRow[];
  advice: string[];
}

export interface IndustryBrief {
  id: number;
  name: string;
  description: string;
  traits: string[];
}

export interface JobBrief {
  id: number;
  name: string;
  description: string;
  required_abilities: string[];
  entry_barrier: number;
  work_styles: string[];
}

export interface DirectionDetail {
  direction: DirectionOut;
  industries: IndustryBrief[];
  jobs: JobBrief[];
}

export interface IndustryDetail {
  id: number;
  name: string;
  description: string;
  traits: string[];
  work_styles: string[];
  jobs: JobBrief[];
}

export interface JobDetail {
  id: number;
  name: string;
  description: string;
  required_abilities: string[];
  entry_barrier: number;
  work_styles: string[];
}

// ----------------------------- target job (Phase 3) -----------------------------
export interface AbilityItem {
  name: string;
  category: string; // hard | soft | plus
  level: number;
  weight: number;
  requirement_type?: string;
}
export interface AbilityModel {
  abilities: AbilityItem[];
  requirements: { education: string; experience_years: number; major: string[]; cert: string[] };
  responsibilities?: string[];
  other_requirements?: string[];
  industry?: string;
  title?: string;
  company?: string;
}
export interface TargetJobOut {
  target_job_id: number;
  user_id: number;
  direction_id: number | null;
  job_id: number | null;
  job_title: string;
  company: string;
  city: string;
  source_jd: { raw_text: string; parsed_json?: Record<string, unknown> };
  ability_model: AbilityModel;
  industry: string;
  responsibilities: string[];
  other_requirements: string[];
  jd_status: string;
  created_at: string | null;
  updated_at: string | null;
}
export interface TargetJobBrief {
  target_job_id: number;
  job_title: string;
  company: string;
  city: string;
  jd_status: string;
  updated_at: string | null;
}
export interface TargetJobHome {
  has_target: boolean;
  items: TargetJobOut[];
  current: TargetJobOut | null;
  match_summary: { total_score: number; ai_status: string; gap_count: number } | null;
}
export interface RelationJudgement {
  ability: string;
  category: string;
  requirement_type: string;
  level: number;
  weight: number;
  relation: "covered" | "partial" | "missing";
  coverage: number;
  reason: string;
  evidence: string;
}
export interface DimensionScore {
  axis: string;
  category: string;
  score: number;
}
export interface MatchItem {
  ability: string;
  category: string;
  evidence: string;
}
export interface RiskItem {
  ability: string;
  relation: string;
  category: string;
  evidence: string;
  reason: string;
}
export interface MatchResult {
  match_id: number;
  target_job_id: number;
  profile_version: number | null;
  jd_version: number;
  total_score: number;
  dimension_scores: DimensionScore[];
  strengths: MatchItem[];
  risks: RiskItem[];
  relation_judgements: RelationJudgement[];
  ai_status: string;
  created_at: string | null;
  updated_at: string | null;
}
export interface CapabilityGap {
  gap_id: number;
  match_id: number;
  ability: string;
  current_evidence: string[];
  required_level: number | null;
  gap_degree: number;
  priority: string;
  why: string;
  evidence: string;
  improvement_direction: string;
  status: string;
  created_at: string | null;
}
export interface MatchResultPayload {
  match: MatchResult;
  gaps: CapabilityGap[];
}

// ----------------------------- prepare (Phase 4) -----------------------------
export interface PrepPlan {
  plan_id: number;
  target_job_id: number;
  match_id: number;
  status: string; // empty | ready | completed
  overall_progress: number; // 0..100, program-computed
  ai_status: string; // ok | fallback (P0-1 transparency)
  created_at: string | null;
  updated_at: string | null;
}
export interface PrepTask {
  task_id: number;
  plan_id: number;
  gap_id: number | null;
  ability: string;
  title: string;
  reason: string;
  current_situation: string;
  action_suggestion: string;
  priority: string; // high | medium | low
  user_priority_override: boolean;
  status: string; // pending | done
  user_note: string;
  is_user_edited: boolean;
  order: number;
}
export interface InterviewFocusItem {
  focus_id: number;
  question: string;
  reason: string;
  related_requirement: string;
  related_experience: string;
  preparation_advice: string;
  evidence_status: string; // sufficient | insufficient | none
  ai_status: string;
}
export interface ResumeAdviceItem {
  advice_id: number;
  advice_type: string; // highlight | evidence_gap | keyword | weak_link
  content: string;
  related_experience: string;
  related_gap: string;
  severity: string; // high | medium | low
  ai_status: string;
}
export interface PrepTargetJob {
  target_job_id: number;
  job_title: string;
  company: string;
  city: string;
  industry: string;
  jd_status: string;
}
export interface PrepGap {
  gap_id: number;
  ability: string;
  priority: string;
  gap_degree: number;
  why: string;
  evidence: string;
  improvement_direction: string;
  status: string;
}
export interface PrepHome {
  has_target: boolean;
  has_match: boolean;
  target_job: PrepTargetJob | null;
  match_summary: { total_score: number; ai_status: string; gap_count: number } | null;
  gaps: PrepGap[];
  prep_plan: PrepPlan | null;
  tasks: PrepTask[];
  interview_focus: InterviewFocusItem[];
  resume_advice: ResumeAdviceItem[];
  prep_stale: boolean;
  interview_stale: boolean;
  resume_stale: boolean;
}

// ----------------------------- tracking (Phase 5) -----------------------------
export type ApplicationStatus =
  | "drafted"
  | "applied"
  | "written_test"
  | "interviewing"
  | "offer_received"
  | "rejected"
  | "withdrawn";

export interface ApplicationIn {
  company: string;
  job_title: string;
  city?: string | null;
  job_url?: string | null;
  source?: string | null;
  applied_at?: string | null;
  status?: ApplicationStatus;
  next_action?: string | null;
  next_action_at?: string | null;
  note?: string;
  target_job_id?: number | null;
}
export interface ApplicationUpdateIn {
  company?: string;
  job_title?: string;
  city?: string | null;
  job_url?: string | null;
  source?: string | null;
  applied_at?: string | null;
  status?: ApplicationStatus;
  next_action?: string | null;
  next_action_at?: string | null;
  note?: string | null;
  target_job_id?: number | null;
}
export interface ApplicationOut {
  application_id: number;
  user_id: number;
  target_job_id: number | null;
  company: string;
  job_title: string;
  city: string | null;
  job_url: string | null;
  source: string | null;
  applied_at: string | null;
  status: ApplicationStatus;
  status_label: string;
  next_action: string | null;
  next_action_at: string | null;
  note: string;
  timeline: { status: string; from_status?: string; ts: string; note?: string }[];
  created_at: string | null;
  updated_at: string | null;
}
export interface InterviewIn {
  round?: string | null;
  interview_type?: string | null;
  scheduled_at?: string | null;
  interviewer?: string | null;
  status?: "scheduled" | "completed" | "cancelled";
  result?: "pending" | "pass" | "fail";
  note?: string | null;
}
export interface InterviewUpdateIn {
  round?: string | null;
  interview_type?: string | null;
  scheduled_at?: string | null;
  status?: "scheduled" | "completed" | "cancelled";
  result?: "pending" | "pass" | "fail";
  interviewer?: string | null;
  note?: string | null;
}
export interface InterviewOut {
  interview_id: number;
  application_id: number;
  user_id: number;
  round: string | null;
  interview_type: string | null;
  scheduled_at: string | null;
  status: string;
  interviewer: string | null;
  result: string;
  note: string | null;
  created_at: string | null;
  updated_at: string | null;
}
export interface ApplicationDetail {
  application: ApplicationOut;
  interviews: InterviewOut[];
  timeline: {
    kind: "status" | "interview";
    status?: string;
    from_status?: string;
    interview_id?: number;
    round?: string | null;
    interview_type?: string | null;
    result?: string;
    ts: string;
    note?: string | null;
  }[];
}
export interface TrackingOverview {
  total: number;
  counts: Record<string, number>;
  counts_labeled: Record<string, number>;
  upcoming_interviews: InterviewOut[];
  recent: ApplicationOut[];
}

// ----------------------------- offer (Phase 6) -----------------------------
export interface OfferIn {
  company: string;
  job_title: string;
  city?: string | null;
  industry?: string | null;
  work_location?: string | null;
  start_date?: string | null;
  salary?: {
    monthly_base?: number | null;
    annual_bonus_months?: number | null;
    sign_on?: number | null;
    equity_value?: number | null;
  };
  insurance_base?: number | null;
  fund_rate?: number | null;
  special_deduction?: number;
  benefits?: unknown[];
  note?: string;
  status?: string;
  application_id?: number | null;
  target_job_id?: number | null;
}
export interface CityCost {
  city: string;
  rent: number;
  food: number;
  transport: number;
  misc: number;
  data_version?: string;
  source?: string;
}
export interface OfferDimensionView {
  dimension: string;
  label: string;
  tier: string;
  score: number;
  reason: string;
  source: string;
}
export interface SalaryResult {
  monthly_base: number;
  insurance_base: number;
  fund_rate: number;
  insurance: { name: string; rate: number; amount: number }[];
  insurance_total: number;
  taxable_monthly: number;
  monthly_tax: number;
  monthly_after_tax: number;
  annual_bonus_months: number;
  annual_bonus_gross: number;
  annual_bonus_tax: number;
  annual_bonus_after_tax: number;
  annual_after_tax: number;
  sign_on: number;
  equity_value: number;
  tax_version: string;
  policy_version: string;
}
export interface OfferOut {
  offer_id: number;
  company: string;
  industry?: string | null;
  job_title: string;
  city?: string | null;
  work_location?: string | null;
  start_date?: string | null;
  salary: { monthly_base?: number; annual_bonus_months?: number; sign_on?: number; equity_value?: number } | null;
  insurance_base?: number | null;
  fund_rate?: number | null;
  special_deduction: number;
  benefits: unknown[];
  note: string;
  status: string;
  status_label: string;
  application_id?: number | null;
  target_job_id?: number | null;
  timeline: { status: string; from_status?: string; ts: string; note?: string }[];
  created_at?: string | null;
  updated_at?: string | null;
}
export interface ComparisonResult {
  comparison_id: string;
  offers: {
    offer_id: number;
    company: string;
    job_title: string;
    city?: string | null;
    status: string;
    dimension_scores: Record<string, number | null>;
    composite_score: number;
    rank: number;
  }[];
  weights: Record<string, number>;
  weight_snapshot: Record<string, number>;
  city_costs: Record<string, { monthly_total: number; annual_total: number }>;
  analysis: {
    recommendations: { focus: string; conditionals: string[]; caveats: string[] }[];
    ai_status: string;
    error?: string | null;
  };
}

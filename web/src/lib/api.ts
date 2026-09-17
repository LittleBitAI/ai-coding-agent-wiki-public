// 백엔드와의 접점 전부. 다른 곳에서 fetch 를 부르지 않는다.
//
// SSE 인데 EventSource 를 안 쓴다. EventSource 는 GET 만 되고 발화는 본문에
// 실어야 하기 때문이다. 그래서 fetch 의 스트림을 직접 읽는다 — 이십몇 줄이고,
// 그 대가로 헤더도 본문도 마음대로 쓴다.

export type Channel = {
  id: string
  label: string
  blurb: string
  live: boolean
  repo: string
  remote: string
  model: string
  model_name: string
  effort: string
}

/** 정책 그래프. `tool/graph.py` 가 낸 `graph.json` 그대로다.
 *
 *  모양을 여기서 다시 적지 않는다. 노드 하나에 열 몇 칸이 있고, 그것을 타입으로
 *  베끼면 파이썬 쪽이 칸을 더할 때마다 두 곳을 고쳐야 한다. 그리는 코드가
 *  자기가 쓰는 칸만 알면 된다. */
export type GraphData = {
  ns: string
  nodes: { id: string; injected: boolean; chars: number }[]
  projects: { key: string; short: string; deny: number; corpus: number; note: string; status: Record<string, string> }[]
  ladder: { n: number; title: string; color: string }[]
  load: { max: number; median: number; hits: number }
  corpus: number
  cap: number
}

export type Project = { id: string; path: string; wired: boolean }
export type Choice = { id: string; label: string; note: string }
export type Options = {
  projects: Project[]
  models: (Choice & { efforts?: Choice[] })[]
  efforts: Choice[]
  codex_error: string
}

export type Turn = {
  ts: number
  role: 'user' | 'assistant'
  text: string
  source?: string
  error?: string
  simple_text?: string
  simple_error?: string
  simple_meta?: { ms?: number; cost_usd?: number }
  ms?: number
  cost_usd?: number
  model?: string
  session_id?: string
  tokens?: Tokens
}

export type Tokens = {
  in?: number
  out?: number
  cache_read?: number
  cache_write?: number
}

export type Ev = {
  kind: 'hits' | 'delta' | 'tool' | 'done' | 'error' | 'simple_start' | 'simple_delta' | 'simple_done' | 'simple_error'
  text: string
  pages?: string[]
  ms?: number
  error?: boolean
  session_id?: string
  model?: string
  cost_usd?: number
  tokens?: Tokens
}

export type Kind = '교정' | '재입력' | '부분수행' | '되돌림'
export const KINDS: Kind[] = ['교정', '재입력', '부분수행', '되돌림']

export type Peek = {
  path: string
  start: number
  line: number
  total: number
  lines: string[]
}

async function json<T>(res: Response, what: string): Promise<T> {
  if (!res.ok) {
    let detail = ''
    try {
      detail = (await res.json()).detail ?? ''
    } catch {
      // 본문이 JSON 이 아니면 상태 코드만으로 말한다.
    }
    throw new Error(detail || `${what} — 서버가 ${res.status} 로 답했다`)
  }
  return res.json()
}

const post = (url: string, body?: unknown) =>
  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

export const getChannels = () =>
  fetch('/api/channels').then((r) => json<Channel[]>(r, '채널 목록'))

export const getGraph = () =>
  fetch('/api/graph').then((r) => json<GraphData>(r, '위키 지도'))

export const getOptions = () =>
  fetch('/api/options').then((r) => json<Options>(r, '고를 것'))

export const getLog = (id: string, legacy = false) =>
  fetch(`/api/log/${id}?legacy=${legacy}`).then((r) => json<Turn[]>(r, '기록'))

export const reset = (id: string) => post(`/api/reset/${id}`).then((r) => json(r, '문맥 지우기'))

/** 프로젝트 선택은 모든 채널이 공유하고 대화는 프로젝트·채널별로 보존한다. */
export const setConfig = (id: string, cfg: { repo: string; model: string; effort: string }) =>
  post(`/api/config/${id}`, cfg).then((r) => json<{ kept: boolean; switched: boolean }>(r, '설정'))

/** 틀린 그 순간에 부류 하나를 찍는다. census 형식으로 쌓인다. */
export const mark = (
  id: string,
  body: { kind: Kind; user_text: string; assistant_text: string; session_id?: string },
) => post(`/api/mark/${id}`, body).then((r) => json<{ ok: boolean; total: number }>(r, '표시'))

/** 다음 세션에 붙일 글. */
export const handoff = (id: string) =>
  post(`/api/handoff/${id}`).then((r) => json<{ text: string }>(r, '인계'))

/** 회고 후보 하나의 운명. wiki · claude_md 는 실제로 파일을 쓴다. */
export const decide = (id: string, candidate: string, target: 'wiki' | 'claude_md' | 'drop') =>
  post(`/api/decide/${id}`, { candidate, target }).then((r) =>
    json<{ text: string; error: boolean; changed?: string; cost_usd?: number }>(r, '결정'),
  )

/** 인용된 경로:줄 의 그 자리. */
export const peek = (repo: string, path: string, line: number) =>
  fetch(
    `/api/file?${new URLSearchParams({ repo, path, line: String(line), around: '25' })}`,
  ).then((r) => json<Peek>(r, '파일'))

/** 발화 하나를 보내고 이벤트를 차례로 넘긴다. 중간에 끊으려면 signal 을 준다. */
export async function say(
  id: string,
  text: string,
  onEvent: (ev: Ev) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await post(`/api/say/${id}`, { text })
  if (!res.ok || !res.body) {
    onEvent({ kind: 'error', text: `서버가 ${res.status} 로 답했다` })
    return
  }
  void signal

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // SSE 는 빈 줄이 한 사건의 끝이다. 마지막 토막은 아직 안 끝났으니 남긴다.
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() ?? ''
    for (const chunk of chunks) {
      const line = chunk.split('\n').find((l) => l.startsWith('data: '))
      if (!line) continue
      try {
        onEvent(JSON.parse(line.slice(6)))
      } catch {
        // 반쪽짜리 JSON 은 버린다. 다음 사건이 온다.
      }
    }
  }
}

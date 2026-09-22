// Every point of contact with the backend. Nothing else calls fetch.
//
// It is SSE without `EventSource`, because `EventSource` is GET only and an
// utterance has to travel in the body. So the fetch stream is read directly —
// about twenty lines, and in exchange the headers and the body are ours.

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

/** The policy graph: `graph.json` exactly as `tool/graph.py` produced it.
 *
 *  The shape is not restated here. A node has a dozen or so fields, and
 *  copying them into a type means editing two places every time the Python
 *  side adds one. The drawing code only needs to know the fields it uses. */
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

/** One rendered piece. `mark` says what it is and whether it was translated. */
export type Part = {
  i: number
  mark: '' | '▶' | '·' | '$' | '──'
  text: string
  at: string
  name: string
}

export type Repo = { path: string; name: string; at: number }

export type Mirrors = {
  here: { host: string; project: string }
  hosts: Record<string, Repo[]>
}

/**
 * `gen` rises on every repository switch and answers whose a late piece is.
 * `feed` names the feed those `parts` indexes belong to — a restarted server
 * hands back the same `gen` for a different feed, and the id is what tells
 * those two apart.
 */
export type Frame = {
  gen: number
  feed: string
  host: string
  project: string
  parts: Part[]
}

async function json<T>(res: Response, what: string): Promise<T> {
  if (!res.ok) {
    let detail = ''
    try {
      detail = (await res.json()).detail ?? ''
    } catch {
      // With a body that is not JSON, the status code is all there is to say.
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

/** Every channel shares the project; conversations are kept per project and
 *  per channel. */
export const setConfig = (id: string, cfg: { repo: string; model: string; effort: string }) =>
  post(`/api/config/${id}`, cfg).then((r) => json<{ kept: boolean; switched: boolean }>(r, '설정'))

/** Name one category at the moment it went wrong, in the census's format. */
export const mark = (
  id: string,
  body: { kind: Kind; user_text: string; assistant_text: string; session_id?: string },
) => post(`/api/mark/${id}`, body).then((r) => json<{ ok: boolean; total: number }>(r, '표시'))

/** The text to hand the next session. */
export const handoff = (id: string) =>
  post(`/api/handoff/${id}`).then((r) => json<{ text: string }>(r, '인계'))

/** What becomes of one retro candidate. `wiki` and `claude_md` really do
 *  write files. */
export const decide = (id: string, candidate: string, target: 'wiki' | 'claude_md' | 'drop') =>
  post(`/api/decide/${id}`, { candidate, target }).then((r) =>
    json<{ text: string; error: boolean; changed?: string; cost_usd?: number }>(r, '결정'),
  )

/** The place a cited `path:line` points at. */
export const peek = (repo: string, path: string, line: number) =>
  fetch(
    `/api/file?${new URLSearchParams({ repo, path, line: String(line), around: '25' })}`,
  ).then((r) => json<Peek>(r, '파일'))

/** Render what a screen is about to show. Failure returns the original.
 *
 *  It calls the phase-one translator directly. Identifiers, paths, links and
 *  config values are lifted out before the request, so there is nothing for
 *  this side to mask. */
export const render = (texts: string[], direction: 'en->ko' | 'ko->en' = 'en->ko') =>
  post('/api/translate', { texts, direction }).then((r) =>
    json<{ texts: string[] }>(r, '번역'),
  )

/** For more than one request holds. Order and count survive intact.
 *
 *  The splitting lives here alone. Split at each call site and changing the
 *  limit means editing as many places as there are screens. */
const BATCH = 40

export async function renderAll(
  texts: string[],
  direction: 'en->ko' | 'ko->en' = 'en->ko',
): Promise<string[]> {
  const out: string[] = []
  for (let i = 0; i < texts.length; i += BATCH) {
    const { texts: done } = await render(texts.slice(i, i + BATCH), direction)
    out.push(...done)
  }
  return out
}

/** Every checkout with a session, and where the mirror is pointed now. */
export const getMirrors = () =>
  fetch('/api/mirror/repos').then((r) => json<Mirrors>(r, '저장소 목록'))

/** Move the mirror. Only a path the server itself listed is accepted. */
export const pointMirror = (host: string, project: string) =>
  post('/api/mirror/point', { host, project }).then((r) =>
    json<{ gen: number; host: string; project: string }>(r, '저장소 전환'),
  )

/** Keep receiving what the mirror renders. Pass a signal to cut it off.
 *
 *  Unlike `say`, this stream has no end. Closing the tab or leaving it aborts
 *  through `signal`, and the server's loop then stops on the closed socket. */
export async function mirrorStream(
  onFrame: (frame: Frame) => void,
  signal: AbortSignal,
): Promise<void> {
  const res = await fetch('/api/mirror/stream', { signal })
  if (!res.ok || !res.body) throw new Error(`서버가 ${res.status} 로 답했다`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() ?? ''
    for (const chunk of chunks) {
      const line = chunk.split('\n').find((l) => l.startsWith('data: '))
      if (!line) continue
      try {
        onFrame(JSON.parse(line.slice(6)))
      } catch {
        // Half a JSON object is dropped. The next event is coming.
      }
    }
  }
}

/** Send one utterance and hand back the events in order. `signal` cuts it short. */
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

    // In SSE a blank line ends one event. The last piece has not ended yet,
    // so it is carried over.
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() ?? ''
    for (const chunk of chunks) {
      const line = chunk.split('\n').find((l) => l.startsWith('data: '))
      if (!line) continue
      try {
        onEvent(JSON.parse(line.slice(6)))
      } catch {
        // Half a JSON object is dropped. The next event is coming.
      }
    }
  }
}

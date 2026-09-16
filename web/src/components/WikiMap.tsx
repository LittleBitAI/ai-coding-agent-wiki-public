// 위키 지도. `wiki.html` 이 하던 일이고, 이제 여기가 그 자리다.
//
// 산문은 안 옮겼다. 옛 페이지는 사다리 설명·옵시디언 비교·쓰는 법을 같이
// 담았는데 셋 다 README·SCHEMA·ENFORCEMENT 의 사본이었고, 그중 하나(쓰는 법)는
// 이미 낡아서 lint 를 "여섯 자리" 라고 적고 있었다. 여기 남은 것은 잰 값뿐이다.

import { useEffect, useRef, useState } from 'react'

import { mountGraph } from '@/graph/force'
import '@/graph/graph.css'
import { getGraph, type GraphData } from '@/lib/api'

export function WikiMap() {
  const [data, setData] = useState<GraphData | null>(null)
  const [error, setError] = useState('')
  const host = useRef<HTMLDivElement>(null)

  useEffect(() => {
    getGraph()
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  // 그리는 쪽은 명령형이고 뿌리를 통째로 잡는다. 그래서 데이터가 온 뒤 한 번만
  // 붙이고, 떠날 때 배치 루프를 멈춘다 — 안 멈추면 화면을 떠나도 계속 돈다.
  useEffect(() => {
    if (!data || !host.current) return
    return mountGraph(host.current, data)
  }, [data])

  if (error) return <p className="wikimap-note">지도를 못 읽었다 — {error}</p>
  if (!data) return <p className="wikimap-note">지도를 읽는 중…</p>

  const injected = data.nodes.filter((n) => n.injected).length
  const budget = data.cap ? `예산 ${data.cap.toLocaleString()}자` : '예산 없음'

  return (
    <div className="wikimap" ref={host}>
      <div className="wrap">
        <header>
          <p className="eyebrow">ai-coding-agent-wiki</p>
          <h1>측정해서 쓰고,<br />어기면 막는 위키</h1>
          <div className="meters">
            <div className="meter">
              <span className="v">{data.nodes.length}</span>
              <span className="k">페이지</span>
            </div>
            <div className="meter">
              <span className="v">{injected}</span>
              <span className="k">주입되는 규칙</span>
            </div>
            <div className="meter">
              <span className="v">{data.load.max.toLocaleString()}</span>
              <span className="k">한 턴 최대 (자)</span>
              <span className="n">중앙 {data.load.median.toLocaleString()} · {budget}</span>
            </div>
            <div className="meter">
              <span className="v">{data.corpus.toLocaleString()}</span>
              <span className="k">측정한 발화</span>
              <span className="n">그중 {data.load.hits.toLocaleString()}건에 실린다</span>
            </div>
          </div>
        </header>

        <h2>그래프</h2>
        <p className="lede">
          노드를 눌러 규칙을 펴고, 끌어서 옮기고, 휠로 확대한다. 크기는 그 규칙이 한
          턴에 싣는 글자수 — 페이지가 느는 것 자체가 비용이다. 색은 가장 세게
          강제되는 층이고, 사다리의 번호 순서와는 다르다.
        </p>

        <div className="controls">
          <div className="tabs">
            <button className="tab" data-project="all" aria-pressed="true">전체</button>
            {data.projects.map((p) => (
              <button key={p.key} className="tab" data-project={p.key} aria-pressed="false">
                {p.short}
              </button>
            ))}
          </div>
          <input id="search" type="search" placeholder="규칙 찾기" aria-label="규칙 찾기" />
          <button id="reset" className="ghost">되돌리기</button>
        </div>

        <div className="stage">
          <svg id="canvas" viewBox="0 0 900 560" role="img" aria-label="위키 규칙 그래프">
            <g id="view" />
          </svg>
          {/* 여기 안쪽은 그리는 쪽이 쓴다. React 가 자식을 갖지 않아야 안 부딪힌다. */}
          <aside id="panel" />
        </div>

        <div className="legend">
          {data.ladder.map((r) => (
            <button key={r.n} className="chip" data-layer={r.n} aria-pressed="true">
              <i className="swatch" style={{ background: r.color }} />
              {r.n}층 {r.title}
            </button>
          ))}
          <span className="static"><i className="solidline" />링크</span>
          <span className="static"><i className="dashline" />함께 실림</span>
        </div>

        <h2>프로젝트마다 무엇이 붙어 있나</h2>
        <p className="lede">
          위키가 무엇을 선언했는지가 아니라, 그쪽 <code>.claude/settings.json</code> 이
          실제로 무엇을 갖고 있는지를 읽은 값이다. 탭을 바꾸면 안 붙은 규칙이 비어 보인다.
        </p>
        <div className="scroll">
          <table>
            <thead>
              <tr><th>저장소</th><th>붙은 규칙</th><th>deny</th><th>코퍼스</th><th /></tr>
            </thead>
            <tbody>
              {data.projects.length === 0 && (
                <tr><td colSpan={5}>아직 붙인 저장소가 없다. <code>--project</code> 로 준다.</td></tr>
              )}
              {data.projects.map((p) => (
                <tr key={p.key}>
                  <td className="mono">{p.short}</td>
                  <td className="num">
                    {Object.values(p.status).filter((v) => v === 'on').length}
                  </td>
                  <td className="num">{p.deny}</td>
                  <td className="num">{p.corpus.toLocaleString()}</td>
                  <td>{p.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

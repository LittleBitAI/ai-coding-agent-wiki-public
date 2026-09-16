import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Candidates } from '@/components/Candidates'

// 인용으로 보이는 인라인 코드. `tool/chat.py:118` · `docs/x.md` · Git 커밋 식별자.
const FILE = /^([\w./-]+\.(?:py|md|ts|tsx|js|json|toml|ya?ml|cmd|txt|css|html|jsonl))(?::(\d+)(?:-\d+)?)?$/
const SHA = /^[0-9a-f]{7,40}$/

export type AnswerProps = {
  text: string
  remote: string
  onPeek: (path: string, line: number) => void
  onDecide?: (candidate: string, target: 'wiki' | 'claude_md' | 'drop') => Promise<string>
}

/** 답 본문. 표와 코드블록이 자주 온다 — gfm 이 그것을 든다.
 *
 *  링크는 새 탭으로 연다. 답에 붙는 링크는 거의 다 커밋 permalink 라, 눌러서
 *  원본을 대조하는 동안 대화가 사라지면 안 된다.
 *
 *  인라인 코드가 경로나 SHA 모양이면 누를 수 있게 한다 — 영상이 "원본 장면까지"
 *  라고 부른 것. 경로는 옆 서랍에서 그 줄을 보여 주고, SHA 는 GitHub 로 간다. */
export function Answer({ text, remote, onPeek, onDecide }: AnswerProps) {
  return (
    <div className="prose-answer">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto">
              <table>{children}</table>
            </div>
          ),
          code: ({ className, children }) => {
            const raw = String(children ?? '').replace(/\n$/, '')

            // ```retro-candidates 펜스 — 회고 후보. 버튼이 붙는다.
            if (className === 'language-retro-candidates') {
              return onDecide ? (
                <Candidates raw={raw} onDecide={onDecide} />
              ) : (
                <code className={className}>{raw}</code>
              )
            }
            // 다른 펜스는 그대로.
            if (className) return <code className={className}>{children}</code>

            const file = raw.match(FILE)
            if (file) {
              const line = file[2] ? Number(file[2]) : 1
              return (
                <button
                  type="button"
                  onClick={() => onPeek(file[1], line)}
                  className="cite"
                  title="이 자리를 본다"
                >
                  {raw}
                </button>
              )
            }
            if (remote && SHA.test(raw)) {
              return (
                <a href={`${remote}/commit/${raw}`} target="_blank" rel="noreferrer" className="cite">
                  {raw}
                </a>
              )
            }
            return <code>{children}</code>
          },
        }}
      >
        {text}
      </Markdown>
    </div>
  )
}

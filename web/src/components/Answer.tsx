import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Candidates } from '@/components/Candidates'

// Inline code that looks like a citation: `tool/chat.py:118`, `docs/x.md`, a
// git commit identifier.
const FILE = /^([\w./-]+\.(?:py|md|ts|tsx|js|json|toml|ya?ml|cmd|txt|css|html|jsonl))(?::(\d+)(?:-\d+)?)?$/
const SHA = /^[0-9a-f]{7,40}$/

export type AnswerProps = {
  text: string
  remote: string
  onPeek: (path: string, line: number) => void
  onDecide?: (candidate: string, target: 'wiki' | 'claude_md' | 'drop') => Promise<string>
}

/** The answer body. Tables and code blocks arrive often, and gfm holds those.
 *
 *  Links open in a new tab. Almost every link in an answer is a commit
 *  permalink, and the conversation must not disappear while the person is
 *  off comparing against the original.
 *
 *  Inline code shaped like a path or a SHA becomes clickable — "all the way
 *  to the original". A path opens that line in the side drawer; a SHA goes to
 *  GitHub. */
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

            // A ```retro-candidates fence: the retro's candidates, which get
            // buttons.
            if (className === 'language-retro-candidates') {
              return onDecide ? (
                <Candidates raw={raw} onDecide={onDecide} />
              ) : (
                <code className={className}>{raw}</code>
              )
            }
            // Every other fence stands as it is.
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

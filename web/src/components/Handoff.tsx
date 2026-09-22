import { useState } from 'react'

type Props = { text: string; onClose: () => void }

/** The text to hand the next session. Copied, and pasted into a new terminal. */
export function Handoff({ text, onClose }: Props) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // Where the clipboard is blocked, the body is still there to select by
      // hand. A failed copy must not leave the person with nothing.
    }
  }

  return (
    <div className="border-b border-border bg-card">
      <div className="mx-auto max-w-3xl px-6 py-3">
        <div className="mb-2 flex items-center justify-between">
          <div className="font-heading text-[12px] text-faint">
            인계 프롬프트 — 마지막 절은 네가 한 줄 적는다
          </div>
          <div className="flex gap-1.5">
            <button
              type="button"
              onClick={copy}
              className="rounded border border-border px-2 py-0.5 text-[11.5px] hover:bg-secondary"
            >
              {copied ? '복사됐다' : '복사'}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded px-2 py-0.5 text-[11.5px] text-muted-foreground hover:bg-secondary"
            >
              닫기
            </button>
          </div>
        </div>
        <textarea
          readOnly
          value={text}
          className="h-64 w-full resize-y rounded-md border border-border bg-background p-2 font-mono text-[11.5px] leading-snug"
        />
      </div>
    </div>
  )
}

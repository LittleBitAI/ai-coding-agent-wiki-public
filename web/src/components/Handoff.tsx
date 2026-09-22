import { useState } from 'react'
import { useOverlay } from '@/lib/overlay'

type Props = { text: string; korean: boolean; onClose: () => void }

/** The text to hand the next session. Copied, and pasted into a new terminal.
 *
 *  Two values, deliberately. What is shown is the Korean overlay; what is
 *  copied is the original. The prompt carries the last exchange of this
 *  channel, so with the answers in English the preview was English on a
 *  screen whose default is Korean — and copying a translation would hand the
 *  next session a reworded version of its own record. */
export function Handoff({ text, korean, onClose }: Props) {
  const [copied, setCopied] = useState(false)
  const [shown] = useOverlay([text], korean)

  async function copy() {
    try {
      // The original, never `shown`.
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
          value={shown}
          className="h-64 w-full resize-y rounded-md border border-border bg-background p-2 font-mono text-[11.5px] leading-snug"
        />
      </div>
    </div>
  )
}

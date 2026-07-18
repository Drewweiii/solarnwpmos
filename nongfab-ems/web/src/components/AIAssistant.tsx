import { useEffect, useState } from 'react'
import { AssistantPanel } from './AssistantPanel'
import { Mascot } from './Mascot'
import type { MascotMood } from './MascotFace'

const MOOD_REVERT_MS = 4000

/** Owns the open/closed state shared between the mascot (the toggle button)
 * and the chat panel it opens - mounted once in Layout.tsx so it floats
 * over every authenticated page. Also owns his facial expression: happy
 * right after he answers something for real, sad right after a fallback/
 * fetch-failure, reverting to the idle look after a few seconds either way. */
export function AIAssistant() {
  const [isOpen, setIsOpen] = useState(false)
  const [mood, setMood] = useState<MascotMood>('idle')

  useEffect(() => {
    if (mood === 'idle') return undefined
    const timer = setTimeout(() => setMood('idle'), MOOD_REVERT_MS)
    return () => clearTimeout(timer)
  }, [mood])

  return (
    <>
      <AssistantPanel isOpen={isOpen} onClose={() => setIsOpen(false)} onAnswered={setMood} />
      <Mascot isOpen={isOpen} onToggle={() => setIsOpen((v) => !v)} mood={mood} />
    </>
  )
}

import { useState } from 'react'
import { AssistantPanel } from './AssistantPanel'
import { Mascot } from './Mascot'
import { useMascotReaction } from '../lib/useMascotReaction'

const ANSWER_MOOD_REVERT_MS = 4000
const PLAY_REACTION_REVERT_MS = 5000

/** Owns the open/closed state shared between the mascot (the toggle button)
 * and the chat panel it opens - mounted once in Layout.tsx so it floats
 * over every authenticated page. Also owns his facial expression + speech
 * bubble via useMascotReaction.ts, fed by two independent sources: answering
 * a real question (happy/sad, no bubble, from AssistantPanel's onAnswered)
 * and "เล่นกับน้อง Solar" play interactions (any mood + a line of dialogue,
 * from AssistantPanel's onInteract) - both revert to idle/no-bubble a few
 * seconds later, and neither can ever stack past its own single timer
 * regardless of how many times it re-fires in a row (see that hook's own
 * docstring for why this needed to be more than a naive useEffect).
 */
export function AIAssistant() {
  const [isOpen, setIsOpen] = useState(false)
  const { mood, speech, trigger } = useMascotReaction()

  return (
    <>
      <AssistantPanel
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        onAnswered={(answerMood) => trigger(answerMood, null, ANSWER_MOOD_REVERT_MS)}
        onInteract={(interaction) => trigger(interaction.mood, interaction.speech, PLAY_REACTION_REVERT_MS)}
      />
      <Mascot isOpen={isOpen} onToggle={() => setIsOpen((v) => !v)} mood={mood} speech={speech} />
    </>
  )
}

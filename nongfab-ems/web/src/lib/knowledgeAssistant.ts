// A tiny, network-free "canned Q&A" engine for the 3D View page's two
// educational side-assistants, น้อง Moon (astronomy) and น้อง Cloud
// (meteorology) - see moonCloudPersonas.ts for their actual content.
//
// Deliberately NOT reusing assistant.ts (น้อง Solar): that one is tied to
// live-data intents, role-gating, and the site's own dashboard pages. These
// two are pure knowledge characters - no API calls, no auth, no role checks -
// so a much smaller, self-contained matcher keeps them from destabilizing
// น้อง Solar's own well-tested pipeline. Same "rule-based, no LLM, no API
// cost" spirit, just scoped to one persona's fixed question set.

import type { MascotInteraction } from './mascotInteractions'

export interface KnowledgeSubQuestion {
  id: string
  /** Short chip label. */
  label: string
  /** Full question text - shown as the "user" bubble and matched on. */
  question: string
  /** Canned answer (Thai, in the persona's own voice). */
  answer: string
}

export interface KnowledgeGroup {
  id: string
  title: string
  /** Bare keywords that (typed alone) surface this group's questions. */
  keywords: string[]
  subQuestions: KnowledgeSubQuestion[]
}

export interface KnowledgePersona {
  id: string
  /** Display name, e.g. "น้อง Moon". */
  name: string
  emoji: string
  /** First message shown when the panel opens. */
  greeting: string
  /** Shown under the input as a "canned, not free-form AI" disclaimer. */
  note: string
  groups: KnowledgeGroup[]
  /** "เล่นกับน้อง ..." play interactions (reuses น้อง Solar's catalog type). */
  play: MascotInteraction[]
  /** Shown when nothing matches. */
  fallback: string
}

export interface KnowledgeReply {
  text: string
  /** Follow-up chips: sibling questions in the same group, or (when nothing
   * matched) every group's first question as a browse starter. */
  suggestions: KnowledgeSubQuestion[]
}

function allSubQuestions(persona: KnowledgePersona): KnowledgeSubQuestion[] {
  return persona.groups.flatMap((g) => g.subQuestions)
}

export function findGroupOfSubQuestion(persona: KnowledgePersona, subQuestionId: string): KnowledgeGroup | null {
  return persona.groups.find((g) => g.subQuestions.some((sq) => sq.id === subQuestionId)) ?? null
}

/** One representative starter chip per group - the greeting/fallback menu. */
export function starterQuestions(persona: KnowledgePersona): KnowledgeSubQuestion[] {
  return persona.groups.map((g) => g.subQuestions[0]).filter((sq): sq is KnowledgeSubQuestion => Boolean(sq))
}

/** Sibling questions in the same group as `subQuestionId` (excluding itself),
 * so answering one always offers a natural next tap. Falls back to the
 * per-group starters when the answered question has no group (shouldn't
 * happen for a real sub-question, but keeps the return total). */
function suggestionsFor(persona: KnowledgePersona, subQuestionId: string): KnowledgeSubQuestion[] {
  const group = findGroupOfSubQuestion(persona, subQuestionId)
  if (!group) return starterQuestions(persona)
  const siblings = group.subQuestions.filter((sq) => sq.id !== subQuestionId)
  return siblings.length > 0 ? siblings : starterQuestions(persona)
}

/** Picks the sub-question whose full `question` text is the longest substring
 * of the visitor's message (longest-match-wins, same rule as น้อง Solar's
 * assistant.ts) so a menu tap - which sends the exact question text - always
 * resolves back to its own answer. A bare group keyword ("เมฆ", "ดวงจันทร์")
 * with no full-question match instead surfaces that group's questions as a
 * clarifying menu. */
export function answerFromKnowledge(persona: KnowledgePersona, question: string): KnowledgeReply {
  const lower = question.toLowerCase()

  let best: KnowledgeSubQuestion | null = null
  let bestLen = -1
  for (const sq of allSubQuestions(persona)) {
    const kw = sq.question.toLowerCase()
    if (kw.length > bestLen && lower.includes(kw)) {
      best = sq
      bestLen = kw.length
    }
  }
  if (best) {
    return { text: best.answer, suggestions: suggestionsFor(persona, best.id) }
  }

  // No full-question match - a bare topic keyword still names a group.
  for (const group of persona.groups) {
    if (group.keywords.some((kw) => lower.includes(kw.toLowerCase()))) {
      return {
        text: `เรื่อง "${group.title}" อยากรู้เรื่องไหนดีครับ เลือกได้เลย 👇`,
        suggestions: group.subQuestions,
      }
    }
  }

  return { text: persona.fallback, suggestions: starterQuestions(persona) }
}

import { describe, expect, it } from 'vitest'
import { answerFromKnowledge, findGroupOfSubQuestion, starterQuestions } from '../knowledgeAssistant'
import { CLOUD_PERSONA, KNOWLEDGE_PERSONAS, MOON_PERSONA } from '../moonCloudPersonas'

describe('answerFromKnowledge', () => {
  it('returns a sub-question\'s exact answer when its full question text is asked (menu-tap path)', () => {
    const sq = MOON_PERSONA.groups[0].subQuestions[0]
    const reply = answerFromKnowledge(MOON_PERSONA, sq.question)
    expect(reply.text).toBe(sq.answer)
  })

  it('offers a group\'s questions as a clarifying menu when only a bare keyword is typed', () => {
    // "เมฆ" is a bare keyword of น้อง Cloud's cloud_basic group, not a full question.
    const reply = answerFromKnowledge(CLOUD_PERSONA, 'เมฆ')
    expect(reply.text).toContain('เลือกได้เลย')
    expect(reply.suggestions.length).toBeGreaterThan(0)
    expect(reply.suggestions.every((sq) => CLOUD_PERSONA.groups.some((g) => g.subQuestions.includes(sq)))).toBe(true)
  })

  it('falls back with starter suggestions when nothing matches', () => {
    const reply = answerFromKnowledge(MOON_PERSONA, 'ราคาหุ้นวันนี้เท่าไหร่')
    expect(reply.text).toBe(MOON_PERSONA.fallback)
    expect(reply.suggestions).toEqual(starterQuestions(MOON_PERSONA))
  })

  it('suggests sibling questions in the same group after answering one', () => {
    const group = MOON_PERSONA.groups.find((g) => g.subQuestions.length > 1)!
    const first = group.subQuestions[0]
    const reply = answerFromKnowledge(MOON_PERSONA, first.question)
    // Every suggestion is a sibling (same group), never the answered one itself.
    expect(reply.suggestions).not.toContainEqual(first)
    expect(reply.suggestions.every((sq) => group.subQuestions.includes(sq))).toBe(true)
  })

  it('picks the longest-matching question when one question text contains another', () => {
    // Guards the longest-match rule: asking a full question must never resolve
    // to a shorter question whose text is a substring of it.
    for (const persona of KNOWLEDGE_PERSONAS) {
      for (const group of persona.groups) {
        for (const sq of group.subQuestions) {
          expect(answerFromKnowledge(persona, sq.question).text).toBe(sq.answer)
        }
      }
    }
  })
})

describe('persona data integrity', () => {
  it('every sub-question has a unique id across both personas', () => {
    const ids = KNOWLEDGE_PERSONAS.flatMap((p) => p.groups.flatMap((g) => g.subQuestions.map((sq) => sq.id)))
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('every sub-question has a non-empty answer and resolves back to its own group', () => {
    for (const persona of KNOWLEDGE_PERSONAS) {
      for (const group of persona.groups) {
        for (const sq of group.subQuestions) {
          expect(sq.answer.trim().length).toBeGreaterThan(0)
          expect(findGroupOfSubQuestion(persona, sq.id)?.id).toBe(group.id)
        }
      }
    }
  })

  it('starterQuestions returns one representative per group', () => {
    for (const persona of KNOWLEDGE_PERSONAS) {
      expect(starterQuestions(persona)).toHaveLength(persona.groups.length)
    }
  })

  it('both personas have play interactions', () => {
    expect(MOON_PERSONA.play.length).toBeGreaterThan(0)
    expect(CLOUD_PERSONA.play.length).toBeGreaterThan(0)
  })
})

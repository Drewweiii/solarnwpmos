import { describe, expect, it } from 'vitest'
import { TOPIC_ANSWERS } from '../assistantContent'
import { ALL_TOPIC_GROUPS, findClarifyGroup, findCategoryById, findGroupById, findGroupBySubQuestionId, TOPIC_CATEGORIES } from '../assistantTopics'

// A guard against the exact failure mode this content is expected to grow
// into over many future sessions: adding a sub-question to assistantTopics.ts
// but forgetting its answer in assistantContent.ts (or vice versa).
describe('assistantTopics/assistantContent consistency', () => {
  it('every sub-question across every category has a matching answer, and every answer has a sub-question', () => {
    const subQuestionIds = ALL_TOPIC_GROUPS.flatMap((g) => g.subQuestions.map((sq) => sq.id))
    const answerIds = Object.keys(TOPIC_ANSWERS)

    for (const id of subQuestionIds) {
      expect(answerIds).toContain(id)
    }
    for (const id of answerIds) {
      expect(subQuestionIds).toContain(id)
    }
  })

  it('sub-question ids are globally unique', () => {
    const ids = ALL_TOPIC_GROUPS.flatMap((g) => g.subQuestions.map((sq) => sq.id))
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('every answer is non-empty and speaks as the male character (never หนู/ค่ะ/คะ)', () => {
    for (const [id, text] of Object.entries(TOPIC_ANSWERS)) {
      expect(text.length, `answer for ${id} should not be empty`).toBeGreaterThan(0)
      expect(text, `answer for ${id} should use ผม/ครับ, not หนู/ค่ะ/คะ`).not.toMatch(/หนู|ค่ะ|คะ/)
    }
  })
})

describe('findClarifyGroup', () => {
  it('finds the Inverter group from a bare keyword, in Thai or English', () => {
    expect(findClarifyGroup('inverter')?.id).toBe('inverter')
    expect(findClarifyGroup('อยากรู้เรื่องอินเวอร์เตอร์')?.id).toBe('inverter')
  })

  it('returns null for a question that names no known group', () => {
    expect(findClarifyGroup('อยากรู้เรื่องดวงจันทร์')).toBeNull()
  })
})

describe('lookup helpers', () => {
  it('findGroupBySubQuestionId finds the owning group', () => {
    expect(findGroupBySubQuestionId('inv_what')?.id).toBe('inverter')
    expect(findGroupBySubQuestionId('nonexistent-id')).toBeNull()
  })

  it('findCategoryById / findGroupById resolve real ids from TOPIC_CATEGORIES', () => {
    expect(findCategoryById('system')?.title).toBeTruthy()
    expect(findCategoryById('nope')).toBeNull()
    expect(findGroupById('inverter')?.title).toBe('Inverter')
    expect(findGroupById('nope')).toBeNull()
  })

  it('every category has at least one group, every group at least one sub-question', () => {
    for (const category of TOPIC_CATEGORIES) {
      expect(category.groups.length).toBeGreaterThan(0)
      for (const group of category.groups) {
        expect(group.subQuestions.length).toBeGreaterThan(0)
      }
    }
  })
})

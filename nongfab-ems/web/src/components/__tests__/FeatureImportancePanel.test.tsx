import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type { FeatureImportanceResponse } from '../../lib/types'
import { FeatureImportancePanel } from '../FeatureImportancePanel'

function renderPanel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <FeatureImportancePanel zone="GIS" />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

describe('FeatureImportancePanel', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('renders an honest empty state when no model is trained', async () => {
    vi.spyOn(api, 'getFeatureImportance').mockResolvedValue({
      available: false,
      zone: 'GIS',
      items: [],
      new_features_total: null,
    } satisfies FeatureImportanceResponse)
    renderPanel()
    expect(await screen.findByText(/ยังไม่มีโมเดล/)).toBeInTheDocument()
  })

  it('headlines the new-feature contribution when a model exists', async () => {
    vi.spyOn(api, 'getFeatureImportance').mockResolvedValue({
      available: true,
      zone: 'GIS',
      items: [
        { feature: 'ssrd_w_m2', importance: 0.6, is_new: false },
        { feature: 'salt_soiling_index', importance: 0.25, is_new: true },
        { feature: 'aod_550nm', importance: 0.15, is_new: true },
      ],
      new_features_total: 0.4,
    } satisfies FeatureImportanceResponse)
    renderPanel()
    // 0.4 -> "40.0%" headline.
    await waitFor(() => expect(screen.getByText(/40\.0%/)).toBeInTheDocument())
    expect(screen.getByText(/Feature importance/i)).toBeInTheDocument()
  })
})

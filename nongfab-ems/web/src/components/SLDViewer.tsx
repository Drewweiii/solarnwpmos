// Interactive single-line diagram built from the zone's own real equipment
// data (see features/src/nongfab_features/sld.py's module docstring) - not
// a scanned image of the original SLD PDF (none is bundled in this repo).
// Plain HTML buttons/divs rather than an SVG canvas so every node is
// keyboard-operable and click-testable without simulating hover.

import { useState } from 'react'
import type { SLDData } from '../lib/types'

interface Selection {
  kind: 'block' | 'string'
  blockId: string
  stringId?: string
}

interface SLDViewerProps {
  sld: SLDData
}

export function SLDViewer({ sld }: SLDViewerProps) {
  const [selected, setSelected] = useState<Selection | null>(null)

  const selectedBlock = selected ? sld.blocks.find((b) => b.id === selected.blockId) : undefined
  const selectedString =
    selected?.kind === 'string' ? selectedBlock?.strings.find((s) => s.id === selected.stringId) : undefined

  return (
    <div className="sld-viewer">
      <div className="sld-diagram">
        {sld.blocks.map((block) => (
          <div key={block.id} className="sld-block-row">
            <div className="sld-strings">
              {block.strings.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  className={
                    selected?.kind === 'string' && selected.stringId === s.id && selected.blockId === block.id
                      ? 'sld-node sld-node-string selected'
                      : 'sld-node sld-node-string'
                  }
                  onClick={() => setSelected({ kind: 'string', blockId: block.id, stringId: s.id })}
                >
                  <span className="sld-node-title">{s.id}</span>
                  <span className="sld-node-sub">{s.modules} modules</span>
                </button>
              ))}
            </div>
            <span className="sld-connector" aria-hidden="true" />
            <button
              type="button"
              className={
                selected?.kind === 'block' && selected.blockId === block.id
                  ? 'sld-node sld-node-inverter selected'
                  : 'sld-node sld-node-inverter'
              }
              onClick={() => setSelected({ kind: 'block', blockId: block.id })}
            >
              <span className="sld-node-title">{block.id}</span>
              <span className="sld-node-sub">{block.inverter_ac_kw} kW</span>
            </button>
            <span className="sld-connector" aria-hidden="true" />
            <div className="sld-node sld-node-ac" aria-hidden="true">
              <span className="sld-node-title">AC Grid</span>
            </div>
          </div>
        ))}
      </div>

      <div className="sld-detail" role="status">
        {!selected && <p className="sld-detail-hint">Click a string or inverter to see its specs.</p>}
        {selected?.kind === 'string' && selectedString && (
          <dl>
            <dt>String</dt>
            <dd>{selectedString.id}</dd>
            <dt>Modules</dt>
            <dd>
              {selectedString.modules} x {sld.module_power_w} W (
              {((selectedString.modules * sld.module_power_w) / 1000).toFixed(2)} kWp)
            </dd>
            <dt>Module model</dt>
            <dd>{sld.module_model ?? 'n/a'}</dd>
            {sld.optimizer_model && (
              <>
                <dt>Optimizer</dt>
                <dd>
                  {sld.optimizer_model} (1 per {sld.optimizer_ratio_modules_per_optimizer} modules)
                </dd>
              </>
            )}
          </dl>
        )}
        {selected?.kind === 'block' && selectedBlock && (
          <dl>
            <dt>Block</dt>
            <dd>{selectedBlock.id}</dd>
            <dt>Inverter</dt>
            <dd>{selectedBlock.inverter_model}</dd>
            <dt>AC rating</dt>
            <dd>{selectedBlock.inverter_ac_kw} kW</dd>
            <dt>MPPT inputs</dt>
            <dd>{selectedBlock.mppt_count}</dd>
            <dt>Strings</dt>
            <dd>{selectedBlock.strings.length}</dd>
          </dl>
        )}
      </div>

      {sld.approximate_string_distribution && (
        <p className="sld-approx-note">
          Per-string module counts are an even-split approximation - no per-string survey exists for this zone.
        </p>
      )}
    </div>
  )
}

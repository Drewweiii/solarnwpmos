import { describe, expect, it } from 'vitest'
import {
  DEFAULT_SATELLITE_ZOOM,
  esriWorldImageryTileGrid,
  esriWorldImageryTileUrl,
  latLonToTile,
  metersPerPixel,
  tileFootprintMeters,
} from '../satelliteTile'

describe('latLonToTile', () => {
  it('the whole world is one tile at zoom 0', () => {
    expect(latLonToTile(0, 0, 0)).toEqual({ x: 0, y: 0, z: 0 })
    expect(latLonToTile(12.7, 101.1, 0)).toEqual({ x: 0, y: 0, z: 0 })
  })

  it('the equator/prime-meridian corner sits at the center tile at any zoom', () => {
    const { x, y, z } = latLonToTile(0, 0, 4)
    expect(z).toBe(4)
    expect(x).toBe(2 ** 4 / 2)
    expect(y).toBe(2 ** 4 / 2)
  })

  it('moving east increases the tile x index', () => {
    const west = latLonToTile(12.7, 100.0, 12)
    const east = latLonToTile(12.7, 102.0, 12)
    expect(east.x).toBeGreaterThan(west.x)
  })

  it('moving north decreases the tile y index (Mercator y grows southward)', () => {
    const south = latLonToTile(10.0, 101.1, 12)
    const north = latLonToTile(15.0, 101.1, 12)
    expect(north.y).toBeLessThan(south.y)
  })

  it('clamps tile indices to the valid [0, 2^zoom - 1] range', () => {
    const { x, y } = latLonToTile(89, 179.9, 3)
    expect(x).toBeGreaterThanOrEqual(0)
    expect(x).toBeLessThan(2 ** 3)
    expect(y).toBeGreaterThanOrEqual(0)
    expect(y).toBeLessThan(2 ** 3)
  })
})

describe('metersPerPixel / tileFootprintMeters', () => {
  it('resolution gets finer (smaller meters/pixel) at higher zoom', () => {
    expect(metersPerPixel(12.7, 10)).toBeGreaterThan(metersPerPixel(12.7, 19))
  })

  it('a tile at the default zoom comfortably covers a GIS/ISB-sized panel array at Nong Fab\'s latitude', () => {
    const footprint = tileFootprintMeters(12.7, DEFAULT_SATELLITE_ZOOM)
    expect(footprint).toBeGreaterThan(200)
    expect(footprint).toBeLessThan(400)
  })
})

describe('esriWorldImageryTileUrl', () => {
  it('builds a z/y/x Esri tile URL (Esri\'s own path order, not the usual z/x/y)', () => {
    const url = esriWorldImageryTileUrl(12.7, 101.1, 10)
    expect(url).toMatch(/^https:\/\/server\.arcgisonline\.com\/ArcGIS\/rest\/services\/World_Imagery\/MapServer\/tile\/10\/\d+\/\d+$/)
  })

  it('defaults to DEFAULT_SATELLITE_ZOOM when no zoom is given', () => {
    const url = esriWorldImageryTileUrl(12.7, 101.1)
    expect(url).toContain(`/tile/${DEFAULT_SATELLITE_ZOOM}/`)
  })
})

describe('esriWorldImageryTileGrid', () => {
  it('returns cols*rows tiles, forced to odd dims so it stays centered', () => {
    expect(esriWorldImageryTileGrid(12.7, 101.1, 3, 3)).toHaveLength(9)
    // even dims round up to the next odd (4 -> 5)
    expect(esriWorldImageryTileGrid(12.7, 101.1, 2, 4)).toHaveLength(3 * 5)
  })

  it('the center tile sits at offset (0, 0) and matches the single-tile URL', () => {
    const grid = esriWorldImageryTileGrid(12.7, 101.1, 3, 5)
    const center = grid.find((t) => t.offsetEastM === 0 && t.offsetNorthM === 0)
    expect(center).toBeDefined()
    expect(center!.url).toBe(esriWorldImageryTileUrl(12.7, 101.1))
  })

  it('tiles are spaced by one footprint; north offset grows northward, east eastward', () => {
    const footprint = tileFootprintMeters(12.7, DEFAULT_SATELLITE_ZOOM)
    const grid = esriWorldImageryTileGrid(12.7, 101.1, 3, 3)
    const easts = [...new Set(grid.map((t) => t.offsetEastM))].sort((a, b) => a - b)
    const norths = [...new Set(grid.map((t) => t.offsetNorthM))].sort((a, b) => a - b)
    expect(easts).toEqual([-footprint, 0, footprint].map((v) => expect.closeTo(v, 3)))
    expect(norths).toEqual([-footprint, 0, footprint].map((v) => expect.closeTo(v, 3)))
    expect(grid.every((t) => t.sizeM === footprint)).toBe(true)
  })

  it('a tall grid (few cols, many rows) covers a long north-south span like Jetty', () => {
    const footprint = tileFootprintMeters(12.7, DEFAULT_SATELLITE_ZOOM)
    const grid = esriWorldImageryTileGrid(12.7, 101.1, 3, 7)
    const northSpan = Math.max(...grid.map((t) => t.offsetNorthM)) - Math.min(...grid.map((t) => t.offsetNorthM))
    // 7 rows -> 6 gaps of one footprint, comfortably past Jetty's ~1.25km array span.
    expect(northSpan).toBeCloseTo(6 * footprint, 3)
    expect(northSpan).toBeGreaterThan(1250)
  })
})

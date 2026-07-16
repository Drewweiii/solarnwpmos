import { describe, expect, it } from 'vitest'
import { DEFAULT_SATELLITE_ZOOM, esriWorldImageryTileUrl, latLonToTile, metersPerPixel, tileFootprintMeters } from '../satelliteTile'

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

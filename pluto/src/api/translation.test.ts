import { describe, it, expect, vi, afterEach } from 'vitest'

// API_BASE reads window.location at import; mock the dep so this runs in the plain node env.
vi.mock('../composables/useNodes', () => ({ API_BASE: 'http://test:7700' }))

import { translationApi } from './translation'

afterEach(() => vi.restoreAllMocks())

// The whole point of the wrappers: a failed write is a THROWN error, never a silent swallow —
// that swallow is exactly what let "Saved ✓" show while drafts never reached disk.
describe('translationApi.putState — must reject when the write does not land', () => {
  it('rejects on a non-ok HTTP response (e.g. 500)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500, statusText: 'err' }))
    await expect(translationApi.putState('game', { sources: {} })).rejects.toThrow()
  })
  it('rejects on a network failure (API down)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('ECONNREFUSED')))
    await expect(translationApi.putState('game', { sources: {} })).rejects.toThrow()
  })
  it('resolves with the parsed body on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ ok: true, game: 'game' }) }))
    await expect(translationApi.putState('game', { sources: {} })).resolves.toEqual({ ok: true, game: 'game' })
  })
  it('PUTs to /translate/<ns> with the JSON body', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({}) })
    vi.stubGlobal('fetch', fetchMock)
    await translationApi.putState('Boku [ca]', { total: 5 })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://test:7700/translate/Boku%20%5Bca%5D')
    expect(init).toMatchObject({ method: 'PUT' })
    expect(JSON.parse(init.body)).toEqual({ total: 5 })
  })
})

describe('translationApi.measure — same throw-on-failure contract (frozen meter otherwise)', () => {
  it('rejects on a non-ok response so the caller can flag the meter stale', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 502, statusText: 'bad' }))
    await expect(translationApi.measure('/disc.gdi', 'STORY.PAC', [])).rejects.toThrow()
  })
})

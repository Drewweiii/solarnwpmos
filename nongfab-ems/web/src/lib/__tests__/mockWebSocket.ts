/** Minimal WebSocket stub for tests - jsdom has no real WebSocket transport,
 * so useChatSocket.ts's `new WebSocket(url)` is redirected here via
 * `vi.stubGlobal('WebSocket', MockWebSocket)`. Captures every constructed
 * instance on the static `instances` array so a test can grab the most
 * recent one and drive it (`.open()`, `.emit(data)`, `.close()`) like a fake
 * server.
 */
export class MockWebSocket {
  static instances: MockWebSocket[] = []
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3

  url: string
  readyState = MockWebSocket.CONNECTING
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  sent: string[] = []

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  open(): void {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.()
  }

  send(data: string): void {
    this.sent.push(data)
  }

  close(): void {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.()
  }

  emit(data: unknown): void {
    this.onmessage?.({ data: JSON.stringify(data) })
  }
}

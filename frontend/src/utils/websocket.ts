import type { WsMessage } from '@/types'

type MessageHandler<T = unknown> = (data: T) => void

export class WarpWebSocket {
  private ws: WebSocket | null = null
  private url: string
  private listeners: Map<string, Set<MessageHandler>> = new Map()
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private reconnectDelay = 1000
  private isManualClose = false

  constructor(url: string) {
    this.url = url
  }

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        resolve()
        return
      }

      this.isManualClose = false
      const wsUrl = this.url.startsWith('ws')
        ? this.url
        : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}${this.url}`

      this.ws = new WebSocket(wsUrl)

      this.ws.onopen = () => {
        console.log(`WebSocket connected: ${this.url}`)
        this.reconnectAttempts = 0
        resolve()
      }

      this.ws.onmessage = (event) => {
        try {
          const msg: WsMessage = JSON.parse(event.data)
          const handlers = this.listeners.get(msg.type)
          if (handlers) {
            handlers.forEach((handler) => handler(msg.data))
          }
          // 也触发通配符处理器
          const allHandlers = this.listeners.get('*')
          if (allHandlers) {
            allHandlers.forEach((handler) => handler(msg))
          }
        } catch (e) {
          console.error('WebSocket message parse error:', e)
        }
      }

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        reject(error)
      }

      this.ws.onclose = () => {
        console.log(`WebSocket closed: ${this.url}`)
        if (!this.isManualClose && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++
          console.log(
            `Reconnecting... attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts}`
          )
          setTimeout(() => this.connect(), this.reconnectDelay * this.reconnectAttempts)
        }
      }
    })
  }

  disconnect(): void {
    this.isManualClose = true
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }

  on<T = unknown>(type: string, handler: MessageHandler<T>): () => void {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set())
    }
    this.listeners.get(type)!.add(handler as MessageHandler)

    // 返回取消订阅函数
    return () => {
      this.listeners.get(type)?.delete(handler as MessageHandler)
    }
  }

  off<T = unknown>(type: string, handler: MessageHandler<T>): void {
    this.listeners.get(type)?.delete(handler as MessageHandler)
  }

  send(data: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
    } else {
      console.warn('WebSocket is not connected')
    }
  }

  subscribe(channel: string, ticker = 'ETH'): void {
    this.send({ action: 'subscribe', channel, ticker })
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }
}

// 预定义的 WebSocket 实例
export const snapshotWs = new WarpWebSocket('/ws/snapshots')
export const signalWs = new WarpWebSocket('/ws/signals')
export const alertWs = new WarpWebSocket('/ws/alerts')

export default WarpWebSocket

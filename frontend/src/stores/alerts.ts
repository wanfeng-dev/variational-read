import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Alert } from '@/types'
import { api } from '@/api'
import { alertWs } from '@/utils/websocket'

export const useAlertsStore = defineStore('alerts', () => {
  // 状态
  const alerts = ref<Alert[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const wsConnected = ref(false)
  const total = ref(0)

  // 筛选条件
  const filter = ref({
    type: '' as string,
    priority: '' as string,
    start: '' as string,
    end: '' as string,
  })

  // 计算属性
  const unacknowledgedCount = computed(
    () => alerts.value.filter((a) => !a.acknowledged).length
  )
  const highPriorityAlerts = computed(() =>
    alerts.value.filter((a) => a.priority === 'HIGH' && !a.acknowledged)
  )
  const recentAlerts = computed(() => alerts.value.slice(0, 10))

  // 操作
  async function fetchAlerts(params?: {
    type?: string
    priority?: string
    start?: string
    end?: string
    limit?: number
  }) {
    loading.value = true
    try {
      const res = await api.getAlertHistory(params ?? { limit: 100 })
      alerts.value = res.alerts
      total.value = res.total
    } catch (e) {
      error.value = '获取预警列表失败'
      console.error(e)
    } finally {
      loading.value = false
    }
  }

  async function acknowledgeAlert(alertId: number) {
    try {
      const res = await api.acknowledgeAlert(alertId)
      if (res.success) {
        // 更新本地状态
        const idx = alerts.value.findIndex((a) => a.id === alertId)
        if (idx !== -1) {
          alerts.value[idx].acknowledged = true
        }
      }
    } catch (e) {
      error.value = '确认预警失败'
      console.error(e)
    }
  }

  async function acknowledgeAll() {
    const unacknowledged = alerts.value.filter((a) => !a.acknowledged)
    for (const alert of unacknowledged) {
      await acknowledgeAlert(alert.id)
    }
  }

  // WebSocket 连接
  async function connectWs() {
    try {
      await alertWs.connect()
      wsConnected.value = true

      // 订阅新预警
      alertWs.on<Alert>('alert', (data) => {
        alerts.value = [data, ...alerts.value]
        total.value++
      })

      alertWs.subscribe('alerts')
    } catch (e) {
      console.error('预警 WebSocket 连接失败:', e)
      wsConnected.value = false
    }
  }

  function disconnectWs() {
    alertWs.disconnect()
    wsConnected.value = false
  }

  // 应用筛选
  async function applyFilter() {
    await fetchAlerts({
      type: filter.value.type || undefined,
      priority: filter.value.priority || undefined,
      start: filter.value.start || undefined,
      end: filter.value.end || undefined,
      limit: 100,
    })
  }

  // 初始化
  async function init() {
    await fetchAlerts({ limit: 50 })
    await connectWs()
  }

  return {
    // 状态
    alerts,
    loading,
    error,
    wsConnected,
    total,
    filter,
    // 计算属性
    unacknowledgedCount,
    highPriorityAlerts,
    recentAlerts,
    // 操作
    fetchAlerts,
    acknowledgeAlert,
    acknowledgeAll,
    connectWs,
    disconnectWs,
    applyFilter,
    init,
  }
})

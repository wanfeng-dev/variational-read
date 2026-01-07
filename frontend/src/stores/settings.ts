import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import type { DataSource, Ticker } from '@/types'

export const useSettingsStore = defineStore('settings', () => {
  // 当前选中的数据源
  const currentSource = ref<DataSource>(
    (localStorage.getItem('currentSource') as DataSource) || 'bybit'
  )

  // 当前选中的标的
  const currentTicker = ref<Ticker>(
    (localStorage.getItem('currentTicker') as Ticker) || 'ETH'
  )

  // 是否显示所有数据源
  const showAllSources = ref<boolean>(
    localStorage.getItem('showAllSources') === 'true'
  )

  // 持久化
  watch(currentSource, (val) => {
    localStorage.setItem('currentSource', val)
  })

  watch(currentTicker, (val) => {
    localStorage.setItem('currentTicker', val)
  })

  watch(showAllSources, (val) => {
    localStorage.setItem('showAllSources', String(val))
  })

  // 切换数据源
  function setSource(source: DataSource) {
    currentSource.value = source
  }

  // 切换标的
  function setTicker(ticker: Ticker) {
    currentTicker.value = ticker
  }

  // 获取当前 key
  function getCurrentKey(): string {
    return `${currentSource.value}-${currentTicker.value}`
  }

  return {
    currentSource,
    currentTicker,
    showAllSources,
    setSource,
    setTicker,
    getCurrentKey,
  }
})

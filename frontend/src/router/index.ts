import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: () => import('@/views/Dashboard.vue'),
      meta: { title: '仪表盘' },
    },
    {
      path: '/signals',
      name: 'signals',
      component: () => import('@/views/Signals.vue'),
      meta: { title: '信号面板' },
    },
    {
      path: '/alerts',
      name: 'alerts',
      component: () => import('@/views/Alerts.vue'),
      meta: { title: '预警中心' },
    },
    {
      path: '/backtest',
      name: 'backtest',
      component: () => import('@/views/Backtest.vue'),
      meta: { title: '回测' },
    },
  ],
})

// 设置页面标题
router.afterEach((to) => {
  const title = to.meta.title as string
  document.title = title ? `${title} - Variational ETH` : 'Variational ETH 交易系统'
})

export default router

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAlertsStore } from '@/stores/alerts'

const route = useRoute()
const alertsStore = useAlertsStore()
const mobileMenuOpen = ref(false)

const currentPath = computed(() => route.path)

const navItems = [
  { path: '/', label: '仪表盘' },
  { path: '/signals', label: '信号' },
  { path: '/alerts', label: '预警' },
  { path: '/backtest', label: '回测' },
]
</script>

<template>
  <div class="app">
    <!-- 顶部导航 -->
    <header class="header">
      <div class="header-content">
        <!-- Logo -->
        <div class="logo">
          <svg class="logo-icon" viewBox="0 0 40 40" fill="none">
            <path d="M8 28C8 28 12 20 20 20C28 20 32 28 32 28" stroke="#4A9EFF" stroke-width="3" stroke-linecap="round"/>
            <path d="M12 24C12 24 15 18 20 18C25 18 28 24 28 24" stroke="#4A9EFF" stroke-width="2" stroke-linecap="round" opacity="0.6"/>
          </svg>
          <div class="logo-text">
            <span class="title">Variational ETH</span>
            <span class="subtitle">High Win-Rate Trading</span>
          </div>
        </div>

        <!-- 桌面导航 -->
        <nav class="nav-desktop">
          <router-link
            v-for="item in navItems"
            :key="item.path"
            :to="item.path"
            class="nav-item"
            :class="{ active: currentPath === item.path }"
          >
            {{ item.label }}
            <span
              v-if="item.path === '/alerts' && alertsStore.unacknowledgedCount"
              class="nav-badge"
            >
              {{ alertsStore.unacknowledgedCount }}
            </span>
          </router-link>
        </nav>

        <!-- 移动端菜单按钮 -->
        <button class="mobile-menu-btn" @click="mobileMenuOpen = !mobileMenuOpen">
          <span></span>
          <span></span>
          <span></span>
        </button>
      </div>

      <!-- 移动端导航 -->
      <nav v-if="mobileMenuOpen" class="nav-mobile">
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: currentPath === item.path }"
          @click="mobileMenuOpen = false"
        >
          {{ item.label }}
        </router-link>
      </nav>
    </header>

    <!-- 主内容区 -->
    <main class="main">
      <router-view />
    </main>
  </div>
</template>

<style>
/* 全局样式 - Variational Funding Map 风格 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

:root {
  /* 深色背景 */
  --bg-primary: #0d1421;
  --bg-secondary: #131c2e;
  --bg-card: #1a2332;
  --bg-card-hover: #202d40;
  
  /* 边框 - 蓝色调 */
  --border-card: #2a3a52;
  --border-accent: #3a5a8a;
  --border-active: #4a9eff;
  
  /* 文字 */
  --text-primary: #ffffff;
  --text-secondary: #8b9cb8;
  --text-muted: #5a6a7a;
  
  /* 强调色 */
  --accent-blue: #4a9eff;
  --accent-cyan: #22d3ee;
  --success: #22c55e;
  --success-bg: rgba(34, 197, 94, 0.15);
  --danger: #ef4444;
  --danger-bg: rgba(239, 68, 68, 0.15);
  --warning: #f59e0b;
  
  /* 圆角 */
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-full: 9999px;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: var(--bg-primary);
  color: var(--text-primary);
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

a {
  text-decoration: none;
  color: inherit;
}

button {
  font-family: inherit;
}

::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: var(--border-card);
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--border-accent);
}
</style>

<style scoped>
.app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.header {
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-card);
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: 16px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo-icon {
  width: 36px;
  height: 36px;
}

.logo-text {
  display: flex;
  flex-direction: column;
}

.logo-text .title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
}

.logo-text .subtitle {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.2;
}

.nav-desktop {
  display: flex;
  gap: 8px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 18px;
  border-radius: var(--radius-full);
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s ease;
  border: 1px solid transparent;
}

.nav-item:hover {
  color: var(--text-primary);
  background: var(--bg-card);
}

.nav-item.active {
  background: var(--accent-blue);
  color: #fff;
}

.nav-badge {
  background: var(--danger);
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: var(--radius-full);
  min-width: 18px;
  text-align: center;
}

.mobile-menu-btn {
  display: none;
  flex-direction: column;
  gap: 5px;
  padding: 8px;
  background: none;
  border: none;
  cursor: pointer;
}

.mobile-menu-btn span {
  display: block;
  width: 20px;
  height: 2px;
  background: var(--text-secondary);
  border-radius: 1px;
  transition: all 0.2s;
}

.mobile-menu-btn:hover span {
  background: var(--text-primary);
}

.nav-mobile {
  display: none;
  flex-direction: column;
  padding: 12px 20px 20px;
  gap: 8px;
  background: var(--bg-secondary);
  border-top: 1px solid var(--border-card);
}

.nav-mobile .nav-item {
  padding: 14px 20px;
  border-radius: var(--radius-md);
  justify-content: center;
}

@media (max-width: 768px) {
  .header-content {
    padding: 12px 16px;
  }
  
  .logo-text .title {
    font-size: 16px;
  }
  
  .logo-text .subtitle {
    display: none;
  }
  
  .nav-desktop {
    display: none;
  }

  .mobile-menu-btn {
    display: flex;
  }

  .nav-mobile {
    display: flex;
  }
}

.main {
  flex: 1;
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
  padding: 0;
}
</style>
